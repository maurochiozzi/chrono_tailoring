import json
import pandas as pd
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Set, Optional

from src.core.models import Task, TaskType, CustomizationType
from src import config

def load_project_requirements(file_path: Path):
    """
    Reads project requirements from a JSON file.

    Supports two formats:
      - New: { "settings": {...}, "milestones": [...] }
      - Legacy: [...] (flat array of milestone dicts)

    Returns a tuple: (settings: dict, milestones: List[Dict])
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        if isinstance(data, list):
            # Legacy format — no settings block
            return {}, data

        settings = data.get('settings', {})
        milestones = data.get('milestones', [])
        return settings, milestones

    except FileNotFoundError:
        print(f"Error: Project requirements file not found at {file_path}")
        return {}, []
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from project requirements file {file_path}: {e}")
        return {}, []

def load_holidays(file_path: Path) -> Set[date]:
    """Loads holidays from a CSV file into a set of date objects."""
    holidays_set: Set[date] = set()
    try:
        with open(file_path, 'r') as f:
            for line in f:
                try:
                    holiday_date = datetime.strptime(line.strip(), '%Y-%m-%d').date()
                    holidays_set.add(holiday_date)
                except ValueError:
                    print(f"Warning: Could not parse date from line in holidays.csv: {line.strip()}")
        return holidays_set
    except FileNotFoundError:
        print(f"Error: Holidays file not found at {file_path}")
        return set()

def load_customization_types(file_path: Path) -> List[CustomizationType]:
    """Reads customization types from a CSV file and constructs their file paths."""
    try:
        df = pd.read_csv(file_path, delimiter=';')
        customization_types = []
        for _, row in df.iterrows():
            name = row['customization_type']
            customization_file_path = config.INPUT_DIR / f"customization_{name}.csv"
            customization_types.append(CustomizationType(name=name, file_path=str(customization_file_path)))
        return customization_types
    except FileNotFoundError:
        print(f"Error: Customization overview file not found at {file_path}")
        return []

def load_raw_tasks_from_csv(task_csv_path: Path) -> List[Task]:
    """
    Loads all tasks from the CSV file into raw Task objects.
    This is used to create a template of tasks before any milestone-specific processing.
    """
    raw_tasks: List[Task] = []
    try:
        df = pd.read_csv(task_csv_path, delimiter=';')
        print(f"DEBUG load_raw_tasks: found {len(df)} rows in {task_csv_path}")
        df['strategy'] = df['strategy'].fillna('')
        # Only fill string/object columns with '' — numeric columns stay as NaN
        obj_cols = df.select_dtypes(include='object').columns
        df[obj_cols] = df[obj_cols].fillna('')

        task_type_cache = {}

        for _, row in df.iterrows():
            description = row['document_type']
            strategy = row['strategy'] if row['strategy'] else None

            cache_key = (description, strategy)
            if cache_key not in task_type_cache:
                task_type_cache[cache_key] = TaskType(description=description, strategy=strategy)
            
            current_task_type = task_type_cache[cache_key]
            task_id = int(row['document_id'])
            part_num = str(row['document_part_number'])
            
            # The original parsing function _parse_successor_ids expects to parse the string here
            # We rewrite the basic logic locally
            successors_str = str(row['successors'])

            duration_val = 0
            if 'std_duration' in row:
                duration_val = float(row['std_duration']) * 60 if pd.notna(row['std_duration']) and str(row['std_duration']).strip() else 0
            elif 'execution_std(h)' in row:
                duration_val = float(row['execution_std(h)']) * 60 if pd.notna(row['execution_std(h)']) and str(row['execution_std(h)']).strip() else 0

            task = Task(
                id=task_id,
                part_number=part_num,
                name=row['document_name'],
                task_type=current_task_type,
                successors_str=successors_str,
                duration_minutes=int(duration_val)
            )
            raw_tasks.append(task)
        
        # Resolve immediate successors and predecessors for raw tasks using their original CSV IDs
        raw_task_id_map = {task.id: task for task in raw_tasks}
        for task in raw_tasks:
            # Emulating task.resolve_successors(raw_task_id_map)
            task.successors_tasks = []
            for succ_id in getattr(task, 'successors_ids', []):
                if succ_id in raw_task_id_map:
                    task.successors_tasks.append(raw_task_id_map[succ_id])
            
        for task in raw_tasks:
            for successor_task in task.successors_tasks:
                successor_task.predecessors.append(task)

        return raw_tasks

    except Exception as e:
        print(f"Error reading Task CSV file {task_csv_path}: {e}")
        import traceback
        traceback.print_exc()
        return []

def read_customization_duration(file_path: Path, customization_name: str, 
                                customization_value: str, task_name: str, task_type_desc: str) -> Optional[int]:
    """
    Reads the duration from a specific customization CSV file.
    """
    try:
        df = pd.read_csv(file_path, delimiter=';')
        df.columns = df.columns.str.lower()
        
        # Try extracting the corresponding column matching the task_type based on standard or custom strategies
        column_candidate = f"{task_type_desc}_st"
        if column_candidate not in df.columns:
            # Maybe the column name maps exactly to the customization_name (legacy approach)
            column_candidate = 'duration_st' if 'duration_st' in df.columns else 'std_duration'
            
        mask = None
        if 'document_name' in df.columns:
             mask = (df['document_name'].str.lower() == task_name.lower())
        elif 'part_document_type' in df.columns:
             mask = (df['part_document_type'].str.lower() == task_type_desc.lower())
             
        if mask is not None:
             match = df[mask]
             if not match.empty:
                 if column_candidate in match.columns:
                     val = match.iloc[0][column_candidate]
                     return int(val) if pd.notna(val) else None

        return None
    except FileNotFoundError:
        print(f"Error: Customization file not found at {file_path}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while reading customization duration: {e}")
        return None
