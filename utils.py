# utils.py

import pandas as pd
import os
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta
from pathlib import Path
import builtins # Import builtins module

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
            print(f"Error exporting Mermaid Gantt chart to {output_file_path}: {e}") # Corrected this line
            
    return mermaid_syntax

def plot_resource_vs_duration(
    task_csv_path: Path,
    customization_overview_csv_path: Optional[Path] = None,
    max_resources: int = 10,
    output_plot_path: Optional[Path] = None,
    project_requirements_path: Optional[Path] = None,
    holidays_path: Optional[Path] = None
):
    """
    Runs scheduling for 1 to max_resources, collects total durations, and plots the results.
    """
    num_resources_list = []
    total_duration_minutes_list = []

    print(f"\n--- Analyzing Resource vs. Duration (1 to {max_resources} Resources) ---")
    
    for num_res in range(1, max_resources + 1):
        # Temporarily suppress print statements from ProjectSchedule and its helpers
        _original_print = builtins.print
        def _suppress_print(*args, **kwargs):
            pass
        builtins.print = _suppress_print

        temp_project_schedule = ProjectSchedule(
            task_csv_path=task_csv_path, # Pass the original task CSV path
            num_resources=num_res,
            customization_overview_csv_path=customization_overview_csv_path,
            project_requirements_path=project_requirements_path, # Ensure project requirements path is passed
            holidays_path=holidays_path # Pass holidays path
        )
        # Restore print
        builtins.print = _original_print



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
