import os
from contextlib import redirect_stdout
from pathlib import Path
from typing import Optional
from datetime import datetime
import copy
import io
import contextlib

from src.schedule.project import ProjectSchedule
from src.schedule.loader import load_project_requirements
from src.config import DEBUG

    # [Req: RF-15.5] — Generate resource vs. duration scatter plot with matplotlib
try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    print("Warning: Matplotlib not found. Plotting will be skipped. Install with 'pip install matplotlib'.")
    MATPLOTLIB_AVAILABLE = False

# [Req: RF-15, RF-15.1, RF-15.2, RF-15.3, RF-15.4, RF-15.5, RF-15.6] — Resource sensitivity analysis: simulates schedule across resource counts
def plot_resource_vs_duration(
    base_schedule: ProjectSchedule,
    min_resources: int = 1,
    max_resources: int = 10,
    output_plot_path: Optional[Path] = None
):
    """Runs scheduling for multiple resource counts, collects total durations, and plots the results.

    Args:
        base_schedule (ProjectSchedule): The project schedule configuration.
        min_resources (int, optional): The minimum resources to simulate. Defaults to 1.
        max_resources (int, optional): The maximum resources to simulate. Defaults to 10.
        output_plot_path (Optional[Path], optional): Where to save the generated scatter plot. Defaults to None.
    """
    num_resources_list = []
    total_duration_minutes_list = []
    resource_duration_data = [] # For graceful degradation

    if DEBUG:
        print(f"\n--- Analyzing Resource vs. Duration ({min_resources} to {max_resources} Resources) ---")
    
    # Create base schedule once outside the loop to avoid severe repetitive I/O
    # [Req: RF-15.2, RF-15.3] — Reuse the base schedule object; suppress stdout for each simulation pass
    test_schedule = copy.deepcopy(base_schedule)
    # Read settings (start date, working hours) from project_config.json
    pr_settings = {}
    if base_schedule.project_requirements_path:
        pr_settings, _ = load_project_requirements(base_schedule.project_requirements_path)
    working_start_hour = int(pr_settings.get('working_start_hour', 8))
    working_end_hour = int(pr_settings.get('working_end_hour', 16))
    if 'project_start_date' in pr_settings:
        project_start_date = datetime.strptime(pr_settings['project_start_date'], '%Y-%m-%d')
    else:
        project_start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    from src.schedule.engine import calculate_task_dates
    # [Req: RF-15.1] — Iterate over the configured resource range
    for num_res in range(min_resources, max_resources + 1):
        # [Req: RF-15.3] — Suppress all internal output during the loop iteration
        with contextlib.redirect_stdout(io.StringIO()):
            test_schedule.num_resources = num_res
            for task in test_schedule.tasks:
                task.init_date = None
                task.end_date = None
            calculate_task_dates(
                test_schedule.tasks, project_start_date, test_schedule.holidays, num_res,
                working_start_hour, working_end_hour
            )

        tasks_with_dates = [t for t in test_schedule.tasks if t.init_date and t.end_date]
        # [Req: RF-15.4] — Total duration = max(end_date) - min(init_date) in minutes
        if tasks_with_dates:
            total_duration_minutes = int((max(t.end_date for t in tasks_with_dates) - min(t.init_date for t in tasks_with_dates)).total_seconds() / 60)
            num_resources_list.append(num_res)
            total_duration_minutes_list.append(total_duration_minutes)
            resource_duration_data.append({'resources': num_res, 'duration_minutes': total_duration_minutes})
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
