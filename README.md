# Chrono Tailoring 🕒

Chrono Tailoring is a sophisticated toolkit for dynamic project scheduling, milestone structuring, and visualization for complex manufacturing or engineering projects. It specialized in modeling variant-heavy deliverable structures with resource constraints.

## Features

- **Automated Scheduling**: Applies resource constraints (Critical Path Method) and calculates initiation, end, and duration times dynamically.
- **Recursive Task Duplication**: Support for `extra_args` variants that clone entire predecessor chains with unique suffixes (e.g., `60010.1`).
- **Smart Consolidation**: Automatically merges redundant task types (like drawings) across variants into single logical efforts to optimize the schedule.
- **Customization Overlays**: Hierarchical duration overrides (Milestone vs. Variant) based on external CSV data.
- **Rich Visualizations**:
  - Interactive Gantt charts (HTML using Vis.js) with dependency arrows and resource histograms.
  - Mermaid diagrams (Flowcharts and Gantts) for different levels of detail.
  - Resource sensitivity plots (Matplotlib).
- **Audit Logging**: Comprehensive JSON/Log trail of any structural mutations or duration adjustments.

---

## How It Works

The system follows a multi-stage pipeline to transform a static template into a resource-constrained schedule:

1.  **Loading**: Reads `deliverable_structure.csv` and searches for `project_config.json`.
2.  **Instantiation**: Creates tasks for each milestone. If `extra_args` are present, it performs a **recursive duplication** of the part and its ancestors.
3.  **Customization**: Looks up durations in `input/customization_*.csv`. If multiple values apply, the **maximum** is selected to ensure a conservative, safe schedule.
4.  **Transformation**: 
    - **Consodilation**: Merges drawing tasks for the same base part.
    - **Bridging**: Eliminates tasks with 0 duration while maintaining dependency continuity.
5.  **Scheduling**: A `heapq`-based engine dispatches tasks to available resource slots, respecting dependencies and factory working hours (skipping weekends/holidays).
6.  **Critical Path**: A backward pass identifies slacks and tags critical tasks for red-arrow highlighting in the Gantt.

---

## Installation & Setup

1.  **Requirements**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Run Simulation**:
    ```bash
    python simulate_project.py
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
