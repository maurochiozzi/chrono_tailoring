System Specifications
=====================

This page presents the comprehensive list of functional (RF) and non-functional (RNF) requirements that dictate the behavior and constraints of the Chrono Tailoring software.

Functional Requirements
-----------------------

Configuration
^^^^^^^^^^^^^

RF-01: Project Requirements Loading
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    The system must read project_config.json in JSON format.

**Intention**
    Centralize all project configuration in a single human-readable file, facilitating changes without touching the code.

**Source Traceability**
    src/schedule/loader.py:L10-37


RF-01.1: New Requirements Format
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Support for the format {"settings":{...},"milestones":[...]}

**Intention**
    Allow the configuration file to evolve with extra fields without breaking the structure.

**Source Traceability**
    src/schedule/loader.py:L28-30


RF-01.2: Legacy Requirements Format
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Support for a flat array of milestones without the settings block, returning settings={}

**Intention**
    Ensure that projects configured before the introduction of the settings block continue to work without forced migration.

**Source Traceability**
    src/schedule/loader.py:L24-26


RF-01.3: Settings Block Fields
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Support for: project_start_date, working_start_hour, working_end_hour, hours_per_day, num_resources.

**Intention**
    Allow all operational parameters of the project to be adjusted via configuration without code changes.

**Example**
    ``project_start_date: 2026-02-08, num_resources: 2``

**Source Traceability**
    src/schedule/project.py:L31-32 + src/schedule/project.py:L74-80


RF-01.4: Error Handling in Loading
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Missing or invalid JSON returns ({}, []) with an error message without an unhandled exception.

**Intention**
    Avoid silent crashes or exposing stack traces to the end user in case of misconfiguration.

**Source Traceability**
    src/schedule/loader.py:L32-37


Data
^^^^

RF-02: Deliverable Structure Loading
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Read the task template from deliverable_structure.csv delimited by semicolon.

**Intention**
    Decouple the task structure definition from the code, allowing tasks to be added/removed by editing only the CSV.

**Source Traceability**
    src/schedule/loader.py:L69-136


RF-02.1: Mandatory Task CSV Fields
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    document_id, document_part_number, document_name, document_type, strategy, std_duration, successors.

**Intention**
    Ensure the loader knows exactly which columns to look for, making the read deterministic.

**Source Traceability**
    src/core/models.py:L14-35


RF-02.2: Native Duration Reading in Minutes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    std_duration is read directly in minutes, NaN results in 0.

**Intention**
    The engine works internally with minutes to maintain precision in customization integrations.

**Example**
    ``std_duration=150 -> 150 minutes``

**Source Traceability**
    src/schedule/loader.py:L101-105


RF-02.3: Robust Successor Parsing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    successors is a CSV string of integers

**Intention**
     NaN, floats, and non-numeric values are ignored.

**Example**
    ``The CSV may have empty or poorly formatted cells without crashing the entire file load.``


RF-02.4: Graph Resolution on Loading
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    After reading, successors_tasks and predecessors are populated by cross-referencing CSV IDs.

**Intention**
    Materializing object references facilitates graph traversal without repetitive lookups in the ID map.

**Source Traceability**
    src/schedule/loader.py:L117-128


RF-02.5: TaskType Cache
~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    The (document_type, strategy) pair is cached to avoid duplicate objects.

**Intention**
    Reduce memory allocations and ensure object identity among tasks of the same type.

**Source Traceability**
    src/core/models.py:L4-7 + src/schedule/loader.py:L83-93


RF-24: Customization Status Verification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    customization_overview.csv updated with path and status columns before simulation.

**Intention**
    Detecting missing customization files before running avoids silent duration=None errors.

**Source Traceability**
    src/export/csv_export.py:6-31


RF-24.1: Path and Status Calculation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Verifies if input/customization_<name>.csv exists - status='ok' or 'nok'.

**Intention**
    Clear separation between what is available and what is missing, traceable in the CSV itself.

**Source Traceability**
    src/export/csv_export.py:L18-21


RF-24.2: CSV Rewrite with Updated Columns
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    File rewritten every execution with updated path and status values.

**Intention**
    Keeps the overview always synced with the real file system state.

**Source Traceability**
    src/export/csv_export.py:L21-26


RF-24.3: Unnamed Column Discard
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Unnamed:* columns generated by pandas are removed before writing.

**Intention**
    Pandas generates ghost columns if the CSV has extra delimiters - removing them avoids corruption.

**Source Traceability**
    src/export/csv_export.py:L14-15


RF-25: External Holiday Loading
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    holidays.csv with one date YYYY-MM-DD per line loaded into Set[date].

**Intention**
    Externalizing holidays allows annual updates without code modification, and Set ensures O(1) lookup.

**Source Traceability**
    src/schedule/loader.py:L39-53


RF-25.1: YYYY-MM-DD Format per Line
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    One date per line without a header.

**Intention**
    Minimalist format readable by humans and without complex parsing library dependency.

**Source Traceability**
    src/schedule/loader.py:L43-49


RF-25.2: Invalid Line Tolerance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Unparseable lines emit a warning and are ignored.

**Intention**
    A poorly formatted holiday should not invalidate all others.

**Source Traceability**
    src/schedule/loader.py:L49


RF-25.3: Result as Set[date]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Set ensures O(1) lookup in is_working_day - duplicates are discarded.

**Intention**
    The scheduler calls is_working_day for every processed day

**Example**
    `` O(1) vs O(n) is critical for long projects.``


Schedule
^^^^^^^^

RF-03: Task Generation per Milestone
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    For each milestone, the system instantiates independent copies of the task template.

**Intention**
    Each milestone represents a distinct product/deliverable that needs its own execution plan without interfering with others.

**Source Traceability**
    src/schedule/project.py:L16-98


RF-03.1: Selection by deliverable_structure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    If the milestone defines deliverable_structure, only listed part_numbers (+ 70000) are included.

**Intention**
    Allow each milestone to use only the relevant subset of tasks for its product scope.

**Source Traceability**
    src/schedule/project.py:L109-124


RF-03.2: Default Selection without deliverable_structure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Without deliverable_structure, all non-milestone tasks from the template are included.

**Intention**
    Provide a complete default behavior for milestones without scope restriction.

**Source Traceability**
    src/schedule/project.py:L122-124


RF-03.3: Forced Inclusion of Milestone Task
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    The 'milestone' type task is always included regardless of selection.

**Intention**
    The milestone task is the completion marker for the deliverable

**Example**
    `` omitting it would break the Gantt semantics.``


RF-03.4: Global Unique IDs via Counter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Each task receives a unique ID via an incremental _next_task_id.

**Intention**
    Duplicate IDs would cause collisions in the task map and incorrect display on the Gantt

**Example**
    `` the counter ensures uniqueness.``


RF-03.5: milestone_id Assignment to Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Each task inherits the milestone_id from its parent milestone.

**Intention**
    Allows filtering and grouping tasks by milestone in visualization and export.

**Source Traceability**
    src/schedule/project.py:L135-137 + src/core/models.py:L96-104


RF-03.6: Post-Copy Dependency Re-wiring
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    successors_ids are remapped from original IDs to new IDs after copying.

**Intention**
    Without re-wiring, clones would point to tasks from another milestone, creating incorrect cross-milestone dependencies.

**Source Traceability**
    src/schedule/project.py:L160-179 + src/core/models.py:L83-93


RF-04: Recursive Task Duplication with Variants
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    extra_args defines variants of a part_number

**Intention**
     the entire chain of predecessors is duplicated for each variant.

**Example**
    ``Products with multiple variants need independent production trajectories for correct scheduling.``


RF-04.1: Two extra_args Formats
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Input as string (part_number only) or dict (part_number + customizations).

**Intention**
    Allow simple variants with short syntax and complex variants with full override.

**Example**
    ``60010.3" vs {"part_number":"60010.1","customizations":{...}}``

**Source Traceability**
    src/schedule/project.py:L139-144


RF-04.2: Recursive Predecessor Duplication
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    When duplicating a task, all its direct and indirect predecessors are also duplicated per variant.

**Intention**
    A variant that shared predecessors with another would have its dates contaminated by the other variant.

**Source Traceability**
    src/schedule/project.py:L100-181


RF-04.3: Part_number with Variant Suffix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    60010 -> 60010.1, 60010.2, 60010.3 in clones.

**Intention**
    The suffix allows tracking which physical variant each task represents in the export CSV and Gantt.

**Source Traceability**
    src/schedule/project.py:L152 (input/project_config.json - suffix defined in extra_args)


RF-04.4: Original_id to New IDs Map
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Ensures that dependencies between duplicated tasks are correctly re-wired within each variant.

**Intention**
    Without the map, clones would keep references to original IDs, and dependencies between variants would be incoherent.

**Source Traceability**
    src/schedule/project.py:L160-172


RF-04.5: Non-Variant Tasks Remain Unique
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Tasks whose part_number is not in the variants list are not duplicated.

**Intention**
    Shared tasks should not be multiplied, or the schedule would be unrealistically long.

**Source Traceability**
    src/schedule/project.py:L150-156


RF-04.6: Consumed Task Deduplication
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    consumed_original_task_ids prevents multiple duplication of the same task.

**Intention**
    Avoid combinatorial explosion of tasks if a predecessor is reachable by multiple paths.

**Source Traceability**
    src/schedule/project.py:L148


RF-08: Exclusion of Zero-Duration Tasks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Tasks with duration 0 after customization are removed and their dependencies bridged.

**Intention**
    A task with duration 0 is semantically non-existent for that product

**Example**
    `` removing it simplifies the graph.``


RF-08.1: Removal from Task List
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Task with duration 0 is excluded from self.tasks.

**Intention**
    Prevents the scheduler from allocating a resource slot for a task with no real work.

**Source Traceability**
    src/schedule/project.py:L280-284


RF-08.2: Dependency Bridging
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Predecessors of the removed task now point directly to its successors.

**Intention**
    Preserves the logical dependency chain even with the eliminated task, avoiding graph gaps.

**Source Traceability**
    src/schedule/project.py:L294-304


RF-08.3: Post-Removal Graph Reconstruction
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    All predecessors and successors_tasks lists are cleared and repopulated after removals.

**Intention**
    Ensures object reference consistency

**Example**
    `` old pointers would cause utility engine bugs.``


RF-09: Date Calculation with Working Hours
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    init_date and end_date calculated respecting working hours, weekends, and holidays.

**Intention**
    Manufacturing project planning needs real work dates, not simple calendar time.

**Source Traceability**
    src/core/time_calc.py:L19-95


RF-09.1: Configurable Working Hours
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    working_start_hour / working_end_hour defaults 8-16 (480 min/day).

**Intention**
    Companies with shifts different from the 8-16 standard can adjust without modifying code.

**Source Traceability**
    src/core/time_calc.py:L4-7 + src/schedule/project.py:L31-32


RF-09.2: Pre-Work Time Advance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Time before the start of work is advanced to working_start_hour:00.

**Intention**
    Tasks cannot start before working hours

**Example**
    `` normalizing the time avoids incorrect end calculations.``


RF-09.3: Next Day Advance if Post-Work
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Time after the end of work advances to the start of the next working day.

**Intention**
    Avoids tasks being scheduled outside hours, which would produce impossible end_dates.

**Source Traceability**
    src/core/time_calc.py:L46-51


RF-09.4: Weekend Skipping
~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Days with weekday >= 5 are ignored in time advance.

**Intention**
    Weekends are not working days in standard manufacturing

**Example**
    `` including them would underestimate real duration.``


RF-09.5: Holiday Skipping
~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Dates in holidays.csv are treated as non-working days.

**Intention**
    National/local holidays imply a shutdown

**Example**
    `` the schedule must reflect this to be realistic.``


RF-09.6: Progressive Daily Duration Distribution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Current day minutes are consumed first, then full days, then remaining minutes.

**Intention**
    Exact algorithm maintaining minute precision without rounding to full days.

**Example**
    ``Task starts 3PM with 120min -> ends 9AM next working day``

**Source Traceability**
    src/core/time_calc.py:L60-93


RF-09.7: Zero Duration Special Case
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    duration_minutes=0 returns current_time without advance.

**Intention**
    Zero-duration tasks (milestones) should not modify the scheduler's time pointer.

**Source Traceability**
    src/core/time_calc.py:L37-38


RF-10: Scheduling with Resource Constraints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Maximum of num_resources tasks executing in parallel, priority queue by earliest_start.

**Intention**
    Real products have limited teams

**Example**
    `` ignoring resource constraints would produce unachievable schedules.``


RF-10.1: Ready Tasks Priority Queue
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    heapq keeps ready tasks ordered by earliest_start_time.

**Intention**
    Dispatch always chooses the task that can start earliest, maximizing resource utilization.

**Source Traceability**
    src/schedule/engine.py:L60-70


RF-10.2: Active Tasks Heap
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    active_tasks_finish_times tracks the finish_time of each running task.

**Intention**
    Allows efficiently detecting when a resource slot becomes free without scanning the entire list.

**Source Traceability**
    src/schedule/engine.py:L73-74


RF-10.3: Event-Driven Time Advance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    The loop advances to min(next start, next end of active task).

**Intention**
    Event-driven: the scheduler only processes when something changes, avoiding unnecessary polling.

**Source Traceability**
    src/schedule/engine.py:L77-90


RF-10.4: Block when Resources Exhausted
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    If num_active == num_resources, waits for the next end before dispatching new tasks.

**Intention**
    Without this block, the scheduler would ignore the resource constraint.

**Source Traceability**
    src/schedule/engine.py:L81-83


RF-10.5: init_date as Max of Predecessors and Event
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    actual_start = max(earliest_start_from_predecessors, current_event_time).

**Intention**
    Ensures the task only starts after all predecessors are finished AND after there is a resource slot.

**Source Traceability**
    src/schedule/engine.py:L121-127


RF-10.6: earliest_start Propagation to Successors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    At the end of each task, earliest_start for successors is updated

**Intention**
     in_degree 0 releases the successor to the queue.

**Example**
    ``Correct implementation of CPM (Critical Path Method) logic with resource constraints.``


RF-10.7: Safety Final Step
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Tasks without dates at the end of the loop receive dates based on project_start.

**Intention**
    Defense-in-depth against graph edge cases that might leave tasks unscheduled.

**Source Traceability**
    src/schedule/engine.py:L133-136


RF-11: Circular Dependency Detection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Kahn's algorithm detects cycles before scheduling

**Intention**
     RuntimeError if a cycle is found.

**Example**
    ``A cycle in the graph makes scheduling impossible``

**Source Traceability**
     detecting early avoids infinite loops in the engine.


RF-11.1: Kahn's Algorithm (in-degree)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Traverses the graph removing nodes with in-degree 0 - if not all are visited, there is a cycle.

**Intention**
    Classic O(V+E) algorithm for cycle detection in DAGs.

**Source Traceability**
    src/schedule/engine.py:L24-43


RF-11.2: RuntimeError with Task Count
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    The exception informs how many tasks were resolved vs. the total.

**Intention**
    Facilitates diagnosis: the developer knows the extent of the cycle without manual graph inspection.

**Source Traceability**
    src/schedule/engine.py:L44-46


RF-12: Critical Path Calculation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Backward pass calculates the slack for each task - is_critical=True if slack==0.

**Intention**
    The critical path determines the minimum project duration, identifying it allows focusing optimization efforts.

**Source Traceability**
    src/schedule/engine.py:L138-181


RF-12.1: project_end as max(end_date)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Project completion is the latest end_date among all tasks.

**Intention**
    Reference for the backward pass - without it, there's no way to calculate relative slacks.

**Source Traceability**
    src/schedule/engine.py:L141


RF-12.2: Terminal Task latest_end = project_end
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Tasks without successors receive latest_end = project_end.

**Intention**
    Terminal tasks are anchor points from which slacks are propagated.

**Source Traceability**
    src/schedule/engine.py:L143-147


RF-12.3: Backward Pass via out_degree
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Graph traversed in reverse - latest_end propagated as min(latest_start of children).

**Intention**
    The minimum ensures the predecessor cannot end later than what the children's earliest start requires.

**Source Traceability**
    src/schedule/engine.py:L162-175


RF-12.4: Slack Calculation in Minutes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    slack = max(0, latest_end - early_finish) converted from timedelta to minutes.

**Intention**
    Minutes unit is consistent with duration_minutes, facilitating comparisons.

**Source Traceability**
    src/schedule/engine.py:L178-179


RF-12.5: is_critical Flag
~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Tasks with slack==0 receive is_critical=True.

**Intention**
    Boolean flag used by Gantt to render red arrows without reprocessing the graph.

**Source Traceability**
    src/schedule/engine.py:L179-180


RF-12.6: Final Sort by init_date
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    self.tasks sorted ascending by init_date after the backward pass.

**Intention**
    Chronological order facilitates export to CSV and sequential rendering on the Gantt.

**Source Traceability**
    src/schedule/engine.py:L182


RF-13: Drawing Task Consolidation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Drawing tasks with the same base part_number are merged into a single task.

**Intention**
    In practice, a part's drawing is done once - duplicating per variant artificially inflates the schedule.

**Source Traceability**
    src/schedule/project.py:L183-244


RF-13.1: Selection Criterion: type==drawing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Only tasks with type.description=='drawing' are candidates.

**Intention**
    Other task types are variant-specific and should not be consolidated.

**Source Traceability**
    src/schedule/project.py:L187-188


RF-13.2: Exclusion of 7XXXX part_numbers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Drawings with base 7XXXX are not consolidated.

**Intention**
    7XXXX part_numbers are milestone markers, not physical parts - consolidating them would distort the hierarchy.

**Source Traceability**
    src/schedule/project.py:L188-190


RF-13.3: Single Task Groups Not Consolidated
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    If only one drawing variant exists, there is no consolidation.

**Intention**
    Consolidating a task with itself would generate an unnecessary replacement task.

**Source Traceability**
    src/schedule/project.py:L198-199


RF-13.4: Consolidated Task Attributes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Unique ID, base part_number, name 'Consolidated Drawing for XXXXX', duration=sum, init=min, end=max.

**Intention**
    Accumulated duration and full time span are the truest representation of real drawing effort.

**Source Traceability**
    src/schedule/project.py:L204-213


RF-13.5: Phase 1: successors_ids Remapping
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    All successors_ids pointing to individual variants are updated to the consolidated ID.

**Intention**
    Must occur before removal so that no pointers remain dangling.

**Source Traceability**
    src/schedule/project.py:L220-228


RF-13.6: Phase 2: Task Array Swap
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Individual variants removed, consolidated task added.

**Intention**
    Array mutation done in a separate phase to not interfere with Phase 1 traversal.

**Source Traceability**
    src/schedule/project.py:L230-232


RF-13.7: Phase 3: Full Graph Reconstruction
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    predecessors and successors_tasks cleared and repopulated for all tasks.

**Intention**
    Ensures all object references are consistent after Phase 1 and 2 substitutions.

**Source Traceability**
    src/schedule/project.py:L234-244


Customization
^^^^^^^^^^^^^

RF-05: Customizations per Milestone and Variant
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Durations adjusted at two levels: milestone (default) and variant (exclusive override).

**Intention**
    Products of the same family can share most customizations but differ in specific details per variant.

**Source Traceability**
    src/schedule/project.py:L246-315


RF-05.1: Milestone Level (Default)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    customizations in the milestone applies to all milestone tasks.

**Intention**
    Defines the base profile of the milestone without needing to repeat settings for each variant.

**Example**
    ``color: red applies to entire 70015``

**Source Traceability**
    src/schedule/project.py:L260-263


RF-05.2: Variant Level (Exclusive Override)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    customizations in an extra_arg completely replaces the milestone's for that variant - no partial merge.

**Intention**
    Total override ensures predictable and traceable behavior

**Example**
    `` a partial merge would be ambiguous.``

**Source Traceability**
    60010.2 with {color:purple} ignores color:red from milestone


RF-05.3: Milestone Customization Inheritance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Variants without explicit customizations inherit from the parent milestone.

**Intention**
    Avoids unnecessary configuration repetition for variants that do not differ from the default.

**Source Traceability**
    src/schedule/project.py:L260-263


RF-05.4: Global Customization Name Collection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    global_applied_customization_names traverses all milestones and variants before any calculation.

**Intention**
    Ensure the list of customization types is complete before processing any duration.

**Source Traceability**
    src/schedule/project.py:L47-65


RF-06: Duration Lookup by Customization Type
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    For each active customization, look up the duration in the corresponding external CSV.

**Intention**
    Separate customization data from source code allows managers to update durations without programming.

**Source Traceability**
    src/schedule/loader.py:L138-172


RF-06.1: Customization File Resolution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    File resolved as input/customization_<name>.csv.

**Intention**
    Predictable naming convention eliminates the need to configure each file path.

**Example**
    ``customization_color.csv``

**Source Traceability**
    src/schedule/loader.py:L55-67 + src/core/models.py:L9-12


RF-06.2: Match by Task Name or Type
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    document_name is preferred, fallback to part_document_type.

**Intention**
    Allows lookup either by specific name (granular) or generic type.

**Source Traceability**
    src/schedule/loader.py:L154-158


RF-06.3: Duration Column Selection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Looks for <task_type_desc>_st, fallback to duration_st or std_duration.

**Intention**
    Each task type can have its own duration column with fallback to standard fields.

**Example**
    ``drawing_st, part_model_st``

**Source Traceability**
    src/schedule/loader.py:L148-151


RF-06.4: Customization as Descriptive Tag
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    The value (e.g., 'red') does not filter rows

**Intention**
     duration is extracted from the row that matches by name/type.

**Example**
    ``Prevents the absence of a 'red' row from silently causing zero duration.``


RF-06.5: Missing File Tolerance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Missing CSV returns None and emits a warning

**Intention**
     does not interrupt execution.

**Example**
    ``A customization type not yet implemented (status 'nok') should not block the simulation.``


RF-07: Maximum Duration Selection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    When multiple customizations produce valid durations, the largest is applied.

**Intention**
    The manufacturer must plan for the worst case of each task

**Example**
    `` underestimating duration results in real delays.``

**Source Traceability**
    color->120min and length->240min => final duration: 240min


RF-07.1: Collection of All Valid Durations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Non-None durations from all active customizations are gathered into a list.

**Intention**
    Ensure no duration source is discarded before comparison.

**Source Traceability**
    src/schedule/project.py:L276-278


RF-07.2: Applying max()
~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    The max() of the list is the final duration.

**Intention**
    Simple, auditable rule without ambiguity.

**Source Traceability**
    src/schedule/project.py:L278-286


RF-07.3: Maintaining Default Duration without Customization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Without customized durations, the std_duration from the template is kept.

**Intention**
    Tasks not affected by customizations should not have their durations accidentally changed.

**Source Traceability**
    src/schedule/project.py:L276-288


Export
^^^^^^

RF-14: Task Export to CSV
~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    All final tasks exported to exported_tasks.csv.

**Intention**
    Provides an auditable artifact importable by external tools (Excel, BI) of the final schedule state.

**Source Traceability**
    src/export/csv_export.py:L34-81


RF-14.1: Fixed CSV Fields
~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Task ID, Part Number, Task Name, Task Type Description, Strategy, Duration (min), Start Date, End Date, Predecessors, Successors, Variant Name, Milestone ID.

**Intention**
    Minimum set to track each task and reconstruct the dependency graph.

**Source Traceability**
    src/export/csv_export.py:L47-58


RF-14.2: Dynamic Customization Columns
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    One Customization_<key> column per key found in variant_customizations of any task.

**Intention**
    Allows auditing which customizations were applied per variant without reprocessing the requirements JSON.

**Example**
    ``Customization_color, Customization_length``

**Source Traceability**
    src/export/csv_export.py:L40-43 + L69-72


RF-14.3: Blank Milestone ID for Consolidated
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Tasks with strategy=='consolidated' have an empty Milestone ID in the CSV.

**Intention**
    Consolidated tasks belong to multiple milestones - assigning a single one would be incorrect.

**Source Traceability**
    src/export/csv_export.py:L62-66


RF-14.4: YYYY-MM-DD HH:MM Date Format
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    init_date and end_date formatted as 'YYYY-MM-DD HH:MM'.

**Intention**
    Ambiguity-safe ISO format readable by humans and importable by pandas/Excel without extra config.

**Source Traceability**
    src/export/csv_export.py:L54-55


RF-16: Mermaid Diagram Export
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Flowcharts and Gantts in 3 levels of detail generated as .mmd files.

**Intention**
    Mermaid diagrams are renderable in Markdown (GitHub, Notion, Obsidian) without extra tools.

**Source Traceability**
    src/export/mermaid.py:L7-351


RF-16.1: Full Flowchart (per Task)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    One node per task, subgraph per milestone, shape and color by type.

**Intention**
    Granular view for detailed dependency analysis between individual tasks.

**Source Traceability**
    src/export/mermaid.py:L19-64


RF-16.2: Type Flowchart (per Task Type)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    One node per type within each milestone, edges between types.

**Intention**
    Architectural view showing type flow without the noise of individual tasks.

**Source Traceability**
    src/export/mermaid.py:L67-106


RF-16.3: Milestone Flowchart (per Milestone)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    One node per milestone, edges represent inter-milestone dependencies.

**Intention**
    High-level executive view for non-technical stakeholders.

**Source Traceability**
    src/export/mermaid.py:L109-126


RF-16.4: Full Gantt
~~~~~~~~~~~~~~~~~~~

**Description**
    One bar per task with real start and end dates.

**Intention**
    Allows reviewing the complete schedule in any tool that renders Mermaid.

**Source Traceability**
    src/export/mermaid.py:L157-191


RF-16.5: Type Gantt
~~~~~~~~~~~~~~~~~~~

**Description**
    One bar per type with total span and accumulated duration.

**Intention**
    Quickly identifies which task type consumes the most time in the project.

**Source Traceability**
    src/export/mermaid.py:L195-247


RF-16.6: milestone_type_summary Gantt
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    One section per milestone, types grouped, individual special tasks.

**Intention**
    Balance between detail and synthesis: visible per milestone without each task's noise.

**Source Traceability**
    src/export/mermaid.py:L251-335


RF-16.7: Mermaid Duration Formatting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Duration as Xd Yh Zm, milestones as 0d.

**Intention**
    Format required by Mermaid syntax - incorrect formatting would cause a parsing error.

**Source Traceability**
    src/export/mermaid.py:L166-182


RF-17: Self-Contained Interactive HTML Gantt
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    gantt_interactive.html generated with Vis.js via CDN - all data embedded as JSON.

**Intention**
    A single HTML file can be shared without needing a server, facilitating distribution.

**Source Traceability**
    src/export/gantt_interactive.py:L51-290


RF-17.1: JSON Embedded Data in HTML
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Items, groups, milestone/type metadata, resource data, and links embedded as JS constants.

**Intention**
    Self-contained: works offline and in any browser without external API calls.

**Source Traceability**
    src/export/gantt_interactive.py:L110-192


RF-17.2: Swim-lanes by Task Name
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Rows = unique names formatted as 'BasePart - TaskName' sorted alphabetically.

**Intention**
    Visually groups all instances of a task across different milestones into the same row.

**Source Traceability**
    src/export/gantt_interactive.py:L89-108


RF-17.3: Colors by Milestone
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    12-color palette with cycling, default #90A4AE color for tasks without a milestone.

**Intention**
    Immediate visual distinction of bars belonging to each product/deliverable.

**Source Traceability**
    src/export/gantt_interactive.py:76-87


RF-17.4: Configurable Title and Start Date
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    title and project_start_date parameters in export_interactive_gantt.

**Intention**
    Generator function reusability for different projects without changing the source.

**Source Traceability**
    src/export/gantt_interactive.py:L51-60


RF-22: In-Browser Data Export
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    JSON and CSV buttons export visible data via automatic download.

**Intention**
    Allows the user to save a filtered schedule snapshot without server file system access.

**Source Traceability**
    src/export/gantt_interactive.py:L636-643 (HTML buttons)


RF-22.1: JSON Export
~~~~~~~~~~~~~~~~~~~~

**Description**
    Visible items after filter exported as JSON array with .json download.

**Intention**
    JSON preserves all structured metadata and is readable by any programming language.

**Source Traceability**
    src/export/gantt_interactive.py:L716-726 (JS exportJSON)


RF-22.2: CSV Export
~~~~~~~~~~~~~~~~~~~

**Description**
    ID, name, milestone, type, part, duration, dates, predecessors, and successors exported as .csv.

**Intention**
    CSV is importable directly by Excel, facilitating analysis by non-technical users.

**Source Traceability**
    src/export/gantt_interactive.py:L728-743 (JS exportCSV)


RF-22.3: Embedded Metadata per Item
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    _* fields embedded in each JSON item during HTML generation.

**Intention**
    Avoids re-export browser processing - all data for export is already in each item object.

**Source Traceability**
    src/export/gantt_interactive.py:L181-191


Analysis
^^^^^^^^

RF-15: Resource Sensitivity Analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Simulates the project with 1 to N resources and generates a duration x resources graph.

**Intention**
    Allows the manager to identify the point of diminishing returns in adding resources, optimizing cost vs. deadline.

**Source Traceability**
    src/export/plot.py:L18-98


RF-15.1: Configurable Resource Range
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    min_resources and max_resources passed as parameters, default 1-10.

**Intention**
    Different projects have different relevant resource ranges

**Example**
    `` configurability avoids hardcoding.``


RF-15.2: ProjectSchedule Base Reuse
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    A single instance is created and dates reset (None) for each iteration.

**Intention**
    Avoid recreating the schedule from scratch in each iteration significantly reduces I/O and CPU time.

**Source Traceability**
    src/export/plot.py:L38-43 + L56-65


RF-15.3: Internal Output Suppression
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    redirect_stdout(os.devnull) suppresses prints from each loop iteration.

**Intention**
    The loop runs N times - without suppression, the terminal would be flooded with repetitive output.

**Source Traceability**
    src/export/plot.py:L57-65


RF-15.4: Total Duration in Minutes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    total_duration = max(end_date) - min(init_date) converted to minutes.

**Intention**
    Minutes are more accurate than days for comparing small differences between resource scenarios.

**Source Traceability**
    src/export/plot.py:L69-73


RF-15.5: Exported Matplotlib Graph
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    resource_vs_duration.png with X-axis=resources, Y-axis=minutes, markers, and grid.

**Intention**
    Immediate visualization of the efficiency curve, faster to interpret than a table of numbers.

**Source Traceability**
    src/export/plot.py:L79-93


RF-15.6: Graceful Degradation without Matplotlib
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    If matplotlib is unavailable, raw data is printed to the terminal.

**Intention**
    Headless environments or minimal setups should not be blocked by an optional visualization dependency.

**Source Traceability**
    src/export/plot.py:L95-98


Visualization
^^^^^^^^^^^^^

RF-18: Interactive Gantt Filters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Sidebar with checkboxes for milestone and task type.

**Intention**
    In projects with many milestones and types, the full view is dense - filters allow focusing on relevant subsets.

**Source Traceability**
    src/export/gantt_interactive.py:L745-755 (JS filterItems)


RF-18.1: Milestone Filter
~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Checkbox with color per milestone, toggle all on/off buttons.

**Intention**
    Allows comparing only selected milestones side-by-side on the same timeline.

**Source Traceability**
    src/export/gantt_interactive.py:L652-658 (HTML sidebar)


RF-18.2: Task Type Filter
~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Checkbox per type, toggle all on/off buttons.

**Intention**
    Allows focusing on only 'release' tasks to review delivery points, for example.

**Source Traceability**
    src/export/gantt_interactive.py:L661-668 (HTML sidebar)


RF-18.3: Combined Filters (AND Logic)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Item visible only if both milestone AND type are active.

**Intention**
    AND logic avoids displaying partially filtered items and maintains visual consistency.

**Source Traceability**
    src/export/gantt_interactive.py:L746-748 (JS)


RF-18.4: Visible Item Count in Header
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    'N tasks · M rows' badge dynamically updated after filtering.

**Intention**
    Immediate user feedback on how many items are visible after applying filters.

**Source Traceability**
    src/export/gantt_interactive.py:L754-755 (JS)


RF-19: SVG Dependency Arrows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Arrows overlaid on the timeline via absolute SVG - red for critical, gray for others.

**Intention**
    Invisible dependencies make it hard to identify the critical path and impact of delays.

**Source Traceability**
    src/export/gantt_interactive.py:L113-197


RF-19.1: Red Critical Arrows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Links where both tasks have is_critical=True are rendered in red with a drop-shadow.

**Intention**
    The critical path is the most actionable project info - must be immediately visible.

**Source Traceability**
    src/export/gantt_interactive.py:L152-158


RF-19.2: Gray Non-Critical Arrows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    All other dependencies are gray (#6b728e).

**Intention**
    Keeps the critical path highlighted while still providing full dependency context.

**Source Traceability**
    src/export/gantt_interactive.py:L160-165


RF-19.3: Non-Critical Arrow Toggle
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    'Show Task Arrows' checkbox in sidebar controls gray arrow visibility.

**Intention**
    In dense projects, many arrows clutter the view - the toggle allows clearing it without losing the critical path.

**Source Traceability**
    src/export/gantt_interactive.py:L700-703 (JS toggle handler)


RF-19.4: Auto-Redraw on Move/Zoom
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Arrows are redrawn on Vis.js rangechanged and changed events.

**Intention**
    Without redrawing, arrows would stay in place while bars move with pan/zoom.

**Source Traceability**
    src/export/gantt_interactive.py:L875-885 (JS event listeners)


RF-19.5: Bezier Arrow Geometry
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Arrows start from the vertical center of the source bar and end at the target bar center with a smooth curve.

**Intention**
    Bezier curve avoids bar overlap and is more readable than straight lines.

**Source Traceability**
    src/export/gantt_interactive.py:820-850 (JS drawArrow)


RF-20: Non-Working Day Highlighting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Weekends and holidays shaded on the timeline as background items.

**Intention**
    Makes it immediate for the user why certain bars skip days, avoiding gap misinterpretation.

**Source Traceability**
    src/export/gantt_interactive.py:L199-219


RF-20.1: Non-Working Day Background
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    For each day in the project range, a type='background' item is added if it's a weekend or holiday.

**Intention**
    Vis.js supports background items natively - the approach is idiomatic and performant.

**Source Traceability**
    src/export/gantt_interactive.py:L209-218


RF-20.2: CSS Styling (holiday-bg)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Non-working day background color defined by CSS class.

**Intention**
    Separates data from presentation - color can be changed without modifying the Python generator.

**Source Traceability**
    src/export/gantt_interactive.py:L302-304 (CSS .holiday-bg)


RF-21: Resource Histogram
~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Step chart below the timeline showing active tasks over time.

**Intention**
    Allows visualizing allocation bottlenecks: peaks above the resource limit indicate potential conflict.

**Source Traceability**
    src/export/gantt_interactive.py:L247-266


RF-21.1: +1/-1 events per Task
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    init_date generates +1 and end_date generates -1 in the time series.

**Intention**
    Efficient sweep-line model to calculate load without iterating over all timesteps.

**Source Traceability**
    src/export/gantt_interactive.py:L249-252


RF-21.2: Sequential Event Processing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Events sorted and processed to accumulate current load.

**Intention**
    Ordered processing ensures load never becomes negative or incorrect.

**Source Traceability**
    src/export/gantt_interactive.py:L253-257


RF-21.3: Double Points for Step Chart
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Two points (old and new value) emitted per event to force step visualization.

**Intention**
    Vis.js interpolates by default - the double point makes the curve a perfect step faithful to discrete allocation.

**Source Traceability**
    src/export/gantt_interactive.py:L261-266


RF-21.4: Y-axis Label with Resource Limit
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Y-axis displays 'Active Tasks (limit: N)' where N is total_resources.

**Intention**
    Without the explicit limit, the user would need external knowledge to interpret the graph.

**Source Traceability**
    src/export/gantt_interactive.py:L797-799 (JS Graph2d options)


RF-21.5: Resource Limit Reference Line
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Horizontal line at the total_resources value displayed in the graph.

**Intention**
    Immediate visual reference of where parallelism ceiling is exceeded.

**Source Traceability**
    src/export/gantt_interactive.py:L809-814 (JS setCustomTime)


RF-23: Sidebar Summary and Requirements Panel
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Sidebar displays project summary and raw project_config.json content.

**Intention**
    Contextualizes the Gantt without opening other files - the viewer is self-sufficient.

**Source Traceability**
    src/export/gantt_interactive.py:L277-290


RF-23.1: Project Summary
~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Start, end, calendar duration, and resource count calculated during generation.

**Intention**
    High-level metrics a manager checks first upon opening the Gantt.

**Source Traceability**
    src/export/gantt_interactive.py:L277-285


RF-23.2: Raw Requirements Content
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    project_config.json read and embedded in a monospace box in the HTML.

**Intention**
    Allows verifying what settings generated the displayed schedule without leaving the page.

**Source Traceability**
    src/export/gantt_interactive.py:L287-290


Audit
^^^^^

RF-26: Transformation Trace Log
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    The system must generate a JSON log with all graph mutations (zero-duration bridging and drawing consolidation).

**Intention**
    Automatic graph mutations hinder auditing - the log provides full transparency on why dates changed.

**Source Traceability**
    src/schedule/project.py:L37-41 + L230-239 + L300-311


Non-Functional Requirements
---------------------------

Architecture
^^^^^^^^^^^^

RNF-01: Modular Structure in Python Package
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    src/ divided into core/, schedule/, and export/ by responsibility.

**Intention**
    Separation of concerns reduces coupling, facilitates unit tests, and allows swapping a module without affecting others.

**Source Traceability**
    src/ (directory structure)


RNF-01.1: core/ Module
~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Domain models (Task, ProjectMilestone, TaskType, CustomizationType) and time calculation.

**Intention**
    Isolates pure domain without I/O dependencies or specific business logic.

**Source Traceability**
    src/core/models.py + src/core/time_calc.py


RNF-01.2: schedule/ Module
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    loader.py (I/O), engine.py (algorithms), project.py (orchestration).

**Intention**
    Each file has a single responsibility - engine.py can be tested without I/O.

**Source Traceability**
    src/schedule/loader.py + src/schedule/engine.py + src/schedule/project.py


RNF-01.3: export/ Module
~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    csv_export, mermaid, plot, gantt_interactive — one exporter per format.

**Intention**
    Adding a new export format does not require modifying existing ones.

**Source Traceability**
    src/export/


Configuration
^^^^^^^^^^^^^

RNF-02: Centralized Config via config.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    All paths and global parameters in config.py using pathlib.Path.

**Intention**
    A single point of change for adapting the project to a new directory structure.

**Source Traceability**
    config.py:L1-21


RNF-02.1: __file__ Derived BASE_DIR
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    BASE_DIR = Path(__file__).parent - all paths derive from it.

**Intention**
    Ensures operation independent of the Python process's working directory.

**Source Traceability**
    config.py:L8


RNF-02.2: Automatic OUTPUT_DIR Creation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    OUTPUT_DIR.mkdir(parents=True) on the first run if it doesn't exist.

**Intention**
    Zero-setup experience: the user does not need to create directories manually.

**Source Traceability**
    simulate_project.py:L32-35


RNF-02.3: Global DEBUG Flag
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    config.DEBUG controls all diagnostic prints.

**Intention**
    A single flag disables all prints without manually commenting each occurrence in the code.

**Source Traceability**
    config.py:L21


Compatibility
^^^^^^^^^^^^^

RNF-03: Legacy Format Backward Compatibility
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Loader accepts flat array without modification - settings returns {}.

**Intention**
    Existing projects do not need to migrate their project_config.json to continue working.

**Source Traceability**
    src/schedule/loader.py:L24-26


Performance
^^^^^^^^^^^

RNF-04: O(log n) Scheduler with heapq
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Binary priority queues for ready and active task selection.

**Intention**
    Linear search alternative would be O(n) per event - for projects with hundreds of tasks, the difference is significant.

**Source Traceability**
    src/schedule/engine.py:L60-70


RNF-10: Output Suppression in Analysis Loop
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    redirect_stdout(os.devnull) during plot_resource_vs_duration iterations.

**Intention**
    Without suppression, N runs × K prints = proportional noise that degrades terminal UX.

**Source Traceability**
    src/export/plot.py:L57-65


RNF-16: Customization CSV Cache
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Customization CSVs are loaded into memory DataFrames at the start instead of reading from disk per task.

**Intention**
    With dozens of milestones and hundreds of tasks, repeated disk reads would degrade performance (I/O burst).

**Source Traceability**
    src/schedule/loader.py:L55-64 + L142-156


RNF-21: Customization Lookup Cache
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Load all customization CSVs into dictionaries (hash maps) in memory during boot.

**Intention**
    Optimize processing speed, especially for Sensitivity Analysis (RF-15)

**Source Traceability**
    src/schedule/loader.py


Distribution
^^^^^^^^^^^^

RNF-05: Self-Contained HTML without Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    gantt_interactive.html works on file:// without local HTTP server.

**Intention**
    Facilitates distribution via email or storage in shared drives without infrastructure.

**Source Traceability**
    src/export/gantt_interactive.py:L291-300 (self-contained HTML)


Frontend
^^^^^^^^

RNF-06: Framework-less Frontend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Vis.js Timeline via CDN + vanilla CSS and JS, no bundler or transpiler.

**Intention**
    Zero build dependencies on frontend: the generated HTML is immediately functional.

**Source Traceability**
    src/export/gantt_interactive.py:L298-300 (CDN links)


Quality
^^^^^^^

RNF-07: Idempotent Execution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    The same inputs always produce the same outputs without state persisting between runs.

**Intention**
    Predictability is essential for comparing results of different project configurations.

**Source Traceability**
    simulate_project.py (top-level execution)


RNF-07.1: No State Between Runs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    No mutable global variables persist from one run to the next.

**Intention**
    Side effects between runs would make results non-reproducible.

**Source Traceability**
    src/schedule/project.py:L16 (always new instance)


RNF-07.2: Config-Based Start Date
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    project_start_date read from settings or config.py, never from datetime.now() in main flow.

**Intention**
    datetime.now() would produce different results per run, breaking idempotency.

**Source Traceability**
    src/schedule/project.py:L74-80


RNF-22: Business Time Validation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Validate if working_start < working_end and if durations are non-negative, emitting clear errors.

**Intention**
    Prevent incoherent calendar settings from causing infinite loops or impossible dates

**Source Traceability**
    src/core/time_calc.py


Resilience
^^^^^^^^^^

RNF-08: Matplotlib Graceful Degradation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Matplotlib ImportError captured - fallback to textual output.

**Intention**
    CI/CD environments or headless servers should not fail due to a visualization dependency.

**Source Traceability**
    src/export/plot.py:L11-16


Observability
^^^^^^^^^^^^^

RNF-09: Conditional Debug Output
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    All diagnostic prints conditioned on config.DEBUG.

**Intention**
    Silent production, verbose development — without code modification between the two.

**Source Traceability**
    config.py:L21 + (usage in all modules)


Robustness
^^^^^^^^^^

RNF-11: Robust Numeric Parsing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    NaN, floats, empty strings, and non-numeric characters tolerated in successors, std_duration, document_id.

**Intention**
    CSVs generated by Numbers/Excel frequently have formatting artifacts - the parser should not fail because of them.

**Source Traceability**
    src/core/models.py:L38-49 + src/schedule/loader.py:L78-81


Extensibility
^^^^^^^^^^^^^

RNF-12: Extensible Customization via File
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    New types added via new .csv + new line in customization_overview.csv without code changes.

**Intention**
    Open/Closed Principle: the system is open for extension (new types) and closed for modification.

**Example**
    ``electronic_equipment and door_position already listed with 'nok' status``

**Source Traceability**
    src/schedule/loader.py:L55-67 + src/export/csv_export.py:L6-31


Integrity
^^^^^^^^^

RNF-13: Global Task ID Uniqueness
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Incremental _next_task_id ensures unique IDs throughout the run.

**Intention**
    Duplicate IDs would cause collisions in the task map and incorrect Gantt display.

**Source Traceability**
    src/schedule/project.py:L36 + L150-154


RNF-14: Graph Reconstruction after Mutation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    predecessors and successors_tasks cleared and repopulated after any task set change.

**Intention**
    Outdated object references are the most common cause of silent bugs in mutable graphs.

**Source Traceability**
    src/schedule/project.py:L234-244 + L306-315


RNF-20: Transformation Audit Log
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    The system must generate audit.log detailing zero-duration removals (RF-08) and consolidations (RF-13).

**Intention**
    Allow auditing and debugging of how the original graph was transformed into the final schedule

**Source Traceability**
    src/core/logger.py


UX/UI
^^^^^

RNF-15: HTML Dark Mode Visual Design
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Dark system design with Inter typography, subtle borders, hover transitions, and styled tooltips without external CSS.

**Intention**
    Professional interface increases tool adoption by project managers.

**Source Traceability**
    src/export/gantt_interactive.py:L303-400 (CSS block)


Documentation
^^^^^^^^^^^^^

RNF-17: Technical Documentation via Docstrings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    All code must be documented in the Google Python Style Guide standard inside .py files.

**Intention**
    Facilitate maintenance and allow automatic technical manual generation

**Source Traceability**
    src/ (all modules)


RNF-18: Automated PDF Generation (Sphinx)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    The system must have Sphinx configuration to convert docstrings into a professional PDF manual.

**Intention**
    Professionalize the deliverable and ensure technical documentation is always in sync with code

**Source Traceability**
    docs/conf.py + Makefile


RNF-19: Requirements List Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    The final PDF must import and format the system_specifications.csv file automatically.

**Intention**
    Ensure total traceability between what was requested (Requirement) and what was coded (Function)

**Source Traceability**
    docs/index.rst


RNF-23: User Manual (README/Markdown)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Description**
    Explanatory file on how to prepare inputs (JSON/CSV) and interpret Mermaid and Gantt diagrams.

**Intention**
    Reduce the learning curve for new Project Managers utilizing the tool

**Source Traceability**
    README.md / docs/user_guide.md


