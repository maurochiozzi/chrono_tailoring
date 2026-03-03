from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Set, Optional

from src.core.models import Task, ProjectMilestone, TaskType, CustomizationType
from src.schedule.loader import (
    load_project_requirements,
    load_holidays,
    load_raw_tasks_from_csv,
    load_customization_types,
    read_customization_duration
)
from src.schedule.engine import calculate_task_dates
from src import config

class ProjectSchedule:
    def __init__(
        self, 
        project_requirements_path: Path,
        num_resources: int = 1, 
        customization_overview_csv_path: Optional[Path] = None, 
        holidays_path: Optional[Path] = None,
        project_start_date: Optional[datetime] = None
    ):
        self.num_resources = num_resources
        pr_settings, pr_milestones = load_project_requirements(project_requirements_path)
        self.project_requirements_data: List[Dict[str, Any]] = pr_milestones
        self.holidays: Set[datetime.date] = load_holidays(holidays_path) if holidays_path else set()

        # Read working hours from settings, fall back to defaults
        self.working_start_hour: int = int(pr_settings.get('working_start_hour', 8))
        self.working_end_hour: int = int(pr_settings.get('working_end_hour', 16))
        
        self.milestones: List[ProjectMilestone] = []
        self.tasks: List[Task] = []
        self._next_task_id = 1
        
        self._raw_task_template: List[Task] = load_raw_tasks_from_csv(config.TASK_CSV_PATH)
        if not self._raw_task_template:
            print("Error: Could not load base task template from CSV. Exiting.")
            return

        self.milestone_template = ProjectMilestone("TEMPLATE", "MilestoneTemplate", {})
        self.milestone_template.tasks = self._raw_task_template
        
        # Identify customizations
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
        if project_start_date is not None:
            start_date = project_start_date
        elif 'project_start_date' in pr_settings:
            start_date = datetime.strptime(pr_settings['project_start_date'], '%Y-%m-%d')
        else:
            start_date = datetime.strptime(config.PROJECT_START_DATE_STR, '%Y-%m-%d')
        
        # Delegate heavy lifting to engine, passing working hours from settings
        calculate_task_dates(
            self.tasks, start_date, self.holidays, self.num_resources,
            self.working_start_hour, self.working_end_hour
        )

        # Group drawings after calculating dates so dates and durations are correct
        self._group_drawing_tasks()

        milestone_id_to_object_map = {m.milestone_id: m for m in self.milestones}
        for milestone in self.milestones:
            milestone.tasks = []

        for task in self.tasks:
            if task.milestone_id in milestone_id_to_object_map:
                milestone_id_to_object_map[task.milestone_id].tasks.append(task)


    def _process_milestone_tasks(self, milestone_template: ProjectMilestone, milestone_data: Dict[str, Any]) -> List[Task]:
        """
        Generates milestone-specific tasks by copying from a template, handling task duplication,
        and re-wiring dependencies.
        """
        required_part_numbers_for_variants: Set[str] = set()

        deliverable_structure = milestone_data.get('deliverable_structure', [])
        
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
        else:
            for template_task in milestone_template.tasks:
                if template_task.type.description != "milestone":
                    base_tasks_for_milestone.append(template_task.clone())

        milestone_template_task = next((t for t in milestone_template.tasks if t.type.description == "milestone"), None)
        
        print(f"DEBUG {milestone_data.get('milestone_id')}: base_tasks_len={len(base_tasks_for_milestone)}, template_len={len(milestone_template.tasks)}")

        if milestone_template_task:
            if not any(t.id == milestone_template_task.id for t in base_tasks_for_milestone):
                base_tasks_for_milestone.append(milestone_template_task.clone())

        # Ensure milestone id gets assigned
        for t in base_tasks_for_milestone:
             t.milestone_id = milestone_data.get('milestone_id')


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
            main_task = original_base_task.clone()
            main_task.id = self._next_task_id
            self._next_task_id += 1

            final_tasks_for_milestone.append(main_task)
            original_id_to_new_ids_map.setdefault(original_base_task.id, []).append(main_task.id)

        # Wire up newly mapped successors
        # First track the new objects
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

    def _group_drawing_tasks(self):
        """Simplifies logic to find drawings and compress them"""
        drawing_tasks_by_base_part_number: Dict[str, List[Task]] = {}
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
                consolidated_tasks.append(consolidated_task)

        # Update pointers
        for task in self.tasks:
            new_successors_ids_set = set()
            for original_successor_id in getattr(task, 'successors_ids', []):
                if original_successor_id in original_drawing_id_to_consolidated_id_map:
                    new_successors_ids_set.add(original_drawing_id_to_consolidated_id_map[original_successor_id])
                else:
                    new_successors_ids_set.add(original_successor_id)
            task.successors_ids = sorted(list(new_successors_ids_set))

        new_tasks_list = [t for t in self.tasks if t.id not in original_drawing_id_to_consolidated_id_map]
        new_tasks_list.extend(consolidated_tasks)
        self.tasks = new_tasks_list

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

    def _apply_customization_durations(self, global_applied_customization_names: List[str]):
        """Runs the customization adjustments for duration variables."""
        customization_map = {ct.name: ct for ct in self.customization_types}
        tasks_to_keep: List[Task] = []
        removed_task_info: Dict[int, Dict[str, List[int]]] = {}

        for task in self.tasks:
            applicable_durations = []
            task_specific_customization_names = global_applied_customization_names
            
            for customization_name in task_specific_customization_names:
                if customization_name in customization_map:
                    customization_type = customization_map[customization_name]
                    current_customization_value = None
                    for entry in self.project_requirements_data:
                        if 'customizations' in entry and customization_name in entry['customizations']:
                            current_customization_value = entry['customizations'][customization_name]
                            break
                    
                    if current_customization_value is not None:
                        duration = read_customization_duration(
                            Path(customization_type.file_path),
                            customization_name,
                            str(current_customization_value),
                            task.name,
                            task.type.description
                        )
                        if duration is not None:
                            applicable_durations.append(duration)
            
            final_duration = task.duration_minutes
            if applicable_durations:
                max_custom_duration = max(applicable_durations)
                if max_custom_duration == 0:
                    removed_task_info[task.id] = {
                        'predecessors': [p.id for p in task.predecessors],
                        'successors': getattr(task, 'successors_ids', [])
                    }
                    continue
                else:
                    final_duration = max_custom_duration
            
            task.duration_minutes = final_duration
            tasks_to_keep.append(task)
        
        self.tasks = tasks_to_keep
        task_id_to_task_map = {task.id: task for task in self.tasks}

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
