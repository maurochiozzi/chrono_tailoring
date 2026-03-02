import pandas as pd
from pathlib import Path
from src.config import INPUT_DIR, DEBUG
from src.schedule.project import ProjectSchedule

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
        df['path'] = df['customization_type'].apply(lambda name: f"input/customization_{name}.csv")
        
        # Add 'status' column
        df['status'] = df['customization_type'].apply(lambda name: 'ok' if (INPUT_DIR / f"customization_{name}.csv").exists() else 'nok')
        
        # Write the updated DataFrame back to the CSV
        df.to_csv(file_path, sep=';', index=False)
        if DEBUG:
            print(f"Updated {file_path} with 'path' and 'status' columns.")

    except FileNotFoundError:
        print(f"Error: Customization overview file not found at {file_path}")
    except Exception as e:
        print(f"An error occurred while updating {file_path}: {e}")


def export_tasks_to_csv(schedule: ProjectSchedule, file_path: str):
    """
    Exports all tasks with their related information to a CSV file.
    """
    try:
        # Collect all unique customization keys first
        all_customization_keys = set()
        for task in schedule.tasks:
            if hasattr(task, 'variant_customizations') and task.variant_customizations:
                all_customization_keys.update(task.variant_customizations.keys())
        
        data = []
        for task in schedule.tasks:
            row = {
                'Task ID': task.id,
                'Part Number': task.part_number,
                'Task Name': task.name,
                'Task Type Description': task.type.description,
                'Task Type Strategy': task.type.strategy,
                'Duration (minutes)': task.duration_minutes,
                'Start Date': task.init_date.strftime('%Y-%m-%d %H:%M') if task.init_date else '',
                'End Date': task.end_date.strftime('%Y-%m-%d %H:%M') if task.end_date else '',
                'Predecessor IDs': ', '.join(str(p.id) for p in task.predecessors),
                'Successor IDs': ', '.join(str(s.id) for s in getattr(task, 'successors_tasks', [])),
                'Variant Name': getattr(task, 'variant_name', '')
            }
            
            # Add Milestone ID column
            if task.type.strategy == "consolidated":
                row['Milestone ID'] = '' 
            else:
                # Approximation of milestone logic 
                row['Milestone ID'] = getattr(task, 'milestone_id', '')
            
            # Add dynamic customization columns
            variant_customizations = getattr(task, 'variant_customizations', {})
            for key in all_customization_keys:
                row[f'Customization_{key}'] = variant_customizations.get(key, '')
            
            data.append(row)

        df = pd.DataFrame(data)
        df.to_csv(file_path, index=False)
        if DEBUG:
            print(f"Successfully exported {len(schedule.tasks)} tasks to {file_path}")

    except Exception as e:
        print(f"An error occurred while exporting tasks to {file_path}: {e}")
