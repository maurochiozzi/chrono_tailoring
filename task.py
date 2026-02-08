import pandas as pd
from typing import List, Optional

class Task:
    def __init__(self, id: int, part_number: str,
                 name: str, successors_str: str, task_type: TaskType):
        self.id = int(id)
        self.part_number = part_number
        self.name = name
        self.successors_ids = self._parse_successor_ids(successors_str)
        self.task_type = task_type
        self.successors_tasks: List['Task'] = [] # To be populated in a second pass

    def _parse_successor_ids(self, successors_str: str) -> List[int]:
        """Parses a comma-separated string of successor IDs into a list of integers."""
        if not successors_str:
            return []
        return [int(s.strip()) for s in str(successors_str).split(',') if s.strip()]

    def __repr__(self):
        return (f"Task(id={self.id}, type='{self.task_type.description}', "
                f"name='{self.name}', successors={self.successors_ids})")

    def resolve_successors(self, all_tasks_map: Dict[int, 'Task']):
        """Resolves successor IDs into actual Task objects."""
        for successor_id in self.successors_ids:
            if successor_id in all_tasks_map:
                self.successors_tasks.append(all_tasks_map[successor_id])
            else:
                print(f"Warning: Successor ID {successor_id} for Task {self.id} not found.")

class TaskType:
    def __init__(self, description: str, strategy: Optional[str] = None):
        self.description = description
        self.strategy = strategy if strategy else None # Ensure empty string becomes None

    def __repr__(self):
        return f"TaskType(description='{self.description}', strategy='{self.strategy}')"

class CustomizationType:
    def __init__(self, name: str, file_path: str):
        self.name = name
        self.file_path = file_path
    
    def __repr__(self):
        return f"CustomizationType(name='{self.name}', file_path='{self.file_path}')"

def load_tasks(file_path: str) -> List[Task]:
    """Reads tasks from a semicolon-delimited CSV file."""
    try:
        df = pd.read_csv(file_path, delimiter=';')
        # Fill NaN values in 'strategy' column with empty strings specifically
        df['strategy'] = df['strategy'].fillna('')
        df.fillna('', inplace=True)  # Replace remaining NaN with empty strings

        task_type_cache = {} # Cache for TaskType objects

        tasks = []
        for _, row in df.iterrows():
            # Get description and strategy for TaskType
            description = row['document_type']
            strategy = row['strategy'] if row['strategy'] else None # Convert empty string to None for consistency in cache key

            # Check if TaskType already exists in cache
            cache_key = (description, strategy)
            if cache_key not in task_type_cache:
                task_type_cache[cache_key] = TaskType(description=description, strategy=strategy)
            
            current_task_type = task_type_cache[cache_key]

            tasks.append(
                Task(
                    id=row['document_id'],
                    part_number=row['document_part_number'],
                    name=row['document_name'],
                    successors_str=row['successors'], # Pass the raw string
                    task_type=current_task_type
                )
            )
        
        # Second pass: Create a map of all tasks for successor resolution
        task_id_to_task_map = {task.id: task for task in tasks}

        # Third pass: Resolve successors for each task
        for task in tasks:
            task.resolve_successors(task_id_to_task_map)

        return tasks
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return []

def load_customization_types(file_path: str) -> List[CustomizationType]:
    """Reads customization types from a CSV file and constructs their file paths."""
    try:
        df = pd.read_csv(file_path, delimiter=';')
        customization_types = []
        for _, row in df.iterrows():
            name = row['customization_type']
            # Assuming file names are in the format customization_{name}.csv
            file_path = f"customization_{name}.csv"
            customization_types.append(CustomizationType(name=name, file_path=file_path))
        return customization_types
    except FileNotFoundError:
        print(f"Error: Customization overview file not found at {file_path}")
        return []

import os

def update_customization_overview_csv(file_path: str):
    """
    Reads customization_overview.csv, adds 'path' and 'status' columns,
    and writes the updated DataFrame back to the CSV.
    """
    try:
        df = pd.read_csv(file_path, delimiter=';')
        
        # Drop any unnamed columns that pandas might create (e.g., from trailing delimiters)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        
        # Add 'path' column
        df['path'] = df['customization_type'].apply(lambda name: f"customization_{name}.csv")
        
        # Add 'status' column
        # This assumes the customization files are in the same directory as customization_overview.csv
        df['status'] = df['path'].apply(lambda p: 'ok' if os.path.exists(p) else 'nok')
        
        # Write the updated DataFrame back to the CSV
        df.to_csv(file_path, sep=';', index=False)
        print(f"Updated {file_path} with 'path' and 'status' columns.")

    except FileNotFoundError:
        print(f"Error: Customization overview file not found at {file_path}")
    except Exception as e:
        print(f"An error occurred while updating {file_path}: {e}")



if __name__ == "__main__":
    # Example usage
    csv_path = '/Users/mchiozzi/sdev/personal/chrono_tailoring/deliverable_structure.csv'
    all_tasks = load_tasks(csv_path)
    for t in all_tasks[:5]:
        print(t)
        if t.successors_tasks:
            print(f"  Successor Tasks: {[st.id for st in t.successors_tasks]}")

    print("\n--- Customization Types ---")
    customization_overview_path = '/Users/mchiozzi/sdev/personal/chrono_tailoring/customization_overview.csv'
    all_customization_types = load_customization_types(customization_overview_path)
    for ct in all_customization_types[:5]:
        print(ct)

    print("\n--- Updating Customization Overview CSV ---")
    update_customization_overview_csv(customization_overview_path)