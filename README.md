# Chrono Tailoring 🕒

Chrono Tailoring is a sophisticated toolkit for dynamic project scheduling, milestone structuring, and visualization for complex manufacturing or engineering projects. It specialized in modeling variant-heavy deliverable structures with resource constraints.

## Features

- **Automated Scheduling**: Applies resource constraints and calculates initiation, end, and duration times dynamically across configured working shifts.
- **Recursive Task Duplication**: Support for `extra_args` variants that clone entire predecessor chains with unique suffixes (e.g., `60010.1`).
- **Optional Drawing Merging**: Run with `--merge-drawings` to merge variant drawing tasks of the same base part into unified efforts while preserving all dependency links.
- **Customization Overlays**: Hierarchical duration overrides (Milestone vs. Variant) based on external CSV data with recursive dependency bridging over 0-duration tasks.
- **Unbranching Critical Path**: Calculates the exact longest path through the task DAG from project start to final milestone, exported to dedicated CSV and highlighted in dashboards.
- **Rich Visualizations**:
  - **Dual-View Interactive Dashboard (HTML)**:
    - **`📅 Gantt View`**: Dynamic grouping (Part, Milestone, Resource, Task), sorting (A→Z, Date), search bar with auto-scroll, live resource utilization graph, and **`⚠️ Critical Path`** highlighting.
    - **`🔀 Flow View`**: Interactive, pan/zoom DAG network graph with shape/color semantics and one-click Critical Path arrow highlighting.
  - Mermaid diagrams (Flowcharts and Gantts) for different levels of detail.
  - Resource sensitivity plots (Matplotlib).
- **Audit Logging**: Comprehensive JSON/Log trail of any structural mutations or duration adjustments.

---

## How It Works

The system follows a multi-stage pipeline to transform a static template into a resource-constrained schedule:

1.  **Loading**: Reads `deliverable_structure.csv` and searches for `project_config.json`.
2.  **Instantiation**: Creates tasks for each milestone. If `extra_args` are present, it performs a **recursive duplication** of the part and its ancestors.
3.  **Customization**: Looks up durations in `input/customization_*.csv`. If multiple values apply, the **maximum** is selected.
4.  **Transformation**: 
    - **Bridging**: Recursively bridges dependencies over zero-duration tasks.
    - **Drawing Merging**: Optionally merges drawing tasks for the same base part if `--merge-drawings` is enabled.
5.  **Scheduling**: A resource-constrained engine dispatches tasks to available resource slots, respecting dependencies and factory working hours (skipping weekends/holidays).
6.  **Critical Path**: Computes the unbranching longest chain from initial root task to the terminal milestone.

---

## Installation & Setup

1.  **Requirements**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Run Simulation**:
    ```bash
    # Standard simulation
    python simulate_project.py

    # Simulation with drawing merging enabled
    python simulate_project.py --merge-drawings
    ```
    Outputs are generated in `output/` (HTML, CSV, PNG, MMD).

3.  **Testing**:
    ```bash
    pytest tests/
    ```

---

## Project Structure

- `src/core/`: Domain models (Task, Milestone) and business logic for time/date calculations.
- `src/schedule/`: The heavy lifters: `loader` (I/O), `engine` (CPM/Resource allocation), and `project` (Orchestrator).
- `src/export/`: Exporters for CSV, interactive HTML, Mermaid, and Matplotlib plots.
- `input/`: Contains `project_config.json`, `deliverable_structure.csv`, and customization data.
- `docs/`: Sphinx documentation source.

---

## Documentation

- **User Guide**: Check [docs/user_guide.md](docs/user_guide.md) for detailed input formats and "start from zero" tutorials.
- **API Reference**: Run `cd docs && make html` to generate full developer documentation.
---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
