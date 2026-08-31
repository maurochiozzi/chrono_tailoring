# Chrono Tailoring User Guide

Welcome to the **Chrono Tailoring** system! This software is designed to parse structural templates and project configurations to automatically generate dynamic, resource-constrained project schedules and visualizations.

This guide provides a step-by-step walkthrough for setting up a project from scratch, preparing input files, and interpreting the output artifacts.

---

## 1. Quick Start: Running from Zero

If you are starting with a fresh directory, follow these steps to generate your first schedule:

1.  **Environment Setup**:
    - Ensure you have Python 3.10+ installed.
    - Create and activate a virtual environment:
      ```bash
      python -m venv venv
      source venv/bin/activate  # On Windows: venv\Scripts\activate
      ```
    - Install dependencies:
      ```bash
      pip install -r requirements.txt
      ```

2.  **Input Preparation**:
    - Create an `input/` folder.
    - Place your `project_config.json` and `deliverable_structure.csv` inside it.
    - (Optional) Define customization CSVs directly in `input/` (e.g., `customization_color.csv`).

3.  **Execution**:
    - Run the simulation script:
      ```bash
      python simulate_project.py
      ```
    - Check the `output/` folder for the generated Gantt charts, CSVs, and Mermaid diagrams.

---

## 2. Input File Formats & Examples

The system relies on a set of core files to define the "What", "How", and "When" of your project.

### 2.1. Project Configuration (`input/project_config.json`)

This file defines the global project settings and the high-level milestones (products).

**Example:**
```json
{
  "settings": {
    "project_start_date": "2026-02-08",
    "working_start_hour": 8,
    "working_end_hour": 16,
    "hours_per_day": 8,
    "num_resources": 2
  },
  "milestones": [
    {
      "milestone_id": "M1",
      "name": "Standard Product",
      "customizations": {
        "color": "red"
      }
    },
    {
      "milestone_id": "M2",
      "name": "Custom Variant",
      "extra_args": [
        "10000.ASM",
        {
          "part_number": "10000.ASM",
          "customizations": { "color": "blue" }
        }
      ]
    }
  ]
}
```

- **`settings`**: Controls the calendar and resource pool.
- **`milestones`**: A list of deliverables. 
  - `customizations`: Milestone-wide settings.
  - `extra_args`: Used for **recursive duplication** (creating variants of specific parts).

### 2.2. Deliverable Structure (`input/deliverable_structure.csv`)

This is the "Blueprint". It defines the sequence of tasks for any product. Use semicolon `;` as a delimiter.

**Example:**
```text
document_id;document_part_number;document_name;document_type;strategy;std_duration;successors
1;70010;Final Release;milestone;release;0;
2;10000.DRW;Frame Drawing;drawing;drafting;120;1
3;10000.PL;Frame Parts List;part_list;review;60;2
```

- **`std_duration`**: Duration in **minutes**.
- **`successors`**: Comma-separated list of `document_id` that depend on this task.

### 2.3. Customizations (`input/customization_*.csv`)

Customizations allow you to override the `std_duration` based on specific tags (e.g., `color`, `length`).

**Registry (`input/customization_overview.csv`):**
This file tells the system which customization types are active. It should have a `customization_type` column matching the filenames.
Example: If you have a row with `color`, the system will search for `input/customization_color.csv`.

**Logic Flow:**
1. System reads types from `customization_overview.csv`.
2. For each type, it loads `input/customization_<type>.csv`.
3. Matches the task by `document_name` or `document_type`.
4. Replaces the duration with the value from the matching column.

**Example `input/customization_color.csv`:**
```text
document_part_number;red;blue
10000.ASM;150;300
```
*If a variant has `{"color": "red"}`, the task for `10000.ASM` will take 150 minutes instead of its default.*

---

## 3. Advanced Features

### 3.1. Recursive Duplication (Variants)
When you add a part to `extra_args` in your config, the system:
1. Locates that part in the structure.
2. Clones it and **all its predecessors recursively**.
3. Appends a suffix (e.g., `.1`) to the part number.
4. Allows you to specify different customizations for each clone.

### 3.2. Optional Drawing Merging (`--merge-drawings`)
By default, individual variant drawing tasks are scheduled separately. When running with the `--merge-drawings` flag:
- The system identifies candidate `drawing` tasks sharing the same base part number.
- Combines their durations into a single unified `Merged Drawing for <base_part>` block.
- Re-wires all predecessor part models and successor releases to connect directly to the merged block.

---

## 4. Understanding Outputs

- **`output/gantt_interactive.html`**: Dual-view interactive dashboard:
  - **📅 Gantt View**:
    - **Grouping**: Group tasks dynamically by **Part Number**, **Milestone**, assigned **Resource**, or view as a flat **Task** list.
    - **Sorting**: Toggle between Alphabetical (`A→Z`) and Initial Scheduled Date (`Date`).
    - **Search**: Auto-complete search bar that focuses and scrolls directly to the selected part.
    - **`⚠️ Critical Path` Toggle**: Instantly highlights critical path task bars with golden borders and dims non-critical tasks.
    - **Resource Graph**: Live utilization curve matching active filters and timelines.
  - **🔀 Flow View**: Interactive, pan/zoom DAG network flowchart with semantic node shapes (Milestones, Drawings, Releases, Tasks) and one-click Critical Path arrow highlighting.
- **`output/exported_tasks.csv`**: Full spreadsheet of every task instance with calculated start/end dates, assigned resource IDs, and semicolon-delimited predecessor IDs.
- **`output/critical_path.csv`**: Unbranching sequential path representing the longest duration path from initial root task to project completion.
- **`output/resource_vs_duration.png`**: Sensitivity analysis showing how adding resources impacts the deadline.
- **`output/transformation_log.json`**: An audit trail showing exactly which tasks were merged or removed.
- **`output/*.mmd`**: Mermaid source files for inclusion in documentation or GitHub.

---

## 5. Developer Guide: Maintenance, Testing, and Documentation

This section provides instructions for developers maintaining the Chrono Tailoring project.

### 5.1. Running the Test Suite
The project uses `pytest` for unit and integration testing. All tests are located in the `tests/` directory.

To run the full test suite from the root of the project:
```bash
pytest
```

To run with verbose output:
```bash
pytest -v
```

To run a specific test module (for example, the time calculation rules):
```bash
pytest tests/unit/test_time_calc.py
```

### 5.2. Updating Requirements & Traceability
The source of truth for the project's requirements and source-code implementation mapping is `input/system_specifications.csv`.

When updating requirements or source code references:
1. Edit the semicolon-delimited file `input/system_specifications.csv`.
2. Regenerate the Sphinx RestructuredText file (`docs/requirements.rst`) by running the rendering script from the root directory:
   ```bash
   python scripts/render_requirements.py
   ```

### 5.3. Building the Sphinx Documentation
Sphinx is used to compile the docstrings and Markdown/reST files into standard formats (like HTML).

To compile the documentation as HTML:
1. Ensure the required Python packages are installed (including `sphinx`, `myst_parser`, `sphinxcontrib-mermaid`, and `sphinx_rtd_theme`).
2. Run `sphinx-build` from the project root:
   ```bash
   sphinx-build -b html docs docs/_build/html
   ```
3. Once the build completes, the static HTML files will be available inside `docs/_build/html/`. Open `index.html` in any web browser to view the documentation.

