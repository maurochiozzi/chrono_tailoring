# Project Summary: Chrono Tailoring Project Management

## Overview

This document summarizes the development and enhancements made to the Chrono Tailoring Project Management system. The primary goal was to create a flexible and accurate system for modeling and scheduling project tasks, with advanced features for dynamic duration adjustments, recursive task duplication, and consolidation of specific task types.

## Business Case

The Chrono Tailoring project involves complex manufacturing processes with customized products. Managing these projects effectively requires:
1.  **Dynamic Duration Adjustment:** Task durations vary based on specific product customizations (e.g., color, length). The system must accurately reflect these variations.
2.  **Efficient Project Scaling:** Products often have multiple variants requiring identical task sequences. Manually duplicating these sequences is error-prone and time-consuming. The system needs to support recursive duplication of entire task predecessor chains with appropriate variant numbering.
3.  **Customization Overrides:** Global project customizations can be overridden by specific variant-level customizations, requiring a hierarchical application of rules.
4.  **Simplified Representation:** Certain task types, like "drawing" tasks, might be duplicated across variants but represent a single logical effort. Consolidating these for a clearer overview and optimized scheduling is crucial.
5.  **Accurate Scheduling:** The system needs to perform resource-constrained scheduling to provide realistic project timelines.

## Core Rules and Solutions Implemented

### 1. Dynamic Duration Adjustment based on Customizations

**Rule:** Tasks' durations must be updated based on specified customization types (e.g., color, length). When multiple durations apply from a customization file, the highest value should be selected. Customization values (e.g., 'red' for color) should be treated as descriptive tags/labels, not used for filtering data lookup in customization CSVs.

**Solution:**
-   Modified `_read_customization_duration` to interpret customization values as tags and always select the maximum applicable duration from the relevant customization CSV file. This ensures that a single task variant will always have a duration set based on its most time-consuming customization attribute.
-   The `_apply_customization_durations` method was enhanced to handle both milestone-level and variant-specific customizations, with variant customizations taking precedence (exclusive override).

### 2. Recursive Task Duplication with Variant Numbering

**Rule:** Support recursive duplication of tasks and their entire predecessor chains based on `extra_args` in `project_requirements.txt`. Duplicated tasks must receive unique IDs and maintain their relative predecessor/successor structure. Duplicated tasks' part numbers should be their original part number with a variant suffix appended (e.g., `60011` becomes `60011.1`). Customizations defined in `extra_args` for a specific part number should completely override milestone-level customizations for that variant; otherwise, milestone customizations apply.

**Solution:**
-   The `_load_tasks` method was extensively modified to process `extra_args` from `project_requirements.txt`, supporting both `list[str]` and `list[dict]` formats for defining variants.
-   A recursive helper function `_recursively_duplicate_task_and_ancestry` was implemented to duplicate tasks and their entire predecessor chains. This ensures that when a task (e.g., "60010") is specified for duplication into variants (e.g., "60010.1", "60010.2"), all its dependent tasks are also duplicated for each variant, maintaining the dependency structure.
-   New unique IDs are assigned to all duplicated tasks (`next_task_id`).
-   `part_number`s are correctly suffixed (`original_pn.N`), and `variant_name` and `variant_customizations` are applied to the duplicated tasks.
-   A global `original_id_to_final_ids_map` and `consumed_original_task_ids` set prevent double duplication and track all new task IDs.
-   The dependency re-wiring logic after duplication was refined to ensure all `successors_ids` of affected tasks correctly point to the new variant tasks or original tasks, and then `successors_tasks` and `predecessors` lists are rebuilt for the entire graph.

### 3. Consolidation of Drawing Tasks

**Rule:** `TaskType.DRAWING` tasks that share the same base `part_number` should be consolidated into a single task, inheriting all unique predecessors and successors from the individual variant drawing tasks.

**Solution:**
-   Implemented the `_group_drawing_tasks` method, which is called early in `ProjectSchedule.__init__` (before `_calculate_task_dates`).
-   This method identifies all `TaskType.DRAWING` tasks that belong to the same base `part_number`.
-   It creates a single "Consolidated Drawing for XXXXX" task, assigning it a new unique ID and the base part number.
-   The consolidated task's duration is set to the maximum duration among its constituent drawing variants.
-   **Crucially, a three-phase re-wiring strategy was implemented:**
    1.  **Phase 1 (Update `successors_ids`):** Before any tasks are removed, all tasks in the graph have their `successors_ids` updated. If a task pointed to an individual drawing variant that is now being consolidated, its `successors_ids` is changed to point to the ID of the new consolidated drawing task.
    2.  **Phase 2 (Filter and Extend `self.tasks`):** The individual drawing variants are filtered out from `self.tasks`, and the newly created consolidated drawing tasks are added. `self.task_id_to_task_map` is rebuilt.
    3.  **Phase 3 (Final Graph Rebuild):** A comprehensive rebuild iterates through all tasks in the now-updated `self.tasks`. It clears all `predecessors` and `successors_tasks` lists and then re-populates them based on the updated `successors_ids` lists and the final `task_id_to_task_map`. This ensures all `Task` object references are consistent and correct.

### 4. Robust Scheduling and Analysis

**Rule:** Clarify user's observation about schedule evaluation occurring before task duplication and fix `_calculate_task_dates` (use `heapq`) and `plot_resource_vs_duration`.

**Solution:**
-   Confirmed that `_group_drawing_tasks` is called before `_calculate_task_dates` in `ProjectSchedule.__init__`, ensuring consolidation happens prior to scheduling.
-   The `_calculate_task_dates` method already utilizes a `heapq`-based topological sort for resource-constrained scheduling, providing efficient and accurate date calculations.
-   The `plot_resource_vs_duration` function was updated to ensure `ProjectSchedule` instances are properly initialized with the `project_requirements_path` for each resource analysis run, guaranteeing accurate inputs for plotting.

## Artifacts Generated

-   `exported_tasks.csv`: A detailed export of all tasks, including consolidated tasks and duplicated variants, with their final durations, start/end dates, predecessors, and successors.
-   `task_flow.mmd`, `task_flow_high_level.mmd`: Mermaid flowchart diagrams visualizing task dependencies at full and high-level views.
-   `task_flow_gantt.mmd`, `task_flow_gantt_high_level.mmd`: Mermaid Gantt charts showing task schedules and durations at full and high-level views.
-   `resource_vs_duration.png`: A plot illustrating the relationship between the number of resources and the total project duration.

## Conclusion

The Chrono Tailoring Project Management system has been significantly enhanced to handle complex project scenarios involving dynamic customizations, recursive task duplication, and intelligent task consolidation. The implemented solutions ensure accurate scheduling, maintain data integrity across duplicated and consolidated tasks, and provide clear visualization tools for project analysis. The system is now more robust, scalable, and provides a more realistic representation of project timelines.