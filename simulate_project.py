# simulate_project.py

from datetime import datetime
from pathlib import Path

import config
from config import DEBUG
from scheduler import ProjectSchedule
from utils import update_customization_overview_csv, export_tasks_to_mermaid_graph, \
                    export_tasks_to_mermaid_gantt, plot_resource_vs_duration

def simulate_project_schedule(num_resources: int = 2):
    print("--- Starting Project Schedule Simulation ---")

    # Define paths using config
    task_csv_path = config.TASK_CSV_PATH
    customization_overview_csv_path = config.CUSTOMIZATION_OVERVIEW_CSV_PATH
    project_requirements_path = config.PROJECT_REQUIREMENTS_PATH
    holidays_path = config.HOLIDAYS_PATH

    # Initialize ProjectSchedule
    project_schedule = ProjectSchedule(
        project_requirements_path, # Now a positional argument
        num_resources=num_resources,
        customization_overview_csv_path=customization_overview_csv_path,
        holidays_path=holidays_path,
        project_start_date=datetime.strptime(config.PROJECT_START_DATE_STR, '%Y-%m-%d')
    )

    if DEBUG:
        print(f"\n--- Project Schedule Summary ({num_resources} Resources) ---")
        print(project_schedule)

        print(f"\n--- Customization Types ---")
        for ct in project_schedule.customization_types:
            print(ct)

    print(f"\n--- Updating Customization Overview CSV ---")
    update_customization_overview_csv(customization_overview_csv_path)

    # Create output directory if it doesn't exist
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Export to Mermaid Graph
    print(f"\n--- Exporting Task Flow to Mermaid Graph (Full Detail) ---")
    export_tasks_to_mermaid_graph(project_schedule.milestones, config.OUTPUT_DIR / "task_flow.mmd", detail_level='full')

    print(f"\n--- Exporting Task Flow to Mermaid Graph (High-Level by Type) ---")
    export_tasks_to_mermaid_graph(project_schedule.milestones, config.OUTPUT_DIR / "task_flow_high_level.mmd", detail_level='type')

    print(f"\n--- Exporting Task Flow to Mermaid Graph (Milestone Level) ---")
    export_tasks_to_mermaid_graph(project_schedule.milestones, config.OUTPUT_DIR / "task_flow_milestone_level.mmd", detail_level='milestone')

    # Export to Mermaid Gantt Chart
    print(f"\n--- Exporting Task Flow to Mermaid Gantt Chart (Full Detail) ---")
    export_tasks_to_mermaid_gantt(project_schedule.milestones, config.OUTPUT_DIR / "task_flow_gantt.mmd", detail_level='full')

    print(f"\n--- Exporting Task Flow to Mermaid Gantt Chart (High-Level by Type) ---")
    export_tasks_to_mermaid_gantt(project_schedule.milestones, config.OUTPUT_DIR / "task_flow_gantt_high_level.mmd", detail_level='type')

    print(f"\n--- Exporting Task Flow to Mermaid Gantt Chart (Milestone Type Summary) ---")
    export_tasks_to_mermaid_gantt(project_schedule.milestones, config.OUTPUT_DIR / "task_flow_gantt_milestone_type_summary.mmd", detail_level='milestone_type_summary')

    # Plot resource vs duration
    plot_resource_vs_duration(
        task_csv_path=task_csv_path,
        customization_overview_csv_path=customization_overview_csv_path,
        min_resources=5,
        max_resources=15,
        output_plot_path=config.OUTPUT_DIR / "resource_vs_duration.png",
        project_requirements_path=project_requirements_path,
        holidays_path=holidays_path
    )

    print(f"\n--- Exporting all tasks to CSV ---")
    project_schedule.export_tasks_to_csv(config.OUTPUT_DIR / "exported_tasks.csv")

    print("\n--- Project Schedule Simulation Complete ---")

if __name__ == "__main__":
    simulate_project_schedule(num_resources=1)
