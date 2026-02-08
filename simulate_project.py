from datetime import datetime
from pathlib import Path
from task import ProjectSchedule, update_customization_overview_csv, export_tasks_to_mermaid_graph, export_tasks_to_mermaid_gantt, plot_resource_vs_duration
import sys

# Define file paths
csv_path = '/Users/mchiozzi/sdev/personal/chrono_tailoring/deliverable_structure.csv'
customization_overview_csv_path = '/Users/mchiozzi/sdev/personal/chrono_tailoring/customization_overview.csv'
project_requirements_path = '/Users/mchiozzi/sdev/personal/chrono_tailoring/project_requirements.txt'

def simulate_project_schedule():
    print("--- Starting Project Schedule Simulation ---")

    # Create ProjectSchedule instance
    num_resources_for_project = 2
    project_schedule = ProjectSchedule(
        task_csv_path=csv_path,
        num_resources=num_resources_for_project,
        customization_overview_csv_path=customization_overview_csv_path,
        project_requirements_path=project_requirements_path
    )

    print(f"\n--- Project Schedule Summary ({num_resources_for_project} Resources) ---")
    print(project_schedule)


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
        max_resources=2,
        output_plot_path=plot_output_path,
        project_requirements_path=project_requirements_path
    )

    print("\n--- Exporting all tasks to CSV ---")
    project_schedule.export_tasks_to_csv('exported_tasks.csv')

    print("\n--- Project Schedule Simulation Complete ---")

if __name__ == "__main__":
    try:
        simulate_project_schedule()
    except Exception as e:
        print(f"An error occurred during simulation: {e}")
        sys.exit(1)