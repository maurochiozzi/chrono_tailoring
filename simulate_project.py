import sys
from pathlib import Path
from src import config
from src.schedule.project import ProjectSchedule
from src.export.csv_export import update_customization_overview_csv, export_tasks_to_csv
from src.export.plot import plot_resource_vs_duration
from src.export.mermaid import export_tasks_to_mermaid_graph, export_tasks_to_mermaid_gantt
from src.export.gantt_interactive import export_interactive_gantt
from src.schedule.loader import load_project_requirements

def main():
    print("--- Starting Chrono Tailoring Project Simulation ---")

    # Update customization overview matching input structure
    update_customization_overview_csv(config.CUSTOMIZATION_OVERVIEW_CSV_PATH)

    # Read project requirements to get num_resources setting
    pr_settings, _ = load_project_requirements(config.PROJECT_REQUIREMENTS_PATH)
    num_resources_to_use = pr_settings.get('num_resources', 1)

    if config.DEBUG:
        print(f"\nInitializing ProjectSchedule with {num_resources_to_use} resource(s)...")

    # Generate Project Schedule
    schedule = ProjectSchedule(
        project_requirements_path=config.PROJECT_REQUIREMENTS_PATH,
        num_resources=num_resources_to_use,
        customization_overview_csv_path=config.CUSTOMIZATION_OVERVIEW_CSV_PATH,
        holidays_path=config.HOLIDAYS_PATH
    )

    if not config.OUTPUT_DIR.exists():
        config.OUTPUT_DIR.mkdir(parents=True)
        if config.DEBUG:
            print(f"Created output directory: {config.OUTPUT_DIR}")

    if config.DEBUG:
        print("\n--- Final Project Schedule Summary ---")
        print(schedule)

    # 1. Export standard task data to CSV
    export_csv_path = config.OUTPUT_DIR / "exported_tasks.csv"
    if config.DEBUG:
        print(f"\nExporting tasks to CSV: {export_csv_path}")
    export_tasks_to_csv(schedule, str(export_csv_path))

    # 2. Analyze resource bottleneck limits (calculates curves and exports plot map)
    print("\n--- Analyzing Resource Constraints ---")
    plot_resource_vs_duration(
        base_schedule=schedule,
        max_resources=10, 
        min_resources=1,
        output_plot_path=config.OUTPUT_DIR / "resource_vs_duration.png"
    )

    # 3. Export detailed Mermaid flow graph
    print("\n--- Generating Mermaid Flow Graphs ---")
    detailed_graph_path = config.OUTPUT_DIR / "detailed_task_graph.mmd"
    export_tasks_to_mermaid_graph(
        schedule.milestones, 
        output_file_path=detailed_graph_path, 
        detail_level='full'
    )
    
    # 4. Generate Gantt charts
    detailed_gantt_path = config.OUTPUT_DIR / "detailed_task_gantt.mmd"
    export_tasks_to_mermaid_gantt(
        schedule.milestones,
        output_file_path=detailed_gantt_path,
        detail_level='full'
    )
    type_gantt_path = config.OUTPUT_DIR / "type_overview_gantt.mmd"
    export_tasks_to_mermaid_gantt(
        schedule.milestones,
        output_file_path=type_gantt_path,
        detail_level='type'
    )
    summary_gantt_path = config.OUTPUT_DIR / "milestone_summary_gantt.mmd"
    export_tasks_to_mermaid_gantt(
        schedule.milestones,
        output_file_path=summary_gantt_path,
        detail_level='milestone_type_summary'
    )

    # 5. Export interactive HTML Gantt chart
    gantt_html_path = config.OUTPUT_DIR / "gantt_interactive.html"
    milestone_name_map = {m.milestone_id: m.name for m in schedule.milestones}
    export_interactive_gantt(
        schedule.tasks,
        output_path=gantt_html_path,
        milestone_name_map=milestone_name_map,
        total_resources=num_resources_to_use,
        project_requirements_path=config.PROJECT_REQUIREMENTS_PATH,
        holidays=schedule.holidays,
    )

    # 6. Export trace log
    trace_log_path = config.OUTPUT_DIR / "transformation_log.json"
    if config.DEBUG:
        print(f"Exporting trace log to JSON: {trace_log_path}")
    import json
    with open(trace_log_path, "w", encoding="utf-8") as f:
        json.dump(schedule.transformation_log, f, indent=2, ensure_ascii=False)

    print("\n--- Simulation Complete ---")

if __name__ == "__main__":
    main()
