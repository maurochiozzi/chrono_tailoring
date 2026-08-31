import pandas as pd
from pathlib import Path
from src import config
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
            print(f"Updated {config.rel_path(file_path)} with 'path' and 'status' columns.")

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
                'Predecessor IDs': ';'.join(str(p.id) for p in task.predecessors),
                'Variant Name': getattr(task, 'variant_name', ''),
                'Is Structural Critical (CPM)': getattr(task, 'is_structural_critical', False),
                'Is Resource Critical (CCPM)': getattr(task, 'is_resource_critical', False),
                'Slack (min)': getattr(task, 'slack', 0),
            }
            
            # [Req: RF-14.3] — Merged drawing tasks span multiple milestones; leave Milestone ID blank
            if task.type.strategy == "merged":
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
        print(f"Successfully exported {len(schedule.tasks)} tasks to {config.rel_path(Path(file_path))}")

    except Exception as e:
        print(f"An error occurred while exporting tasks to {file_path}: {e}")


def _export_path_csv(tasks, file_path: str, label: str):
    """Helper to export a list of tasks to a critical-path CSV."""
    data = []
    for task in tasks:
        data.append({
            'Task ID': task.id,
            'Part Number': task.part_number,
            'Task Name': task.name,
            'Task Type': task.type.description,
            'Duration (min)': task.duration_minutes,
            'Start Date': task.init_date.strftime('%Y-%m-%d %H:%M') if task.init_date else '',
            'End Date': task.end_date.strftime('%Y-%m-%d %H:%M') if task.end_date else '',
            'Predecessor IDs': ';'.join(str(p.id) for p in task.predecessors),
        })
    df = pd.DataFrame(data)
    df.to_csv(file_path, index=False, encoding='utf-8-sig')
    print(f"{label}: {len(tasks)} tasks -> {config.rel_path(Path(file_path))}")


# [Req: RF-12.6] — Exports both Structural Critical Path (CPM) and Resource Critical Chain (CCPM)
def export_critical_path_csv(schedule: ProjectSchedule, file_path: str):
    """Exports both structural critical path and resource critical chain CSVs.

    Args:
        schedule (ProjectSchedule): The fully computed project schedule.
        file_path (str): The base output file path (used for structural path).
    """
    try:
        from src.schedule.engine import compute_structural_critical_path, compute_resource_critical_chain

        struct_path = compute_structural_critical_path(schedule.tasks)
        _export_path_csv(struct_path, file_path, "Structural Critical Path (CPM)")

        res_chain = compute_resource_critical_chain(schedule.tasks)
        res_file = file_path.replace('critical_path', 'critical_chain')
        _export_path_csv(res_chain, res_file, "Resource Critical Chain (CCPM)")

    except Exception as e:
        print(f"An error occurred while exporting critical path to {file_path}: {e}")
