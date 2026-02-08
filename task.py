import pandas as pd
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from collections import deque
from pathlib import Path

class Task:
    def __init__(self, id: int, part_number: str,
                 name: str, successors_str: str, task_type: TaskType):
        self.id = int(id)
        self.part_number = part_number
        self.name = name
        self.successors_ids = self._parse_successor_ids(successors_str)
        self.task_type = task_type
        self.successors_tasks: List['Task'] = [] # To be populated in a second pass
        self.init_date: Optional[datetime] = None
        self.end_date: Optional[datetime] = None
        self.predecessors: List['Task'] = [] # To be populated in a later pass
        self.duration: int = 10

    def _parse_successor_ids(self, successors_str: str) -> List[int]:
        """Parses a comma-separated string of successor IDs into a list of integers."""
        if not successors_str:
            return []
        return [int(s.strip()) for s in str(successors_str).split(',') if s.strip()]

    def __repr__(self):
        init_date_str = self.init_date.strftime('%Y-%m-%d') if self.init_date else 'None'
        end_date_str = self.end_date.strftime('%Y-%m-%d') if self.end_date else 'None'
        return (f"Task(id={self.id}, type='{self.task_type.description}', "
                f"name='{self.name}', successors_ids={self.successors_ids}, "
                f"init_date='{init_date_str}', end_date='{end_date_str}', duration={self.duration})")

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

        # Fourth pass: Populate predecessors for each task
        for task in tasks:
            for successor_task in task.successors_tasks:
                successor_task.predecessors.append(task)


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

def calculate_task_dates(tasks: List[Task], today_date: datetime):
    """
    Calculates init_date and end_date for all tasks based on dependencies and duration.
    Implements a topological sort for scheduling.
    """
    # Initialize in-degrees for all tasks (count of predecessors not yet scheduled)
    in_degree = {task.id: len(task.predecessors) for task in tasks}
    
    # Queue for tasks ready to be scheduled (no unscheduled predecessors)
    ready_queue = deque()

    # Find tasks with no predecessors and add them to the ready queue
    for task in tasks:
        if in_degree[task.id] == 0:
            ready_queue.append(task)
            task.init_date = today_date
            task.end_date = task.init_date + timedelta(minutes=task.duration)

    scheduled_count = 0
    while ready_queue:
        current_task = ready_queue.popleft()
        scheduled_count += 1

        # Propagate dates to successors
        for successor_task in current_task.successors_tasks:
            # Update successor's init_date based on current_task's end_date
            # A successor's init_date is the latest end_date of all its predecessors
            if successor_task.init_date is None or current_task.end_date > successor_task.init_date:
                successor_task.init_date = current_task.end_date
            
            # Decrement in-degree for successor
            in_degree[successor_task.id] -= 1
            if in_degree[successor_task.id] == 0:
                # If all predecessors are scheduled, calculate its end_date and add to queue
                if successor_task.init_date is None: # Should not happen if logic is correct
                    successor_task.init_date = today_date # Fallback
                successor_task.end_date = successor_task.init_date + timedelta(minutes=successor_task.duration)
                ready_queue.append(successor_task)
    
    if scheduled_count != len(tasks):
        print("Warning: Cyclic dependency detected or some tasks could not be scheduled.")



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

def export_tasks_to_mermaid_graph(tasks: List[Task], output_file_path: Optional[Path] = None, detail_level: str = 'full') -> str:
    """
    Generates a Mermaid flowchart (graph TD) representation of tasks.
    Can generate a detailed graph of individual tasks or a high-level graph based on task types.
    """
    mermaid_lines = ["graph TD"]

    if detail_level == 'full':
        node_styles = [] # Collect style directives here

        # Define color mapping for task types
        task_type_colors = {
            'release': 'fill:#F96',        # Orange
            'drawing': 'fill:#9F6',        # Light Green
            'part_model': 'fill:#69F',     # Light Blue
            'part_list': 'fill:#FC6',      # Yellow-Orange
            'milestone': 'fill:#C6F'       # Purple
        }

        # Define nodes with details and shapes for individual tasks
        for task in tasks:
            init_date_str = task.init_date.strftime('%Y-%m-%d') if task.init_date else 'None'
            end_date_str = task.end_date.strftime('%Y-%m-%d') if task.end_date else 'None'

            shape_map = {
                'release': '[[{}]]',
                'drawing': '({})',
                'part_model': '({})',
                'part_list': '{{{}}}',
                'milestone': '(( {} ))'
            }
            shape_template = shape_map.get(task.task_type.description, '[{}]')

            node_label_content = (f"{task.name}<br>"
                                  f"Type: {task.task_type.description}<br>"
                                  f"Part No: {task.part_number}<br>"
                                  f"Init: {init_date_str}<br>"
                                  f"End: {end_date_str}<br>"
                                  f"Dur: {task.duration}min")
            
            node_definition = f"{task.id}{shape_template.format(node_label_content)}"
            mermaid_lines.append(f"    {node_definition}")

            # Add style directive for the node
            color_style = task_type_colors.get(task.task_type.description, 'fill:#CCC') # Default light gray
            node_styles.append(f"    style {task.id} {color_style}")

        # Define edges (dependencies) for individual tasks
        for task in tasks:
            for successor_task in task.successors_tasks:
                mermaid_lines.append(f"    {task.id} --> {successor_task.id}")
        
        # Append node styles after all nodes and edges
        mermaid_lines.extend(node_styles)

    elif detail_level == 'type':
        # Collect unique task types and their connections
        unique_task_types = set()
        type_dependencies = set() # Stores (source_type_desc, target_type_desc)

        for task in tasks:
            source_type_desc = task.task_type.description
            unique_task_types.add(source_type_desc)

            for successor_task in task.successors_tasks:
                target_type_desc = successor_task.task_type.description
                unique_task_types.add(target_type_desc)
                type_dependencies.add((source_type_desc, target_type_desc))

        # Define nodes for each unique task type description
        def sanitize_id(text: str) -> str:
            return text.replace(" ", "_").replace("-", "_").replace(".", "").lower()

        for type_desc in sorted(list(unique_task_types)):
            sanitized_id = sanitize_id(type_desc)
            mermaid_lines.append(f"    {sanitized_id}[{type_desc}]")

        # Define edges between task types
        for source_type_desc, target_type_desc in sorted(list(type_dependencies)):
            sanitized_source_id = sanitize_id(source_type_desc)
            sanitized_target_id = sanitize_id(target_type_desc)
            mermaid_lines.append(f"    {sanitized_source_id} --> {sanitized_target_id}")

    else:
        raise ValueError(f"Unknown detail_level: {detail_level}. Expected 'full' or 'type'.")
            
    mermaid_syntax = "\n".join(mermaid_lines)

    if output_file_path:
        try:
            output_file_path.write_text(mermaid_syntax)
            print(f"Mermaid graph exported to: {output_file_path}")
        except Exception as e:
            print(f"Error exporting Mermaid graph to {output_file_path}: {e}")
            
    return mermaid_syntax

def export_tasks_to_mermaid_gantt(tasks: List[Task], output_file_path: Optional[Path] = None, detail_level: str = 'full') -> str:
    """
    Generates a Mermaid Gantt chart representation of tasks.
    Can generate a detailed chart of individual tasks or a high-level chart based on task types.
    """
    mermaid_lines = [
        "gantt",
        "    dateFormat  YYYY-MM-DD HH:mm",
        "    axisFormat %H:%M",
        "    title       Task Schedule Overview"
    ]

    # Define color mapping for task types
    task_type_colors = {
        'release': 'fill:#F96',        # Orange
        'drawing': 'fill:#9F6',        # Light Green
        'part_model': 'fill:#69F',     # Light Blue
        'part_list': 'fill:#FC6',      # Yellow-Orange
        'milestone': 'fill:#C6F'       # Purple
    }

    # Helper to sanitize ID for Mermaid class names (if needed for type-level)
    def sanitize_id(text: str) -> str:
        return text.replace(" ", "_").replace("-", "_").replace(".", "").lower()

    # SECTION: Full Detail Gantt Chart
    if detail_level == 'full':
        mermaid_lines.append("    section All Tasks")
        gantt_styles = [] # Collect style directives here

        for task in tasks:
            init_date_str = task.init_date.strftime('%Y-%m-%d %H:%M') if task.init_date else 'None'
            end_date_str = task.end_date.strftime('%Y-%m-%d %H:%M') if task.end_date else 'None'

            # Task label for the Gantt bar
            task_label = f"{task.name} ({task.part_number}) ({task.task_type.description})"

            # Gantt task syntax: Task Name :id, start_date, end_date
            if task.init_date and task.end_date:
                mermaid_lines.append(f"    {task_label} :{task.id}, {init_date_str}, {end_date_str}")
            else:
                # Fallback for tasks without calculated dates (should not happen with scheduling logic)
                mermaid_lines.append(f"    {task_label} :{task.id}, {init_date_str}, {task.duration}min") 

            # Add style directive for the task
            color_style = task_type_colors.get(task.task_type.description, 'fill:#CCC') # Default light gray
            gantt_styles.append(f"    style {task.id} {color_style},stroke:#333")

        # Append style directives
        mermaid_lines.extend(gantt_styles)

    # SECTION: Type Detail Gantt Chart
    elif detail_level == 'type':
        mermaid_lines.append("    section Task Types Overview")
        type_date_spans = {} # {type_desc: {'min_init': datetime, 'max_end': datetime}}

        for task in tasks:
            type_desc = task.task_type.description
            if type_desc not in type_date_spans:
                type_date_spans[type_desc] = {'min_init': task.init_date, 'max_end': task.end_date}
            
            # Update min_init_date for the type
            if task.init_date and (type_date_spans[type_desc]['min_init'] is None or task.init_date < type_date_spans[type_desc]['min_init']):
                type_date_spans[type_desc]['min_init'] = task.init_date
            
            # Update max_end_date for the type
            if task.end_date and (type_date_spans[type_desc]['max_end'] is None or task.end_date > type_date_spans[type_desc]['max_end']):
                type_date_spans[type_desc]['max_end'] = task.end_date
        
        gantt_styles = [] # Collect style directives for types
        for type_desc in sorted(type_date_spans.keys()):
            type_info = type_date_spans[type_desc]
            type_id = sanitize_id(type_desc) # Use sanitized ID for Gantt bar
            min_init_str = type_info['min_init'].strftime('%Y-%m-%d %H:%M') if type_info['min_init'] else 'None'
            max_end_str = type_info['max_end'].strftime('%Y-%m-%d %H:%M') if type_info['max_end'] else 'None'

            if type_info['min_init'] and type_info['max_end']:
                mermaid_lines.append(f"    {type_desc} :{type_id}, {min_init_str}, {max_end_str}")
            else:
                mermaid_lines.append(f"    {type_desc} :{type_id}, {min_init_str}, 0min") # Fallback for types without calculated dates

            color_style = task_type_colors.get(type_desc, 'fill:#CCC') # Default light gray
            gantt_styles.append(f"    style {type_id} {color_style},stroke:#333")
        
        mermaid_lines.extend(gantt_styles)

    else:
        raise ValueError(f"Unknown detail_level: {detail_level}. Expected 'full' or 'type'.")
            
    mermaid_syntax = "\n".join(mermaid_lines)

    if output_file_path:
        try:
            output_file_path.write_text(mermaid_syntax)
            print(f"Mermaid Gantt chart exported to: {output_file_path}")
        except Exception as e:
            print(f"Error exporting Mermaid Gantt chart to {output_file_path}: {e}")
            
    return mermaid_syntax



if __name__ == "__main__":
    # Example usage
    csv_path = '/Users/mchiozzi/sdev/personal/chrono_tailoring/deliverable_structure.csv'
    all_tasks = load_tasks(csv_path)
    
    today_str = "2026-02-08" # As per user context "Sunday, February 8, 2026"
    today_date_obj = datetime.strptime(today_str, '%Y-%m-%d')
    calculate_task_dates(all_tasks, today_date_obj)

    print("\n--- First 5 Tasks ---")
    for t in all_tasks[:5]:
        print(t)
        if t.successors_tasks:
            print(f"  Successor Tasks (IDs): {[st.id for st in t.successors_tasks]}")
        if t.predecessors:
            print(f"  Predecessor Tasks (IDs): {[pt.id for pt in t.predecessors]}")

    print("\n--- Task with no predecessors (if any) ---")
    found_no_predecessor_task = False
    for t in all_tasks:
        if not t.predecessors:
            print(t)
            found_no_predecessor_task = True
            break
    if not found_no_predecessor_task:
        print("No task found with no predecessors.")


    print("\n--- Customization Types ---")
    customization_overview_path = '/Users/mchiozzi/sdev/personal/chrono_tailoring/customization_overview.csv'
    all_customization_types = load_customization_types(customization_overview_path)
    for ct in all_customization_types[:5]:
        print(ct)

    print("\n--- Updating Customization Overview CSV ---")
    update_customization_overview_csv(customization_overview_path)

    print("\n--- Exporting Task Flow to Mermaid Graph (Full Detail) ---")
    mermaid_output_path_full = Path("task_flow.mmd")
    export_tasks_to_mermaid_graph(all_tasks, mermaid_output_path_full, detail_level='full')

    print("\n--- Exporting Task Flow to Mermaid Graph (High-Level by Type) ---")
    mermaid_output_path_type = Path("task_flow_high_level.mmd")
    export_tasks_to_mermaid_graph(all_tasks, mermaid_output_path_type, detail_level='type')

    print("\n--- Exporting Task Flow to Mermaid Gantt Chart (Full Detail) ---")
    mermaid_output_path_gantt_full = Path("task_flow_gantt.mmd")
    export_tasks_to_mermaid_gantt(all_tasks, mermaid_output_path_gantt_full, detail_level='full')

    print("\n--- Exporting Task Flow to Mermaid Gantt Chart (High-Level by Type) ---")
    mermaid_output_path_gantt_type = Path("task_flow_gantt_high_level.mmd")
    export_tasks_to_mermaid_gantt(all_tasks, mermaid_output_path_gantt_type, detail_level='type')