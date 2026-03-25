import json
import pandas as pd
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Set, Optional

from src.core.models import Task, TaskType, CustomizationType
from src import config

# [Req: RF-01, RF-01.1, RF-01.2, RF-01.3, RF-01.4] — Reads project config; supports new {settings,milestones} and legacy flat-array formats
def load_project_requirements(file_path: Path):
    """Reads project requirements from a JSON file.

    Supports two formats:
      - New: { "settings": {...}, "milestones": [...] }
      - Legacy: [...] (flat array of milestone dicts)

    Args:
        file_path (Path): Path to the project requirements JSON file.

    Returns:
        tuple: A tuple containing:
            - settings (dict): Global project configuration settings.
            - milestones (List[Dict]): The list of configured milestones.
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        if isinstance(data, list):  # [Req: RF-01.2] — Legacy format: no settings block
            # Legacy format — no settings block
            return {}, data

        # [Req: RF-01.1] — New format: explicit settings + milestones keys
        settings = data.get('settings', {})
        milestones = data.get('milestones', [])
        return settings, milestones

    except FileNotFoundError:  # [Req: RF-01.4] — Graceful error handling; no unhandled exception
        print(f"Error: Project requirements file not found at {file_path}")
        return {}, []
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from project requirements file {file_path}: {e}")
        return {}, []

# [Req: RF-25, RF-25.1, RF-25.2, RF-25.3] — Loads holidays into a Set[date] for O(1) lookup in is_working_day
def load_holidays(file_path: Path) -> Set[date]:
    """Loads holidays from a CSV file into a set of date objects.

    Args:
        file_path (Path): Path to the holidays.csv file.

    Returns:
        Set[date]: A set containing all valid parsed holiday dates.
    """
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

# [Req: RF-06.1, RNF-16] — Resolves customization type name to its dedicated CSV file path under input/, and caches DataFrame in memory
def load_customization_types(file_path: Path) -> List[CustomizationType]:
    """Reads customization types from a CSV file, constructs their file paths, and caches them in memory.

    Args:
        file_path (Path): Path to the customization_overview.csv file.

    Returns:
        List[CustomizationType]: A list of resolved CustomizationType configurations.
    """
    try:
        import pandas as pd
        df = pd.read_csv(file_path, delimiter=';')
        
        customization_types = []
        for custom_type in df['customization_type']:
            path_str = f"customization_{custom_type}.csv"
            customization_csv = config.INPUT_DIR / path_str
            
            # [Req: RNF-16, RNF-20] — Load CSV into memory once and convert to Hash Map
            lookup_dict = None
            if customization_csv.exists():
                df_cache = pd.read_csv(customization_csv, delimiter=';')
                df_cache = df_cache.loc[:, ~df_cache.columns.str.contains('^Unnamed')]
                df_cache.columns = df_cache.columns.str.lower()
                
                lookup_dict = {}
                for _, row in df_cache.iterrows():
                    doc_name = str(row.get('document_name', '')).strip().lower()
                    doc_type = str(row.get('part_document_type', '')).strip().lower()
                    row_dict = row.to_dict()
                    if doc_name and doc_name != 'nan':
                        lookup_dict[doc_name] = row_dict
                    elif doc_type and doc_type != 'nan':
                        lookup_dict[doc_type] = row_dict
                
            customization_types.append(CustomizationType(name=custom_type, file_path=customization_csv, df=lookup_dict))
            
        return customization_types
    except FileNotFoundError:
        print(f"Error: Customization overview file not found at {file_path}")
        return []

# [Req: RF-02, RF-02.1, RF-02.2, RF-02.3, RF-02.4, RF-02.5] — Loads all tasks from deliverable_structure.csv into raw Task objects
def load_raw_tasks_from_csv(task_csv_path: Path) -> List[Task]:
    """Loads all tasks from the CSV file into raw Task objects.
    
    This is used to create a template of tasks before any milestone-specific processing.

    Args:
        task_csv_path (Path): Path to the `deliverable_structure.csv` file.

    Returns:
        List[Task]: A sequential list of un-linked baseline Task templates.
    """
    raw_tasks: List[Task] = []
    try:
        df = pd.read_csv(task_csv_path, delimiter=';')
        print(f"DEBUG load_raw_tasks: found {len(df)} rows in {task_csv_path}")
        df['strategy'] = df['strategy'].fillna('')
        # Only fill string/object columns with '' — numeric columns stay as NaN
        obj_cols = df.select_dtypes(include='object').columns
        df[obj_cols] = df[obj_cols].fillna('')

        # [Req: RF-02.5] — Cache TaskType objects by (description, strategy) to avoid duplicates
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

            # [Req: RF-02.2] — Read standard duration directly in minutes; NaN / missing values default to 0
            duration_val = 0
            if 'std_duration' in row:
                duration_val = float(row['std_duration']) if pd.notna(row['std_duration']) and str(row['std_duration']).strip() else 0
            elif 'execution_std(h)' in row:
                duration_val = float(row['execution_std(h)']) if pd.notna(row['execution_std(h)']) and str(row['execution_std(h)']).strip() else 0

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
        # [Req: RF-02.4] — Resolve successors_tasks and predecessors using original CSV IDs
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

# [Req: RF-06, RF-06.2, RF-06.3, RF-06.4, RNF-16] — Looks up a task's duration in a cached customization DataFrame, matching by name or type
def read_customization_duration(lookup_dict: Any, customization_name: str,
                                customization_value: str, task_name: str, task_type_desc: str) -> Optional[int]:
    """Reads the duration from a specific customization cached Hash Map.

    Args:
        lookup_dict (Any): The cached dictionary containing the CSV configurations.
        customization_name (str): The customization tag.
        customization_value (str): The value selected for the customization.
        task_name (str): The target task name.
        task_type_desc (str): The target task type.

    Returns:
        Optional[int]: The parsed duration in minutes. None if not matched.
    """
    if lookup_dict is None or not isinstance(lookup_dict, dict):
        return None

    try:
        import pandas as pd
        column_candidate = f"{task_type_desc.lower()}_st"
        
        match = lookup_dict.get(task_name.lower())
        if not match:
            match = lookup_dict.get(task_type_desc.lower())
            
        if match:
            # Maybe the column name maps exactly to the customization_name (legacy approach)
            if column_candidate not in match:
                column_candidate = 'duration_st' if 'duration_st' in match else 'std_duration'

            if column_candidate in match:
                val = match[column_candidate]
                return int(val) if pd.notna(val) else None

        return None
    except Exception as e:
        print(f"An unexpected error occurred while reading customization duration: {e}")
        return None
