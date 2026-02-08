import pandas as pd
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from collections import deque
from pathlib import Path
import copy # Added import

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

class ProjectSchedule: # Renamed from CustomizationDeliverable
    def __init__(self, task_csv_path: Optional[str] = None, tasks: Optional[List[Task]] = None, num_resources: int = 1, customization_overview_csv_path: Optional[str] = None):
        self.num_resources = num_resources
        
        if tasks is not None:
            self.tasks = tasks
        elif task_csv_path:
            self.tasks = self._load_tasks(task_csv_path)
        else:
            raise ValueError("Either 'tasks' or 'task_csv_path' must be provided.")

        self.customization_types: List[CustomizationType] = []
        if customization_overview_csv_path:
            self.customization_types = self._load_customization_types(customization_overview_csv_path)
        
        # Assuming "today's date" for scheduling start is fixed or passed in.
        today_str = "2026-02-08"
        today_date_obj = datetime.strptime(today_str, '%Y-%m-%d')
        self._calculate_task_dates(today_date_obj)

    def _load_tasks(self, file_path: str) -> List[Task]:
        """Reads tasks from a semicolon-delimited CSV file."""
        try:
            df = pd.read_csv(file_path, delimiter=';')
            df['strategy'] = df['strategy'].fillna('')
            df.fillna('', inplace=True)

            task_type_cache = {}
            tasks = []
            for _, row in df.iterrows():
                description = row['document_type']
                strategy = row['strategy'] if row['strategy'] else None

                cache_key = (description, strategy)
                if cache_key not in task_type_cache:
                    task_type_cache[cache_key] = TaskType(description=description, strategy=strategy)
                
                current_task_type = task_type_cache[cache_key]

                tasks.append(
                    Task(
                        id=row['document_id'],
                        part_number=row['document_part_number'],
                        name=row['document_name'],
                        successors_str=row['successors'],
                        task_type=current_task_type
                    )
                )
            
            task_id_to_task_map = {task.id: task for task in tasks}

            for task in tasks:
                task.resolve_successors(task_id_to_task_map)

            for task in tasks:
                for successor_task in task.successors_tasks:
                    successor_task.predecessors.append(task)
            return tasks
        except FileNotFoundError:
            print(f"Error: File not found at {file_path}")
            return []

    def _load_customization_types(self, file_path: str) -> List[CustomizationType]:
        """Reads customization types from a CSV file and constructs their file paths."""
        try:
            df = pd.read_csv(file_path, delimiter=';')
            customization_types = []
            for _, row in df.iterrows():
                name = row['customization_type']
                file_path = f"customization_{name}.csv"
                customization_types.append(CustomizationType(name=name, file_path=file_path))
            return customization_types
        except FileNotFoundError:
            print(f"Error: Customization overview file not found at {file_path}")
            return []

    def _calculate_task_dates(self, today_date: datetime):
        """
        Calculates init_date and end_date for all tasks based on dependencies and duration.
        Implements a topological sort for scheduling with resource constraints.
        """
        in_degree = {task.id: len(task.predecessors) for task in self.tasks}
        tasks_by_id = {task.id: task for task in self.tasks}

        resource_free_time = [today_date] * self.num_resources

        tasks_earliest_start_by_pred = {task.id: today_date for task in self.tasks}

        ready_to_schedule_pq = [] 

        for task in self.tasks:
            if in_degree[task.id] == 0:
                tasks_earliest_start_by_pred[task.id] = today_date
                ready_to_schedule_pq.append((today_date, task.id))
        
        ready_to_schedule_pq.sort()

        scheduled_count = 0
        while scheduled_count < len(self.tasks):
            if not ready_to_schedule_pq:
                print("Warning: Cyclic dependency detected or some tasks could not be scheduled.")
                break

            best_task_index_in_pq = -1
            earliest_feasible_start = None
            resource_index_for_best_task = -1

            for i, (pred_earliest_start, task_id) in enumerate(ready_to_schedule_pq):
                current_task_obj = tasks_by_id[task_id]

                earliest_possible_start_on_any_resource = None
                assigned_resource_index_for_this_task = -1

                for res_idx, res_time in enumerate(resource_free_time):
                    potential_start_time_on_this_resource = max(pred_earliest_start, res_time)

                    if assigned_resource_index_for_this_task == -1 or potential_start_time_on_this_resource < earliest_possible_start_on_any_resource:
                        earliest_possible_start_on_any_resource = potential_start_time_on_this_resource
                        assigned_resource_index_for_this_task = res_idx
                
                if best_task_index_in_pq == -1 or earliest_possible_start_on_any_resource < earliest_feasible_start:
                    best_task_index_in_pq = i
                    earliest_feasible_start = earliest_possible_start_on_any_resource
                    resource_index_for_best_task = assigned_resource_index_for_this_task
                
                elif earliest_possible_start_on_any_resource == earliest_feasible_start and task_id < tasks_by_id[ready_to_schedule_pq[best_task_index_in_pq][1]].id:
                     best_task_index_in_pq = i
                     earliest_feasible_start = earliest_possible_start_on_any_resource
                     resource_index_for_best_task = assigned_resource_index_for_this_task


            if best_task_index_in_pq == -1:
                print("Error: Could not find a task to schedule. Check scheduling logic.")
                break
            
            _, current_task_id = ready_to_schedule_pq.pop(best_task_index_in_pq)
            current_task = tasks_by_id[current_task_id]

            current_task.init_date = earliest_feasible_start
            current_task.end_date = current_task.init_date + timedelta(minutes=current_task.duration)
            
            resource_free_time[resource_index_for_best_task] = current_task.end_date

            scheduled_count += 1

            for successor_task in current_task.successors_tasks:
                in_degree[successor_task.id] -= 1
                
                tasks_earliest_start_by_pred[successor_task.id] = max(
                    tasks_earliest_start_by_pred[successor_task.id],
                    current_task.end_date
                )

                if in_degree[successor_task.id] == 0:
                    if (tasks_earliest_start_by_pred[successor_task.id], successor_task.id) not in ready_to_schedule_pq:
                        ready_to_schedule_pq.append((tasks_earliest_start_by_pred[successor_task.id], successor_task.id))
                        ready_to_schedule_pq.sort()

        if scheduled_count != len(self.tasks):
            print("Warning: Cyclic dependency detected or some tasks could not be scheduled.")

    def get_deliverable_init_date(self) -> Optional[datetime]:
        earliest_init = None
        for task in self.tasks:
            if task.init_date:
                if earliest_init is None or task.init_date < earliest_init:
                    earliest_init = task.init_date
        return earliest_init

    def get_deliverable_end_date(self) -> Optional[datetime]:
        latest_end = None
        for task in self.tasks:
            if task.end_date:
                if latest_end is None or task.end_date > latest_end:
                    latest_end = task.end_date
        return latest_end

    def get_total_duration(self) -> Optional[timedelta]:
        earliest_init = self.get_deliverable_init_date()
        latest_end = self.get_deliverable_end_date()
        if earliest_init and latest_end:
            return latest_end - earliest_init
        return None

    def __repr__(self):
        init_date_str = self.get_deliverable_init_date().strftime('%Y-%m-%d %H:%M') if self.get_deliverable_init_date() else 'None'
        end_date_str = self.get_deliverable_end_date().strftime('%Y-%m-%d %H:%M') if self.get_deliverable_end_date() else 'None'
        total_duration = self.get_total_duration()
        total_duration_str = str(total_duration) if total_duration else 'None'
        return (f"ProjectSchedule(num_tasks={len(self.tasks)}, "
                f"num_resources={self.num_resources}, "
                f"earliest_init='{init_date_str}', latest_end='{end_date_str}', "
                f"total_duration='{total_duration_str}')")

    @staticmethod
    def _load_tasks_static(file_path: str) -> List[Task]:
        """Reads tasks from a semicolon-delimited CSV file (static version)."""
        try:
            df = pd.read_csv(file_path, delimiter=';')
            df['strategy'] = df['strategy'].fillna('')
            df.fillna('', inplace=True)

            task_type_cache = {}
            tasks = []
            for _, row in df.iterrows():
                description = row['document_type']
                strategy = row['strategy'] if row['strategy'] else None

                cache_key = (description, strategy)
                if cache_key not in task_type_cache:
                    task_type_cache[cache_key] = TaskType(description=description, strategy=strategy)
                
                current_task_type = task_type_cache[cache_key]

                tasks.append(
                    Task(
                        id=row['document_id'],
                        part_number=row['document_part_number'],
                        name=row['document_name'],
                        successors_str=row['successors'],
                        task_type=current_task_type
                    )
                )
            
            task_id_to_task_map = {task.id: task for task in tasks}

            for task in tasks:
                task.resolve_successors(task_id_to_task_map)

            for task in tasks:
                for successor_task in task.successors_tasks:
                    successor_task.predecessors.append(task)
            return tasks
        except FileNotFoundError:
            print(f"Error: File not found at {file_path}")
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
            if task.end_date and (type_date_spans[type_desc]['max_end'] is None or type_date_spans[type_desc]['max_end'] < task.end_date):
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
            print(f"Error exporting Mermaid Gantt chart to {output_plot_path}: {e}")
            
    return mermaid_syntax

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    print("Warning: Matplotlib not found. Plotting will be skipped. Install with 'pip install matplotlib'.")
    MATPLOTLIB_AVAILABLE = False

def plot_resource_vs_duration(
    task_csv_path: str,
    customization_overview_csv_path: Optional[str] = None,
    max_resources: int = 10,
    output_plot_path: Optional[Path] = None
):
    """
    Runs scheduling for 1 to max_resources, collects total durations, and plots the results.
    """
    num_resources_list = []
    total_duration_minutes_list = []

    print(f"\n--- Analyzing Resource vs. Duration (1 to {max_resources} Resources) ---")
    
    # Load tasks once outside the loop to avoid redundant loading
    base_tasks = ProjectSchedule._load_tasks_static(task_csv_path)

    for num_res in range(1, max_resources + 1):
        # Create a deep copy of the base tasks list to ensure a fresh state for each scheduling run
        tasks_for_run = copy.deepcopy(base_tasks)
        
        # Create ProjectSchedule instance, which will schedule the tasks
        temp_project_schedule = ProjectSchedule(
            tasks=tasks_for_run, # Pass pre-loaded and copied tasks
            task_csv_path=None, # Indicate that tasks are already provided
            num_resources=num_res,
            customization_overview_csv_path=customization_overview_csv_path
        )
        
        total_duration = temp_project_schedule.get_total_duration()
        if total_duration:
            # Convert timedelta to total minutes for plotting
            total_duration_minutes = total_duration.total_seconds() / 60
            num_resources_list.append(num_res)
            total_duration_minutes_list.append(total_duration_minutes)
            print(f"  Resources: {num_res}, Total Duration: {total_duration_minutes:.2f} minutes")
        else:
            print(f"  Resources: {num_res}, Could not calculate total duration.")

    if MATPLOTLIB_AVAILABLE:
        plt.figure(figsize=(10, 6))
        plt.plot(num_resources_list, total_duration_minutes_list, marker='o', linestyle='-')
        plt.title('Project Duration vs. Number of Resources')
        plt.xlabel('Number of Resources')
        plt.ylabel('Total Project Duration (minutes)')
        plt.grid(True)
        plt.xticks(num_resources_list)
        plt.tight_layout()

        if output_plot_path:
            plt.savefig(output_plot_path)
            print(f"Plot saved to: {output_plot_path}")
        else:
            plt.show()
    else:
        print("\nRaw Data (Number of Resources, Total Duration in Minutes):")
        for i in range(len(num_resources_list)):
            print(f"{num_resources_list[i]}, {total_duration_minutes_list[i]:.2f}")



if __name__ == "__main__":
    csv_path = '/Users/mchiozzi/sdev/personal/chrono_tailoring/deliverable_structure.csv'
    customization_overview_csv_path = '/Users/mchiozzi/sdev/personal/chrono_tailoring/customization_overview.csv'

    # Create ProjectSchedule instance
    num_resources_for_project = 2
    project_schedule = ProjectSchedule(
        task_csv_path=csv_path,
        num_resources=num_resources_for_project,
        customization_overview_csv_path=customization_overview_csv_path
    )

    print(f"\n--- Project Schedule Summary ({num_resources_for_project} Resources) ---")
    print(project_schedule)

    print("\n--- First 5 Tasks ---")
    for t in project_schedule.tasks[:5]:
        print(t)
        if t.successors_tasks:
            print(f"  Successor Tasks (IDs): {[st.id for st in t.successors_tasks]}")
        if t.predecessors:
            print(f"  Predecessor Tasks (IDs): {[pt.id for pt in t.predecessors]}")

    print("\n--- Task with no predecessors (if any) ---")
    found_no_predecessor_task = False
    for t in project_schedule.tasks:
        if not t.predecessors:
            print(t)
            found_no_predecessor_task = True
            break
    if not found_no_predecessor_task:
        print("No task found with no predecessors.")


    print("\n--- Customization Types ---")
    for ct in project_schedule.customization_types[:5]:
        print(ct)

    print("\n--- Updating Customization Overview CSV ---")
    update_customization_overview_csv(customization_overview_csv_path)

    print("\n--- Exporting Task Flow to Mermaid Graph (Full Detail) ---")
    mermaid_output_path_full = Path("task_flow.mmd")
    export_tasks_to_mermaid_graph(project_schedule.tasks, mermaid_output_path_full, detail_level='full')

    print("\n--- Exporting Task Flow to Mermaid Graph (High-Level by Type) ---")
    mermaid_output_path_type = Path("task_flow_high_level.mmd")
    export_tasks_to_mermaid_graph(project_schedule.tasks, mermaid_output_path_type, detail_level='type')

    print("\n--- Exporting Task Flow to Mermaid Gantt Chart (Full Detail) ---")
    mermaid_output_path_gantt_full = Path("task_flow_gantt.mmd")
    export_tasks_to_mermaid_gantt(project_schedule.tasks, mermaid_output_path_gantt_full, detail_level='full')

    print("\n--- Exporting Task Flow to Mermaid Gantt Chart (High-Level by Type) ---")
    mermaid_output_path_gantt_type = Path("task_flow_gantt_high_level.mmd")
    export_tasks_to_mermaid_gantt(project_schedule.tasks, mermaid_output_path_gantt_type, detail_level='type')

    # Add resource vs duration plotting
    plot_output_path = Path("resource_vs_duration.png")
    plot_resource_vs_duration(
        task_csv_path=csv_path,
        customization_overview_csv_path=customization_overview_csv_path,
        max_resources=70,
        output_plot_path=plot_output_path
    )