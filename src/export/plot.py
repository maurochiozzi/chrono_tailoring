import os
from contextlib import redirect_stdout
from pathlib import Path
from typing import Optional
from datetime import datetime

from src.schedule.project import ProjectSchedule
from src.schedule.loader import load_project_requirements
from src.config import DEBUG

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    print("Warning: Matplotlib not found. Plotting will be skipped. Install with 'pip install matplotlib'.")
    MATPLOTLIB_AVAILABLE = False

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
            project_requirements_path, 
            num_resources=min_resources,
            customization_overview_csv_path=customization_overview_csv_path,
            holidays_path=holidays_path 
        )
    # Read settings (start date, working hours) from project_requirements.txt
    pr_settings = {}
    if project_requirements_path:
        pr_settings, _ = load_project_requirements(project_requirements_path)
    working_start_hour = int(pr_settings.get('working_start_hour', 8))
    working_end_hour = int(pr_settings.get('working_end_hour', 16))
    if 'project_start_date' in pr_settings:
        project_start_date = datetime.strptime(pr_settings['project_start_date'], '%Y-%m-%d')
    else:
        project_start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    from src.schedule.engine import calculate_task_dates
    for num_res in range(min_resources, max_resources + 1):
        with open(os.devnull, 'w') as f, redirect_stdout(f):
            base_schedule.num_resources = num_res
            for task in base_schedule.tasks:
                task.init_date = None
                task.end_date = None
            calculate_task_dates(
                base_schedule.tasks, project_start_date, base_schedule.holidays, num_res,
                working_start_hour, working_end_hour
            )

        total_duration = base_schedule.get_total_duration()
        if total_duration:
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
            for res, dur in zip(num_resources_list, total_duration_minutes_list):
                print(f"  {res}: {dur:.2f}")
