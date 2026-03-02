# utils.py

import pandas as pd
import os
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta
from pathlib import Path
import builtins # Import builtins module
from contextlib import redirect_stdout
from config import DEBUG

from model import Task
from scheduler import ProjectSchedule # Import ProjectSchedule for plot_resource_vs_duration

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    print("Warning: Matplotlib not found. Plotting will be skipped. Install with 'pip install matplotlib'.")
    MATPLOTLIB_AVAILABLE = False

def update_customization_overview_csv(file_path: Path):
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
        df['status'] = df['path'].apply(lambda p: 'ok' if os.path.exists(p) else 'nok')
        
        # Write the updated DataFrame back to the CSV
        df.to_csv(file_path, sep=';', index=False)
        if DEBUG:
            print(f"Updated {file_path} with 'path' and 'status' columns.")

    except FileNotFoundError:
        print(f"Error: Customization overview file not found at {file_path}")
    except Exception as e:
        print(f"An error occurred while updating {file_path}: {e}")

def export_tasks_to_mermaid_graph(milestones: List[ProjectMilestone], output_file_path: Optional[Path] = None, detail_level: str = 'full') -> str:
    """
    Generates a Mermaid flowchart (graph TD) representation of tasks, grouped by milestone.
    Can generate a detailed graph of individual tasks or a high-level graph based on task types.
    """
    mermaid_lines = ["graph TD"]
    all_tasks = [task for milestone in milestones for task in milestone.tasks]

    def sanitize_id(text: str) -> str:
        return text.replace(" ", "_").replace("-", "_").replace(".", "").lower()

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

        for milestone in milestones:
            mermaid_lines.append(f"    subgraph M_{milestone.milestone_id}[Milestone {milestone.milestone_id} - {milestone.name}]")
            
            # Define nodes with details and shapes for individual tasks within the milestone
            for task in milestone.tasks:
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
                mermaid_lines.append(f"        {node_definition}")

                # Add style directive for the node
                color_style = task_type_colors.get(task.task_type.description, 'fill:#CCC') # Default light gray
                node_styles.append(f"        style {task.id} {color_style}")
            mermaid_lines.append("    end") # End subgraph
        
        # Define edges (dependencies) for individual tasks across all tasks
        for task in all_tasks:
            for successor_task in task.successors_tasks:
                # Only draw edge if successor is also in a known milestone task list
                # This prevents drawing edges to tasks that might have been filtered out or not yet processed.
                if any(s_task.id == successor_task.id for m in milestones for s_task in m.tasks):
                    mermaid_lines.append(f"    {task.id} --> {successor_task.id}")
        
        # Append node styles after all nodes and edges
        mermaid_lines.extend(node_styles)

    elif detail_level == 'type':
        def sanitize_id(text: str) -> str:
            return text.replace(" ", "_").replace("-", "_").replace(".", "").lower()

        for milestone in milestones:
            mermaid_lines.append(f"    subgraph M_{milestone.milestone_id}[Milestone {milestone.milestone_id} - {milestone.name} (Types)]")
            
            unique_task_types_in_milestone = set()
            type_dependencies_in_milestone = set() # Stores (source_type_desc, target_type_desc)

            for task in milestone.tasks:
                source_type_desc = task.task_type.description
                unique_task_types_in_milestone.add(source_type_desc)

                for successor_task in task.successors_tasks:
                    # Check if successor task also belongs to the current milestone
                    if successor_task.milestone_id == milestone.milestone_id:
                        target_type_desc = successor_task.task_type.description
                        unique_task_types_in_milestone.add(target_type_desc)
                        type_dependencies_in_milestone.add((source_type_desc, target_type_desc))

            # Define nodes for each unique task type description within this milestone
            for type_desc in sorted(list(unique_task_types_in_milestone)):
                sanitized_id = sanitize_id(type_desc)
                # Prefix with milestone ID to ensure uniqueness across milestones if types repeat
                mermaid_lines.append(f"        {sanitized_id}_{milestone.milestone_id}[{type_desc}]")

            # Define edges between task types within this milestone
            for source_type_desc, target_type_desc in sorted(list(type_dependencies_in_milestone)):
                sanitized_source_id = sanitize_id(source_type_desc)
                sanitized_target_id = sanitize_id(target_type_desc)
                mermaid_lines.append(f"        {sanitized_source_id}_{milestone.milestone_id} --> {sanitized_target_id}_{milestone.milestone_id}")
            mermaid_lines.append("    end") # End subgraph
        
        # Add global dependencies between milestones (if a type in one milestone depends on a type in another)
        # This part requires iterating through all_tasks to find cross-milestone type dependencies
        global_type_dependencies = set()
        for task in all_tasks:
            for successor_task in task.successors_tasks:
                if task.milestone_id != successor_task.milestone_id:
                    source_type_desc = task.task_type.description
                    target_type_desc = successor_task.task_type.description
                    global_type_dependencies.add((task.milestone_id, source_type_desc, successor_task.milestone_id, target_type_desc))

        for source_mid, source_td, target_mid, target_td in sorted(list(global_type_dependencies)):
            sanitized_source_id_node = sanitize_id(source_td) + f"_{source_mid}"
            sanitized_target_id_node = sanitize_id(target_td) + f"_{target_mid}"
            mermaid_lines.append(f"    {sanitized_source_id_node} --> {sanitized_target_id_node}")

    elif detail_level == 'milestone':
        milestone_dependencies = set()
        # Create a mapping from task ID to its milestone ID for efficient lookup
        task_to_milestone_map = {task.id: milestone.milestone_id for milestone in milestones for task in milestone.tasks}

        for milestone in milestones:
            # Add node for the milestone itself
            sanitized_milestone_id = sanitize_id(str(milestone.milestone_id))
            mermaid_lines.append(f"    {sanitized_milestone_id}[Milestone {milestone.milestone_id} - {milestone.name}]")

            for task in milestone.tasks:
                for successor_task in task.successors_tasks:
                    successor_milestone_id = task_to_milestone_map.get(successor_task.id)
                    if successor_milestone_id and successor_milestone_id != milestone.milestone_id:
                        milestone_dependencies.add((milestone.milestone_id, successor_milestone_id))
        
        # Add edges between milestones
        for source_milestone_id, target_milestone_id in sorted(list(milestone_dependencies), key=lambda x: (x[0], x[1])):
            sanitized_source_milestone_id = sanitize_id(str(source_milestone_id))
            sanitized_target_milestone_id = sanitize_id(str(target_milestone_id))
            mermaid_lines.append(f"    {sanitized_source_milestone_id} --> {sanitized_target_milestone_id}")

    else:
        raise ValueError(f"Unknown detail_level: {detail_level}. Expected 'full', 'type', or 'milestone'.")
            
    mermaid_syntax = "\n".join(mermaid_lines)

    if output_file_path:
        try:
            output_file_path.write_text(mermaid_syntax)
            if DEBUG:
                print(f"Mermaid graph exported to: {output_file_path}")
        except Exception as e:
            print(f"Error exporting Mermaid graph to {output_file_path}: {e}")
            
    return mermaid_syntax

def export_tasks_to_mermaid_gantt(milestones: List[ProjectMilestone], output_file_path: Optional[Path] = None, detail_level: str = 'full') -> str:
    """
    Generates a Mermaid Gantt chart representation of tasks, grouped by milestone.
    Can generate a detailed chart of individual tasks or a high-level chart based on task types.
    """
    mermaid_lines = [
        "gantt",
        "    dateFormat  YYYY-MM-DD",
        "    axisFormat %d-%m",
        "    title       Task Schedule Overview",
        "    excludes    weekends"
    ]

    def sanitize_id(text: str) -> str:
        return text.replace(" ", "_").replace("-", "_").replace(".", "").lower()

    # SECTION: Full Detail Gantt Chart
    if detail_level == 'full':
        for milestone in milestones:
            mermaid_lines.append(f"    section Milestone {milestone.milestone_id} - {milestone.name}")
            
            # Get current date for 'active' and 'done' status
            # Using a fixed date or project_start_date for consistent rendering if actual current date is not desired
            reference_date = datetime.now().date() 

            for task in milestone.tasks:
                init_date_str = task.init_date.strftime('%Y-%m-%d') if task.init_date else 'None'
                end_date_str = task.end_date.strftime('%Y-%m-%d') if task.end_date else 'None'
                
                task_duration_mermaid_format = ""
                if task.duration is not None:
                    total_minutes = task.duration
                    days = total_minutes // (8 * 60) # Assuming 8 working hours per day
                    hours = (total_minutes % (8 * 60)) // 60
                    minutes = total_minutes % 60
                    
                    if days > 0:
                        task_duration_mermaid_format += f"{days}d "
                    if hours > 0:
                        task_duration_mermaid_format += f"{hours}h "
                    if minutes > 0:
                        task_duration_mermaid_format += f"{minutes}m "
                    
                    if not task_duration_mermaid_format: # If duration is 0
                        task_duration_mermaid_format = "0d"
                    else:
                        task_duration_mermaid_format = task_duration_mermaid_format.strip()
                
                task_status = "" # No status prefixes
                task_duration_mermaid_format = "0d" if task.task_type.description == "milestone" else task_duration_mermaid_format # Milestones have 0d duration

                # Task label for the Gantt bar
                task_label_gantt = f"{task.name} ({task.part_number})"

                if task.init_date and task.end_date:
                    mermaid_lines.append(f"    {task_label_gantt} :{task.id}, {init_date_str}, {end_date_str}")
                else:
                    mermaid_lines.append(f"    {task_label_gantt} :{task.id}, {init_date_str}, {task_duration_mermaid_format}")

    elif detail_level == 'type':
        # Aggregate all tasks from all milestones for type overview
        all_tasks = [task for milestone in milestones for task in milestone.tasks]
        mermaid_lines.append("    section Task Types Overview")
        type_date_spans = {} # {type_desc: {'min_init': datetime, 'max_end': datetime, 'total_duration': timedelta}}

        for task in all_tasks:
            type_desc = task.task_type.description
            if type_desc not in type_date_spans:
                type_date_spans[type_desc] = {
                    'min_init': task.init_date, 
                    'max_end': task.end_date, 
                    'total_duration': timedelta(minutes=0)
                }
            
            # Update min_init_date for the type
            if task.init_date and (type_date_spans[type_desc]['min_init'] is None or type_date_spans[type_desc]['min_init'] > task.init_date):
                type_date_spans[type_desc]['min_init'] = task.init_date
            
            # Update max_end_date for the type
            if task.end_date and (type_date_spans[type_desc]['max_end'] is None or type_date_spans[type_desc]['max_end'] < task.end_date):
                type_date_spans[type_desc]['max_end'] = task.end_date
            
            # Sum durations for the type overview
            type_date_spans[type_desc]['total_duration'] += timedelta(minutes=task.duration)
        
        for type_desc in sorted(type_date_spans.keys()):
            type_info = type_date_spans[type_desc]
            
            # Convert total_duration to human-readable format (e.g., "2d 20h")
            total_seconds = type_info['total_duration'].total_seconds()
            total_minutes = int(total_seconds / 60)
            
            duration_parts = []
            if total_minutes >= (8 * 60): # Full working days
                days = total_minutes // (8 * 60)
                duration_parts.append(f"{days}d")
                total_minutes %= (8 * 60)
            
            if total_minutes >= 60: # Hours
                hours = total_minutes // 60
                duration_parts.append(f"{hours}h")
                total_minutes %= 60
            
            if total_minutes > 0: # Remaining minutes
                duration_parts.append(f"{total_minutes}m")
            
            duration_display = " ".join(duration_parts) if duration_parts else "0m"

            min_init_str = type_info['min_init'].strftime('%Y-%m-%d') if type_info['min_init'] else 'None'
            max_end_str = type_info['max_end'].strftime('%Y-%m-%d') if type_info['max_end'] else 'None'

            # Type label: "Type Name (Duration)"
            if type_desc == "milestone":
                # For high-level type view, the milestone task itself is a type.
                # Just use the generic 'milestone' type_desc
                type_label = type_desc
                duration_mermaid_format = "0d" # Milestones have 0d duration
            else:
                type_label = f"{type_desc} ({duration_display})"
                duration_mermaid_format = f"{min_init_str}, {max_end_str}"
            
            # No task_status_prefix as per new requirements

            if type_info['min_init'] and type_info['max_end']:
                mermaid_lines.append(f"    {type_label} :{sanitize_id(type_desc)}, {duration_mermaid_format}")
            else:
                # Fallback, similar to the example for un-dated tasks, specify an ID and duration
                mermaid_lines.append(f"    {type_label} :{sanitize_id(type_desc)}, {duration_mermaid_format}")
    
    elif detail_level == 'milestone_type_summary':
        for milestone in milestones:
            mermaid_lines.append(f"    section {milestone.name}")

            # Separate tasks into those to be summarized and those to be listed individually
            tasks_to_summarize = []
            individual_tasks = []
            
            milestone_id_as_str = str(milestone.milestone_id) # The original numerical ID for comparison
            milestone_name_str = str(milestone.name) # The user-friendly name, e.g., "70015"

            for task in milestone.tasks:
                # Check for tasks whose ID or name matches the milestone name
                # This logic assumes the "70000 drawing task" means a task whose part_number or id is the milestone ID
                # and its name might contain the milestone name.
                # However, the clearest interpretation is: if a task's part_number (which I'm now using as milestone name)
                # is the same as the milestone's name, or if its id is the milestone's id.
                
                # Check if task is the special 'milestone' task itself, or if its part_number is the milestone's name
                if task.task_type.description == "milestone" or str(task.part_number) == milestone_name_str:
                    individual_tasks.append(task)
                else:
                    tasks_to_summarize.append(task)

            type_date_spans_in_milestone = {}

            # Aggregate tasks_to_summarize
            for task in tasks_to_summarize:
                type_desc = task.task_type.description
                if type_desc not in type_date_spans_in_milestone:
                    type_date_spans_in_milestone[type_desc] = {
                        'min_init': task.init_date,
                        'max_end': task.end_date,
                        'total_duration': timedelta(minutes=0)
                    }
                if task.init_date and (type_date_spans_in_milestone[type_desc]['min_init'] is None or type_date_spans_in_milestone[type_desc]['min_init'] > task.init_date):
                    type_date_spans_in_milestone[type_desc]['min_init'] = task.init_date
                if task.end_date and (type_date_spans_in_milestone[type_desc]['max_end'] is None or type_date_spans_in_milestone[type_desc]['max_end'] < task.end_date):
                    type_date_spans_in_milestone[type_desc]['max_end'] = task.end_date
                type_date_spans_in_milestone[type_desc]['total_duration'] += timedelta(minutes=task.duration)

            # Generate Gantt lines for summarized tasks
            for type_desc in sorted(type_date_spans_in_milestone.keys()):
                type_info = type_date_spans_in_milestone[type_desc]
                
                total_seconds = type_info['total_duration'].total_seconds()
                total_minutes = int(total_seconds / 60)
                
                duration_parts = []
                if total_minutes >= (8 * 60): days = total_minutes // (8 * 60); duration_parts.append(f"{days}d"); total_minutes %= (8 * 60)
                if total_minutes >= 60: hours = total_minutes // 60; duration_parts.append(f"{hours}h"); total_minutes %= 60
                if total_minutes > 0: duration_parts.append(f"{total_minutes}m")
                duration_display = " ".join(duration_parts) if duration_parts else "0m"

                min_init_str = type_info['min_init'].strftime('%Y-%m-%d') if type_info['min_init'] else 'None'
                max_end_str = type_info['max_end'].strftime('%Y-%m-%d') if type_info['max_end'] else 'None'

                type_label = f"{type_desc} {milestone.name} ({duration_display})" # Use milestone.name
                duration_mermaid_format = f"{min_init_str}, {max_end_str}"
                mermaid_task_id = f"{sanitize_id(type_desc)}_{milestone.name}" # Use milestone.name
                
                if type_info['min_init'] and type_info['max_end']:
                    mermaid_lines.append(f"    {type_label} :{mermaid_task_id}, {duration_mermaid_format}")
                else:
                    mermaid_lines.append(f"    {type_label} :{mermaid_task_id}, {duration_mermaid_format}")

            # Generate Gantt lines for individual tasks (those not summarized)
            for task in individual_tasks:
                init_date_str = task.init_date.strftime('%Y-%m-%d') if task.init_date else 'None'
                end_date_str = task.end_date.strftime('%Y-%m-%d') if task.end_date else 'None'
                
                task_duration_mermaid_format = ""
                if task.duration is not None:
                    total_minutes = task.duration
                    days = total_minutes // (8 * 60)
                    hours = (total_minutes % (8 * 60)) // 60
                    minutes = total_minutes % 60
                    
                    if days > 0: task_duration_mermaid_format += f"{days}d "
                    if hours > 0: task_duration_mermaid_format += f"{hours}h "
                    if minutes > 0: task_duration_mermaid_format += f"{minutes}m "
                    task_duration_mermaid_format = task_duration_mermaid_format.strip() if task_duration_mermaid_format else "0d"

                if task.task_type.description == "milestone":
                    type_label = str(milestone.name)
                    duration_mermaid_format = "0d"
                    mermaid_task_id = "milestone"
                else:
                    # For individual tasks, use task.name and task.id for unique identification
                    # If task.name is "storage_cabinte", replace it with milestone_name and task_type
                    if task.name == "storage_cabinet":
                        type_label = f"{milestone.name} {task.task_type.description} ({task_duration_mermaid_format})"
                    else:
                        type_label = f"{task.name} ({task_duration_mermaid_format})" # Include duration in label
                    
                    duration_mermaid_format = f"{init_date_str}, {end_date_str}"
                    mermaid_task_id = str(task.id) # Use the task's unique ID
                    
                if task.init_date and task.end_date:
                    mermaid_lines.append(f"    {type_label} :{mermaid_task_id}, {duration_mermaid_format}")
                else:
                    mermaid_lines.append(f"    {type_label} :{mermaid_task_id}, {duration_mermaid_format}")


    else:
        raise ValueError(f"Unknown detail_level: {detail_level}. Expected 'full' or 'type'.")
            
    mermaid_syntax = "\n".join(mermaid_lines)

    if output_file_path:
        try:
            output_file_path.write_text(mermaid_syntax)
            if DEBUG:
                print(f"Mermaid Gantt chart exported to: {output_file_path}")
        except Exception as e:
            print(f"Error exporting Mermaid Gantt chart to {output_file_path}: {e}") # Corrected this line
            
    return mermaid_syntax

def plot_resource_vs_duration(
    task_csv_path: Path,
    customization_overview_csv_path: Optional[Path] = None,
    max_resources: int = 10,
    min_resources: int = 1,
    output_plot_path: Optional[Path] = None,
    project_requirements_path: Optional[Path] = None,
    holidays_path: Optional[Path] = None
):
    """
    Runs scheduling for 1 to max_resources, collects total durations, and plots the results.
    """
    num_resources_list = []
    total_duration_minutes_list = []

    if DEBUG:
        print(f"\n--- Analyzing Resource vs. Duration ({min_resources} to {max_resources} Resources) ---")
    
    # Create base schedule once outside the loop to avoid severe repetitive I/O
    with open(os.devnull, 'w') as f, redirect_stdout(f):
        base_schedule = ProjectSchedule(
            project_requirements_path, # Now a positional argument
            num_resources=min_resources,
            customization_overview_csv_path=customization_overview_csv_path,
            holidays_path=holidays_path # Pass holidays path
        )
        # Import datetime and config inside function or ensure they are available at module level
        import config
        from datetime import datetime
        project_start_date = datetime.strptime(config.PROJECT_START_DATE_STR, '%Y-%m-%d')

    for num_res in range(min_resources, max_resources + 1):
        # Temporarily suppress print statements from ProjectSchedule and its helpers
        with open(os.devnull, 'w') as f, redirect_stdout(f):
            base_schedule.num_resources = num_res
            for task in base_schedule.tasks:
                task.init_date = None
                task.end_date = None
            base_schedule._calculate_task_dates(project_start_date)

        total_duration = base_schedule.get_total_duration()
        if total_duration:
            # Convert timedelta to total minutes for plotting
            total_duration_minutes = total_duration.total_seconds() / 60
            num_resources_list.append(num_res)
            total_duration_minutes_list.append(total_duration_minutes)
            if DEBUG:
                print(f"  Resources: {num_res}, Total Duration: {total_duration_minutes:.2f} minutes")
        else:
            if DEBUG:
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
            if DEBUG:
                print(f"Plot saved to: {output_plot_path}")
        else:
            plt.show()
    else:
        if DEBUG:
            print("\nRaw Data (Number of Resources, Total Duration in Minutes):")
            for i in range(len(num_resources_list)):
                print(f"{num_resources_list[i]}, {total_duration_minutes_list[i]:.2f}")
