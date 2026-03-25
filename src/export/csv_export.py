import pandas as pd
from pathlib import Path
from src.config import INPUT_DIR, DEBUG
from src.schedule.project import ProjectSchedule

# [Req: RF-24, RF-24.1, RF-24.2, RF-24.3] — Pre-flight check: validates customisation CSV files exist and updates overview status
def update_customization_overview_csv(file_path: Path):
    """Reads customization_overview.csv, adds 'path' and 'status' columns,
    and writes the updated DataFrame back to the CSV.

    Args:
        file_path (Path): Path to the customization_overview.csv file.
    """
    try:
        df = pd.read_csv(file_path, delimiter=';')
        
        # Drop any unnamed columns that pandas might create (e.g., from trailing delimiters)
        # [Req: RF-24.3] — Discard phantom Unnamed:* columns created by pandas when CSV has trailing delimiters
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        
        # Add 'path' column
        # [Req: RF-24.1] — Add resolved file path for each customisation type
        df['path'] = df['customization_type'].apply(lambda name: f"input/customization_{name}.csv")
        
        # [Req: RF-24.1, RF-24.2] — Set status='ok' if file exists, 'nok' otherwise; rewrite CSV
        df['status'] = df['customization_type'].apply(lambda name: 'ok' if (INPUT_DIR / f"customization_{name}.csv").exists() else 'nok')
        
        # Write the updated DataFrame back to the CSV
        df.to_csv(file_path, sep=';', index=False)
        if DEBUG:
            print(f"Updated {file_path} with 'path' and 'status' columns.")

    except FileNotFoundError:
        print(f"Error: Customization overview file not found at {file_path}")
    except Exception as e:
        print(f"An error occurred while updating {file_path}: {e}")


# [Req: RF-14, RF-14.1, RF-14.2, RF-14.3, RF-14.4] — Exports final schedule to CSV including dynamic customisation columns
def export_tasks_to_csv(schedule: ProjectSchedule, file_path: str):
    """Exports all tasks with their related information to a CSV file.

    Args:
        schedule (ProjectSchedule): The fully computed project schedule to export.
        file_path (str): The output file path.
    """
    try:
        # [Req: RF-14.2] — Discover all customisation keys dynamically across all tasks
        all_customization_keys = set()
        for task in schedule.tasks:
            if hasattr(task, 'variant_customizations') and task.variant_customizations:
                all_customization_keys.update(task.variant_customizations.keys())
        
        data = []
        for task in schedule.tasks:
            # [Req: RF-14.1] — Fixed columns; [RF-14.4] dates formatted as YYYY-MM-DD HH:MM
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
            
            # [Req: RF-14.3] — Consolidated drawing tasks span multiple milestones; leave Milestone ID blank
            if task.type.strategy == "consolidated":
                row['Milestone ID'] = '' 
            else:
                row['Milestone ID'] = getattr(task, 'milestone_id', '')
            
            # [Req: RF-14.2] — Dynamic per-task customisation columns
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
