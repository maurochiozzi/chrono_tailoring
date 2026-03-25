from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Set, Optional

from src.core.models import Task, ProjectMilestone, TaskType, CustomizationType
from src.core.logger import audit_logger
from src.schedule.loader import (
    load_project_requirements,
    load_holidays,
    load_raw_tasks_from_csv,
    load_customization_types,
    read_customization_duration
)
from src.schedule.engine import calculate_task_dates
from src import config

# [Req: RF-03, RF-05, RF-06, RF-07, RF-08, RF-09, RF-10, RF-13] — Orchestrates full schedule: loads, customises, schedules and consolidates tasks
class ProjectSchedule:
    """Orchestrates full schedule computing: loads, customises, schedules and consolidates tasks.
    
    .. mermaid::

       graph TD
           A[Load project_config.json] --> B[Load deliverable_structure.csv]
           B --> C{For Each Milestone}
           C --> D[Process Variants & Duplication]
           D --> E[Apply Customizations]
           E --> F[Consolidate Drawing Tasks]
           F --> G[Bridge Zero-Duration Tasks]
           G --> H[Engine: Calculate Dates]
           H --> I[Finish]

    Attributes:
        num_resources (int): Maximum default resources acting in parallel.
        project_requirements_path (Path): Path to the requirements dataset.
        project_requirements_data (List[Dict[str, Any]]): Loaded requirements payload.
        holidays (Set[datetime.date]): Loaded non-working days.
        working_start_hour (int): Start of the working shift.
        working_end_hour (int): End of the working shift.
        milestones (List[ProjectMilestone]): Built sequence of project milestones.
        tasks (List[Task]): The master flat list of instantiated tasks.
        transformation_log (List[Dict[str, Any]]): Audit trailing for debugging structure transformations.
        customization_types (List[CustomizationType]): Cached strategy overlays.
    """
    def __init__(
        self, 
        project_requirements_path: Path,
        num_resources: int = 1, 
        customization_overview_csv_path: Optional[Path] = None, 
        holidays_path: Optional[Path] = None,
        project_start_date: Optional[datetime] = None
    ):
        self.num_resources = num_resources
        self.project_requirements_path = project_requirements_path
        pr_settings, pr_milestones = load_project_requirements(project_requirements_path)
        self.project_requirements_data: List[Dict[str, Any]] = pr_milestones
        self.holidays: Set[datetime.date] = load_holidays(holidays_path) if holidays_path else set()

        # Read working hours from settings, fall back to defaults
        # [Req: RF-01.3, RF-09.1] — Working-hour window read from settings; falls back to 8-16
        self.working_start_hour: int = int(pr_settings.get('working_start_hour', 8))
        self.working_end_hour: int = int(pr_settings.get('working_end_hour', 16))
        
        self.milestones: List[ProjectMilestone] = []
        self.tasks: List[Task] = []
        self._next_task_id = 1
        
        # [Req: RF-26] — Log of all schedule transformations to allow auditing
        self.transformation_log: List[Dict[str, Any]] = []
        
        # [Req: RF-02] — Load the full task template from deliverable_structure.csv
        self._raw_task_template: List[Task] = load_raw_tasks_from_csv(config.TASK_CSV_PATH)
        if not self._raw_task_template:
            print("Error: Could not load base task template from CSV. Exiting.")
            return

        self.milestone_template = ProjectMilestone("TEMPLATE", "MilestoneTemplate", {})
        self.milestone_template.tasks = self._raw_task_template
        
        # Identify customizations
        # [Req: RF-05.4] — Collect all customisation names referenced across milestones and variants
        global_applied_customization_names: Set[str] = set()
        for entry in self.project_requirements_data:
            milestone_id = entry.get("milestone_id")
            milestone_name = entry.get("milestone_name", f"Milestone {milestone_id}")
            if milestone_id is None:
                continue

            milestone = ProjectMilestone(milestone_id, milestone_name, [])
            milestone.tasks = self._process_milestone_tasks(self.milestone_template, entry)
            
            self.milestones.append(milestone)
            self.tasks.extend(milestone.tasks)
            
            if 'customizations' in entry:
                global_applied_customization_names.update(entry['customizations'].keys())
            if 'extra_args' in entry:
                for arg in entry['extra_args']:
                    if isinstance(arg, dict) and 'customizations' in arg:
                        global_applied_customization_names.update(arg['customizations'].keys())

        self.customization_types: List[CustomizationType] = []
        if customization_overview_csv_path:
            self.customization_types = load_customization_types(customization_overview_csv_path)

        if global_applied_customization_names:
            self._apply_customization_durations(list(global_applied_customization_names))

        # Resolve project start date: explicit arg > settings > config default
        # [Req: RF-01.3] — Start date priority: explicit arg > settings > config fallback
        if project_start_date is not None:
            start_date = project_start_date
        elif 'project_start_date' in pr_settings:
            start_date = datetime.strptime(pr_settings['project_start_date'], '%Y-%m-%d')
        else:
            start_date = datetime.strptime(config.PROJECT_START_DATE_STR, '%Y-%m-%d')
        
        # Delegate heavy lifting to engine, passing working hours from settings
        # [Req: RF-10] — Delegate resource-constrained scheduling to the engine
        calculate_task_dates(
            self.tasks, start_date, self.holidays, self.num_resources,
            self.working_start_hour, self.working_end_hour
        )

        # [Req: RF-13] — Consolidate variant drawing tasks after dates are computed
        self._group_drawing_tasks()

        milestone_id_to_object_map = {m.milestone_id: m for m in self.milestones}
        for milestone in self.milestones:
            milestone.tasks = []

        for task in self.tasks:
            if task.milestone_id in milestone_id_to_object_map:
                milestone_id_to_object_map[task.milestone_id].tasks.append(task)


    # [Req: RF-03, RF-03.1, RF-03.2, RF-03.3, RF-03.4, RF-03.5, RF-03.6, RF-04, RF-04.1, RF-04.4]
    def _process_milestone_tasks(self, milestone_template: ProjectMilestone, milestone_data: Dict[str, Any]) -> List[Task]:
        """Generates milestone-specific tasks by copying from a template, handling task duplication,
        and re-wiring dependencies.

        Args:
            milestone_template (ProjectMilestone): Baseline group containing the raw imported tasks.
            milestone_data (Dict[str, Any]): Project milestone requirements dict subset.

        Returns:
            List[Task]: Synthesized list of duplicated and wired task entities for this specific phase.
        """
        required_part_numbers_for_variants: Set[str] = set()

        deliverable_structure = milestone_data.get('deliverable_structure', [])
        
        # [Req: RF-03.1, RF-03.2] — Filter tasks by deliverable_structure if present; default = all non-milestone tasks
        base_tasks_for_milestone: List[Task] = []
        if deliverable_structure:
            required_part_numbers_for_selection: Set[str] = {'70000'}
            for item in deliverable_structure:
                if isinstance(item, dict) and 'part_number' in item:
                    required_part_numbers_for_selection.add(str(item['part_number']).split('.')[0])
                elif isinstance(item, str):
                    required_part_numbers_for_selection.add(item.split('.')[0])
            
            for template_task in milestone_template.tasks:
                if template_task.part_number.split('.')[0] in required_part_numbers_for_selection:
                    base_tasks_for_milestone.append(template_task.clone())
        else:  # [Req: RF-03.2] — No deliverable_structure: include everything except the milestone marker
            for template_task in milestone_template.tasks:
                if template_task.type.description != "milestone":
                    base_tasks_for_milestone.append(template_task.clone())

        milestone_template_task = next((t for t in milestone_template.tasks if t.type.description == "milestone"), None)
        
        print(f"DEBUG {milestone_data.get('milestone_id')}: base_tasks_len={len(base_tasks_for_milestone)}, template_len={len(milestone_template.tasks)}")

        # [Req: RF-03.3] — Milestone marker task is always included regardless of selection filters
        if milestone_template_task:
            if not any(t.id == milestone_template_task.id for t in base_tasks_for_milestone):
                base_tasks_for_milestone.append(milestone_template_task.clone())

        # Ensure milestone id gets assigned
        # [Req: RF-03.5] — Propagate milestone_id to every task for grouping in export/visualisation
        for t in base_tasks_for_milestone:
             t.milestone_id = milestone_data.get('milestone_id')


        # [Req: RF-04.1] — extra_args supports both str (part_number only) and dict (with customizations)
        extra_args = milestone_data.get('extra_args', [])
        for arg_entry in extra_args:
            if isinstance(arg_entry, dict) and 'part_number' in arg_entry:
                required_part_numbers_for_variants.add(str(arg_entry['part_number']).split('.')[0])
            elif isinstance(arg_entry, str):
                required_part_numbers_for_variants.add(arg_entry.split('.')[0])
        
        # Add dynamic variation and ID mapping here
        final_tasks_for_milestone: List[Task] = []
        original_id_to_new_ids_map: Dict[int, List[int]] = {}

        for original_base_task in base_tasks_for_milestone:
            # [Req: RF-03.4, RF-04.5] — Assign new global unique ID; non-variant tasks stay as single copies
            main_task = original_base_task.clone()
            main_task.id = self._next_task_id
            self._next_task_id += 1

            final_tasks_for_milestone.append(main_task)
            original_id_to_new_ids_map.setdefault(original_base_task.id, []).append(main_task.id)

        # Wire up newly mapped successors
        # First track the new objects
        # [Req: RF-03.6, RF-04.4] — Re-wire successors_ids using original->new ID map; rebuild predecessor lists
        new_id_to_task_map: Dict[int, Task] = {task.id: task for task in final_tasks_for_milestone}
        
        for task in final_tasks_for_milestone:
            task.successors_tasks = []
            task.predecessors = []
            
            new_successors_ids_for_task = set()
            for original_successor_id in getattr(task, 'successors_ids', []):
                if original_successor_id in original_id_to_new_ids_map:
                    for mapped_new_id in original_id_to_new_ids_map[original_successor_id]:
                        if mapped_new_id != task.id:
                            new_successors_ids_for_task.add(mapped_new_id)
            task.successors_ids = sorted(list(new_successors_ids_for_task))

        for task in final_tasks_for_milestone:
            for successor_id in task.successors_ids:
                if successor_id in new_id_to_task_map:
                    successor_task = new_id_to_task_map[successor_id]
                    task.successors_tasks.append(successor_task)
                    successor_task.predecessors.append(task)

        return final_tasks_for_milestone

    # [Req: RF-13, RF-13.1, RF-13.2, RF-13.3, RF-13.4, RF-13.5, RF-13.6, RF-13.7]
    def _group_drawing_tasks(self):
        """Simplifies logic to find drawings and compress them globally.
        
        Modifies `self.tasks` in place by replacing multiple variant drawings 
        with a single consolidated entity for efficiency.
        """
        drawing_tasks_by_base_part_number: Dict[str, List[Task]] = {}
        # [Req: RF-13.1, RF-13.2] — Candidate drawings: type=='drawing' AND base part_number NOT starting with '7'
        for task in self.tasks:
            if task.type.description == "drawing":
                base_part_number = task.part_number.split('.')[0]
                if base_part_number.startswith('7'):
                    continue  # Do not consolidate 7XXXX milestone drawings
                if base_part_number not in drawing_tasks_by_base_part_number:
                    drawing_tasks_by_base_part_number[base_part_number] = []
                drawing_tasks_by_base_part_number[base_part_number].append(task)
        
        consolidated_tasks: List[Task] = []
        original_drawing_id_to_consolidated_id_map: Dict[int, int] = {}

        # [Req: RF-13.3, RF-13.4] — Only groups with >1 task are consolidated; duration=sum, init=min, end=max
        for base_part_number, drawing_tasks in drawing_tasks_by_base_part_number.items():
            if len(drawing_tasks) > 1:
                valid_inits = [dt.init_date for dt in drawing_tasks if dt.init_date]
                valid_ends = [dt.end_date for dt in drawing_tasks if dt.end_date]
                earliest_init = min(valid_inits) if valid_inits else None
                latest_end = max(valid_ends) if valid_ends else None

                consolidated_task = Task(
                    id=self._next_task_id,
                    part_number=base_part_number,
                    name=f"Consolidated Drawing for {base_part_number}",
                    task_type=TaskType(description="drawing", strategy="consolidated"),
                    duration_minutes=int(sum(dt.duration_minutes for dt in drawing_tasks))
                )
                consolidated_task.init_date = earliest_init
                consolidated_task.end_date = latest_end
                
                self._next_task_id += 1
                for dt in drawing_tasks:
                    original_drawing_id_to_consolidated_id_map[dt.id] = consolidated_task.id
                    
                # [Req: RF-26] — Trace Log: Record drawing consolidation
                log_data = {
                    "event": "drawing_consolidated",
                    "base_part": base_part_number,
                    "consumed_ids": [dt.id for dt in drawing_tasks],
                    "consolidated_id": consolidated_task.id
                }
                self.transformation_log.append(log_data)
                audit_logger.info(f"Drawing Consolidated: {log_data}")
                
                consolidated_tasks.append(consolidated_task)

        # [Req: RF-13.5] — Phase 1: remap all successors_ids pointing to individual variants -> consolidated ID
        for task in self.tasks:
            new_successors_ids_set = set()
            for original_successor_id in getattr(task, 'successors_ids', []):
                if original_successor_id in original_drawing_id_to_consolidated_id_map:
                    new_successors_ids_set.add(original_drawing_id_to_consolidated_id_map[original_successor_id])
                else:
                    new_successors_ids_set.add(original_successor_id)
            task.successors_ids = sorted(list(new_successors_ids_set))

        # [Req: RF-13.6] — Phase 2: remove individual variant drawing tasks; add consolidated task
        new_tasks_list = [t for t in self.tasks if t.id not in original_drawing_id_to_consolidated_id_map]
        new_tasks_list.extend(consolidated_tasks)
        self.tasks = new_tasks_list

        # [Req: RF-13.7] — Phase 3: rebuild full graph (predecessors + successors_tasks) from updated successors_ids
        task_id_to_task_map = {task.id: task for task in self.tasks}
        for task in self.tasks:
            task.predecessors = []
            task.successors_tasks = []

        for task in self.tasks:
            for successor_id in task.successors_ids:
                if successor_id in task_id_to_task_map:
                    successor_task = task_id_to_task_map[successor_id]
                    task.successors_tasks.append(successor_task)
                    successor_task.predecessors.append(task)

    # [Req: RF-05, RF-05.1, RF-05.2, RF-06, RF-07, RF-07.1, RF-07.2, RF-07.3, RF-08, RF-08.1, RF-08.2, RF-08.3]
    def _apply_customization_durations(self, global_applied_customization_names: List[str]):
        """Runs the customization adjustments for duration variables.

        Args:
            global_applied_customization_names (List[str]): Extracted subset of customizations active in the timeline.
        """
        customization_map = {ct.name: ct for ct in self.customization_types}
        tasks_to_keep: List[Task] = []
        removed_task_info: Dict[int, Dict[str, List[int]]] = {}

        for task in self.tasks:
            # [Req: RF-06] — Collect applicable durations from each active customisation type
            applicable_durations = []
            task_specific_customization_names = global_applied_customization_names
            
            for customization_name in task_specific_customization_names:
                if customization_name in customization_map:
                    customization_type = customization_map[customization_name]
                    current_customization_value = None
                    # [Req: RF-05.1, RF-05.2] — Read value: variant-level override first, then milestone default
                    for entry in self.project_requirements_data:
                        if 'customizations' in entry and customization_name in entry['customizations']:
                            current_customization_value = entry['customizations'][customization_name]
                            break
                    
                    if current_customization_value is not None:
                        # Use new cache-based lookup
                        duration = read_customization_duration(
                            customization_type.df,
                            customization_name,
                            current_customization_value,
                            task.name,
                            task.type.description
                        )
                        if duration is not None:
                            applicable_durations.append(duration)
            
            # [Req: RF-07.1, RF-07.2, RF-08.1] — max() of valid durations; 0 duration means task is excluded
            final_duration = task.duration_minutes
            if applicable_durations:
                max_custom_duration = max(applicable_durations)  # [Req: RF-07.2]
                if max_custom_duration == 0:  # [Req: RF-08.1] — Zero duration: task removed from schedule
                    removed_task_info[task.id] = {
                        'predecessors': [p.id for p in task.predecessors],
                        'successors': getattr(task, 'successors_ids', [])
                    }
                    
                    # [Req: RF-26] — Trace Log: Record task removal due to zero duration
                    log_data = {
                        "event": "task_removed",
                        "task_id": task.id,
                        "part": task.part_number,
                        "reason": "duration=0",
                        "bridged_predecessors": [p.id for p in task.predecessors],
                        "bridged_successors": getattr(task, 'successors_ids', [])
                    }
                    self.transformation_log.append(log_data)
                    audit_logger.info(f"Task Removed: {log_data}")
                    
                    continue
                else:
                    final_duration = max_custom_duration
            # [Req: RF-07.3] — No applicable customisation: keep original std_duration
            task.duration_minutes = final_duration
            tasks_to_keep.append(task)
        
        self.tasks = tasks_to_keep
        task_id_to_task_map = {task.id: task for task in self.tasks}

        # [Req: RF-08.2] — Bridge successors_ids of predecessors over removed (zero-duration) tasks
        for task in self.tasks:
            new_successors_ids = set()
            for original_successor_id in getattr(task, 'successors_ids', []):
                if original_successor_id in task_id_to_task_map:
                    new_successors_ids.add(original_successor_id)
                elif original_successor_id in removed_task_info:
                    removed_succ_info = removed_task_info[original_successor_id]
                    for indirect_successor_id in removed_succ_info['successors']:
                        if indirect_successor_id in task_id_to_task_map:
                            new_successors_ids.add(indirect_successor_id)
            task.successors_ids = sorted(list(new_successors_ids))

        # [Req: RF-08.3] — Full graph rebuild after task removal to restore consistent object references
        for task in self.tasks:
            task.predecessors.clear()
            task.successors_tasks.clear()

        for task in self.tasks:
            for successor_id in task.successors_ids:
                if successor_id in task_id_to_task_map:
                    successor_task = task_id_to_task_map[successor_id]
                    task.successors_tasks.append(successor_task)
                    successor_task.predecessors.append(task)

    def get_deliverable_init_date(self) -> Optional[datetime]:
        earliest_init = None
        for task in self.tasks:
            if task.init_date:
                if earliest_init is None or task.init_date < earliest_init:
                    earliest_init = task.init_date
        return earliest_init

    def get_deliverable_end_date(self) -> Optional[datetime]:
        latest_end = None
        for task in self.tasks:
            if task.end_date:
                if latest_end is None or task.end_date > latest_end:
                    latest_end = task.end_date
        return latest_end

    def get_total_duration(self) -> Optional[timedelta]:
        earliest_init = self.get_deliverable_init_date()
        latest_end = self.get_deliverable_end_date()
        if earliest_init and latest_end:
            return latest_end - earliest_init
        return None

    def __repr__(self):
        init_date_str = self.get_deliverable_init_date().strftime('%Y-%m-%d %H:%M') if self.get_deliverable_init_date() else 'None'
        end_date_str = self.get_deliverable_end_date().strftime('%Y-%m-%d %H:%M') if self.get_deliverable_end_date() else 'None'
        total_duration = self.get_total_duration()
        total_duration_str = str(total_duration) if total_duration else 'None'
        return (f"ProjectSchedule(num_tasks={len(self.tasks)}, "
                f"num_resources={self.num_resources}, "
                f"earliest_init='{init_date_str}', latest_end='{end_date_str}', "
                f"total_duration='{total_duration_str}')")
