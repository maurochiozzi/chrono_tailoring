# scheduler.py

import pandas as pd
from typing import List, Optional, Dict, Any, Set, Tuple
from datetime import datetime, timedelta, date
from pathlib import Path
import json
import heapq

from model import Task, TaskType, CustomizationType, ProjectMilestone # Import classes from model.py
import config # Import config for constants
from config import DEBUG # Import DEBUG flag

class ProjectSchedule:
    WORKING_START_HOUR = 8
    WORKING_END_HOUR = 16 # 8 hours total (16-8)
    HOURS_PER_DAY = 8 # (16-8)

    def __init__(self, project_requirements_path: Path, # Made required
                 num_resources: int = 1, 
                 customization_overview_csv_path: Optional[Path] = None, 
                 holidays_path: Optional[Path] = None,
                 project_start_date: Optional[datetime] = None):
        self.num_resources = num_resources
        self.project_requirements_data: List[Dict[str, Any]] = []
        self.holidays: Set[date] = set()
        self.milestones: List[ProjectMilestone] = [] # New: list of ProjectMilestone objects
        self.tasks: List[Task] = [] # Aggregated tasks from all milestones
        self._next_task_id = 1 # Global task ID counter
        self._raw_task_template: List[Task] = [] # New: Store raw tasks as template
        self.milestone_template: Optional[ProjectMilestone] = None # Explicitly hold the MilestoneTemplate object

        if project_requirements_path:
            self.project_requirements_data = self._load_project_requirements(project_requirements_path)

        if holidays_path:
            self.holidays = self._load_holidays(holidays_path)

        # Load raw tasks template once from the CSV
        self._raw_task_template = self._load_raw_tasks_from_csv(config.TASK_CSV_PATH)
        if not self._raw_task_template:
            print("Error: Could not load base task template from CSV. Exiting.")
            return

        # Populate the milestone_template object
        self.milestone_template = ProjectMilestone("TEMPLATE", "MilestoneTemplate", {})
        self.milestone_template.tasks = self._raw_task_template

        # Process each milestone defined in project_requirements.txt
        global_applied_customization_names: Set[str] = set()
        if self.project_requirements_data:
            for milestone_entry in self.project_requirements_data:
                milestone_id = milestone_entry.get("milestone_id")
                milestone_name = milestone_entry.get("milestone_name", f"Milestone {milestone_id}")
                
                if milestone_id is None:
                    print(f"Warning: Milestone entry missing 'milestone_id'. Skipping: {milestone_entry}")
                    continue

                milestone = ProjectMilestone(milestone_id, milestone_name, milestone_entry)
                
                # Process tasks for this specific milestone using the raw template
                milestone.tasks = self._process_milestone_tasks(self.milestone_template, milestone.milestone_data)
                
                self.milestones.append(milestone)
                self.tasks.extend(milestone.tasks) # Aggregate tasks

                # Collect global customization names across all milestones
                if 'customizations' in milestone_entry:
                    global_applied_customization_names.update(milestone_entry['customizations'].keys())
                if 'extra_args' in milestone_entry:
                    for arg in milestone_entry['extra_args']: # Corrected from 'entry' to 'milestone_entry'
                        if isinstance(arg, dict) and 'customizations' in arg:
                            global_applied_customization_names.update(arg['customizations'].keys())
                        elif isinstance(arg, str): # Handle new format "60010.1" which inherits global customizations
                             # Customizations are inherited from milestone_entry for these
                            pass # Already covered by milestone_customizations
        
        self.customization_types: List[CustomizationType] = []
        if customization_overview_csv_path:
            self.customization_types = self._load_customization_types(customization_overview_csv_path)
        
        applied_customizations_from_reqs = list(global_applied_customization_names)

        self._group_drawing_tasks()
        if DEBUG:
            print(f"DEBUG: After _group_drawing_tasks, self.tasks has {len(self.tasks)} tasks.")

        if DEBUG:
            print(f"DEBUG: Before _apply_customization_durations, self.tasks has {len(self.tasks)} tasks.")
        if applied_customizations_from_reqs:
            self._apply_customization_durations(applied_customizations_from_reqs)
            if DEBUG:
                print(f"DEBUG: After _apply_customization_durations, self.tasks has {len(self.tasks)} tasks.")

        # Use project_start_date from argument or config
        if project_start_date is None:
            project_start_date = datetime.strptime(config.PROJECT_START_DATE_STR, '%Y-%m-%d')
        self._calculate_task_dates(project_start_date)

        # After all processing, re-populate milestone.tasks to reflect the final scheduled tasks
        # and ensure consolidated drawing tasks are correctly associated.
        milestone_id_to_object_map = {m.milestone_id: m for m in self.milestones}
        for milestone in self.milestones:
            milestone.tasks = [] # Clear existing tasks

        for task in self.tasks:
            if task.milestone_id in milestone_id_to_object_map:
                milestone_id_to_object_map[task.milestone_id].tasks.append(task)
            # Consolidated drawing tasks and other non-milestone-specific tasks might not have a direct milestone_id.
            # They are part of the overall project schedule and will be included in the aggregated self.tasks.
            # If a consolidated task needs to be explicitly linked to a specific milestone,
            # that logic would need to be added here. For now, rely on task.milestone_id if set.

    # --- Internal Helper Methods ---
    def _load_project_requirements(self, file_path: Path) -> List[Dict]:
        """Reads project requirements from a JSON file."""
        try:
            with open(file_path, 'r') as f:
                requirements_data = json.load(f)
            return requirements_data
        except FileNotFoundError:
            print(f"Error: Project requirements file not found at {file_path}")
            return []
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from project requirements file {file_path}: {e}")
            return []
        except Exception as e:
            print(f"An unexpected error occurred while loading project requirements from {file_path}: {e}")
            return []

    def _load_raw_tasks_from_csv(self, task_csv_path: Path) -> List[Task]:
        """
        Loads all tasks from the CSV file into raw Task objects.
        This is used to create a template of tasks before any milestone-specific processing.
        Original CSV IDs are retained here.
        """
        raw_tasks: List[Task] = []
        try:
            df = pd.read_csv(task_csv_path, delimiter=';')
            df['strategy'] = df['strategy'].fillna('')
            df.fillna('', inplace=True)

            task_type_cache = {}

            for _, row in df.iterrows():
                description = row['document_type']
                strategy = row['strategy'] if row['strategy'] else None

                cache_key = (description, strategy)
                if cache_key not in task_type_cache:
                    task_type_cache[cache_key] = TaskType(description=description, strategy=strategy)
                
                current_task_type = task_type_cache[cache_key]
                task_id = int(row['document_id'])
                part_num = str(row['document_part_number'])
                successors_str = row['successors']

                task = Task(
                    id=task_id,
                    part_number=part_num,
                    name=row['document_name'],
                    successors_str=successors_str,
                    task_type=current_task_type
                )
                raw_tasks.append(task)
            
            # Resolve immediate successors and predecessors for raw tasks using their original CSV IDs
            raw_task_id_map = {task.id: task for task in raw_tasks}
            for task in raw_tasks:
                task.successors_ids = task._parse_successor_ids(task.successors_str)
                task.resolve_successors(raw_task_id_map)
            
            for task in raw_tasks:
                for successor_task in task.successors_tasks:
                    successor_task.predecessors.append(task)

            return raw_tasks

        except FileNotFoundError:
            print(f"Error: Task CSV file not found at {task_csv_path}")
            return []
        except Exception as e:
            print(f"An error occurred in _load_raw_tasks_from_csv: {e}")
            raise # Re-raise for debugging purposes

    def _is_working_day(self, day: date) -> bool:
        """Checks if a given day is a weekday and not a holiday."""
        # Monday is 0, Sunday is 6
        if day.weekday() >= 5: # Weekend
            return False
        if day in self.holidays: # Holiday
            return False
        return True

    def _get_next_working_time(self, current_time: datetime, duration_minutes: int) -> datetime:
        """
        Calculates the end time by advancing current_time by duration_minutes,
        respecting working hours (8 AM to 4 PM), skipping weekends and holidays.
        """
        if duration_minutes == 0:
            return current_time # 0-duration tasks finish immediately

        remaining_minutes = duration_minutes
        
        # Adjust start time to the next working hour if outside
        if current_time.hour < self.WORKING_START_HOUR:
            current_time = current_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0)
        elif current_time.hour >= self.WORKING_END_HOUR:
            current_time = current_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0) + timedelta(days=1)
        
        # Ensure current_time is on a working day at a working hour
        while not self._is_working_day(current_time.date()) or current_time.hour < self.WORKING_START_HOUR or current_time.hour >= self.WORKING_END_HOUR:
            if current_time.hour >= self.WORKING_END_HOUR:
                current_time += timedelta(days=1)
                current_time = current_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0)
            elif current_time.hour < self.WORKING_START_HOUR:
                current_time = current_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0)
            elif not self._is_working_day(current_time.date()):
                current_time += timedelta(days=1)
                current_time = current_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0)
            
        end_time = current_time

        while remaining_minutes > 0:
            minutes_to_end_of_working_day = (self.WORKING_END_HOUR - end_time.hour) * 60 - end_time.minute

            if minutes_to_end_of_working_day > 0:
                # Can fit some or all remaining minutes in current working day
                if remaining_minutes <= minutes_to_end_of_working_day:
                    end_time += timedelta(minutes=remaining_minutes)
                    remaining_minutes = 0
                else:
                    end_time += timedelta(minutes=minutes_to_end_of_working_day)
                    remaining_minutes -= minutes_to_end_of_working_day
            
            if remaining_minutes > 0:
                # Move to the next working day
                end_time += timedelta(days=1)
                end_time = end_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0)
                while not self._is_working_day(end_time.date()):
                    end_time += timedelta(days=1)
                    end_time = end_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0)
        
        return end_time

    def _process_milestone_tasks(self, milestone_template: ProjectMilestone, milestone_data: Dict[str, Any]) -> List[Task]:
        """
        Generates milestone-specific tasks by copying from a template, handling task duplication,
        and re-wiring dependencies.
        """
        if DEBUG:
            print(f"DEBUG: Entering _process_milestone_tasks for milestone_name='{milestone_data.get('milestone_name')}', current self._next_task_id={self._next_task_id}")

        
        try:
            required_part_numbers_for_variants: Set[str] = set() # This set controls which tasks have variants

            deliverable_structure = milestone_data.get('deliverable_structure', [])
            
            base_tasks_for_milestone: List[Task] = []
            if deliverable_structure:
                # If deliverable_structure is present, filter template_tasks based on it
                required_part_numbers_for_selection: Set[str] = set()
                required_part_numbers_for_selection.add('70000') # Always include global part number
                for item in deliverable_structure:
                    if isinstance(item, dict) and 'part_number' in item:
                        required_part_numbers_for_selection.add(str(item['part_number']).split('.')[0])
                    elif isinstance(item, str):
                        required_part_numbers_for_selection.add(item.split('.')[0])
                
                for template_task in milestone_template.tasks:
                    if template_task.part_number.split('.')[0] in required_part_numbers_for_selection:
                        base_tasks_for_milestone.append(template_task.clone())
            else:
                # If deliverable_structure is not present or empty, include all non-milestone tasks from template
                for template_task in milestone_template.tasks:
                    if template_task.task_type.description != TaskType.MILESTONE.description: # Exclude milestone task from bulk copy
                        base_tasks_for_milestone.append(template_task.clone())

            # Always ensure the special milestone task (original ID 257) is included
            milestone_template_task = next((t for t in milestone_template.tasks if t.id == 257 and t.task_type.description == TaskType.MILESTONE.description), None)
            if milestone_template_task:
                if not any(t.id == milestone_template_task.id for t in base_tasks_for_milestone):
                    base_tasks_for_milestone.append(milestone_template_task.clone())

            # Populate required_part_numbers_for_variants from extra_args for variant generation
            extra_args = milestone_data.get('extra_args', [])
            for arg_entry in extra_args:
                if isinstance(arg_entry, dict) and 'part_number' in arg_entry:
                    required_part_numbers_for_variants.add(str(arg_entry['part_number']).split('.')[0])
                elif isinstance(arg_entry, str):
                    required_part_numbers_for_variants.add(arg_entry.split('.')[0])
            
            # The part_number_to_extra_args dictionary for variant generation logic remains as is.
            # It will implicitly use original_base_task.part_number in part_number_to_extra_args to find variants.

            # Build initial ID to Task map for these filtered/copied base tasks for successor resolution
            # These are still using original CSV IDs for internal linking within this milestone's base tasks
            base_task_id_map = {task.id: task for task in base_tasks_for_milestone}
            # Note: At this stage, each task's predecessors/successors list contains *original* Task objects
            # from the template, not yet re-wired to other tasks in base_tasks_for_milestone.
            # We'll rely on the original_id_to_new_ids_map for later re-wiring with new IDs.


            # Map part_number to its base tasks (there might be multiple tasks for one part_number in deliverable_structure, although unlikely for 60010)
            base_tasks_by_part_number: Dict[str, List[Task]] = {}
            for task in base_tasks_for_milestone:
                if task.part_number not in base_tasks_by_part_number:
                    base_tasks_by_part_number[task.part_number] = []
                base_tasks_by_part_number[task.part_number].append(task)

            part_number_to_extra_args: Dict[str, List[Dict[str, Any]]] = {}
            milestone_customizations = milestone_data.get('customizations', {}) # Use milestone_data
            if 'extra_args' in milestone_data: # Use milestone_data
                for arg_entry in milestone_data['extra_args']: # Use milestone_data
                    if isinstance(arg_entry, dict):
                        full_part_number_from_arg = str(arg_entry['part_number'])
                        base_pn_for_lookup = full_part_number_from_arg.split('.')[0]

                        if base_pn_for_lookup not in part_number_to_extra_args:
                            part_number_to_extra_args[base_pn_for_lookup] = []
                        custom_from_arg = arg_entry.get('customizations', {})
                        if custom_from_arg:
                            variant_customs = custom_from_arg
                        else:
                            variant_customs = milestone_customizations
                        part_number_to_extra_args[base_pn_for_lookup].append({
                            "part_number": full_part_number_from_arg,
                            "customizations": variant_customs
                        })
                    elif isinstance(arg_entry, str):
                        full_part_number = arg_entry
                        base_pn_for_lookup = arg_entry.split('.')[0]
                        
                        if base_pn_for_lookup not in part_number_to_extra_args:
                            part_number_to_extra_args[base_pn_for_lookup] = []
                        part_number_to_extra_args[base_pn_for_lookup].append({
                            "part_number": full_part_number,
                            "customizations": milestone_customizations
                        })

            # Dictionary to store the final tasks for this milestone, each with a unique ID
            final_tasks_for_milestone: List[Task] = []
            # Map original ID from CSV to all its corresponding new IDs (could be one or many if duplicated)
            original_id_to_new_ids_map: Dict[int, List[int]] = {}

            # --- Phase 1: Assign new unique IDs to all tasks and generate variants ---
            for original_base_task in base_tasks_for_milestone:
                # Every task from base_tasks_for_milestone needs a new unique ID, even if not explicitly duplicated.
                # This ensures no ID collisions across milestones.

                # 1. Create the main version of the task with a new unique ID
                main_task = original_base_task.clone()
                main_task.id = self._next_task_id
                main_task.milestone_id = milestone_data.get('milestone_id') # Assign milestone_id
                # Apply milestone-level customizations to main_task by default
                main_task.variant_customizations.update(milestone_customizations) 
                
                if DEBUG:
                    print(f"DEBUG: Assigning new ID {main_task.id} to original task {original_base_task.id}")
                self._next_task_id += 1

                final_tasks_for_milestone.append(main_task)
                original_id_to_new_ids_map.setdefault(original_base_task.id, []).append(main_task.id)

                # 2. Check if this task type has variants defined in extra_args
                # (e.g., 60010 variants like 60010.1, 60010.2)
                if original_base_task.part_number in part_number_to_extra_args:
                    for extra_arg_entry in part_number_to_extra_args[original_base_task.part_number]:
                        # If the extra_arg_entry provides customizations, these should override
                        # the milestone-level customizations for this specific variant or base task.
                        if extra_arg_entry.get("customizations"):
                            if original_base_task.part_number == extra_arg_entry["part_number"]:
                                # This is the base task, update its customizations
                                main_task.variant_customizations.update(extra_arg_entry["customizations"])
                                continue # Skip creating a duplicate if it's the base part number
                            else:
                                # This is a variant, create it with its specific customizations
                                variant_task = original_base_task.clone()
                                variant_task.id = self._next_task_id
                                variant_task.milestone_id = milestone_data.get('milestone_id') # Assign milestone_id
                                if DEBUG:
                                    print(f"DEBUG: Creating variant task for original {original_base_task.id} to new ID {variant_task.id}")
                                self._next_task_id += 1
                                
                                variant_task.part_number = str(extra_arg_entry["part_number"])
                                variant_task.variant_name = variant_task.part_number.split('.')[-1] if '.' in variant_task.part_number else None
                                # Variants should inherit from milestone_customizations first, then be overridden by specific extra_arg customizations
                                variant_task.variant_customizations.update(milestone_customizations)
                                variant_task.variant_customizations.update(extra_arg_entry["customizations"])
                                
                                final_tasks_for_milestone.append(variant_task)
                                original_id_to_new_ids_map.setdefault(original_base_task.id, []).append(variant_task.id)
                        elif original_base_task.part_number != extra_arg_entry["part_number"]:
                            # Case: extra_arg_entry is a string (e.g., "60010.1") or a dict without 'customizations' key
                            # These variants still get milestone-level customizations
                            variant_task = original_base_task.clone()
                            variant_task.id = self._next_task_id
                            variant_task.milestone_id = milestone_data.get('milestone_id') # Assign milestone_id
                            if DEBUG:
                                print(f"DEBUG: Creating variant task for original {original_base_task.id} to new ID {variant_task.id}")
                            self._next_task_id += 1
                            
                            variant_task.part_number = str(extra_arg_entry["part_number"])
                            variant_task.variant_name = variant_task.part_number.split('.')[-1] if '.' in variant_task.part_number else None
                            # Inherit milestone-level customizations
                            variant_task.variant_customizations.update(milestone_customizations) 
                            
                            final_tasks_for_milestone.append(variant_task)
                            original_id_to_new_ids_map.setdefault(original_base_task.id, []).append(variant_task.id)
                elif original_base_task.part_number not in part_number_to_extra_args:
                    # If there are no extra_args for this part number, and it's not a variant
                    # but the overall milestone has customizations, ensure they are applied.
                    # This case is handled by the default update on main_task, but explicitly
                    # clarifying the logic path here. No action needed as main_task already got it.
                    pass



            if DEBUG:
                print(f"DEBUG: original_id_to_new_ids_map for milestone '{milestone_data.get('milestone_name')}': {original_id_to_new_ids_map}")

            # --- Phase 2: Re-wiring Dependencies for final_tasks_for_milestone ---
            # Build a map of new IDs to task objects for efficient lookup
            new_id_to_task_map: Dict[int, Task] = {task.id: task for task in final_tasks_for_milestone}

            # Identify the milestone task within this milestone's tasks
            milestone_task = None
            other_tasks_in_milestone: List[Task] = []
            for task in final_tasks_for_milestone:
                if task.task_type.description == TaskType.MILESTONE.description:
                    milestone_task = task
                else:
                    other_tasks_in_milestone.append(task)
            
            # If a milestone task exists, make it depend on all other tasks in this milestone
            if milestone_task:
                # Clear existing successors_ids for the milestone task if any, as we're redefining its predecessors
                milestone_task.successors_ids.clear() 
                # milestone_task.predecessors.clear() # Predecessors will be rebuilt below

                for other_task in other_tasks_in_milestone:
                    # Make other_task a predecessor of milestone_task
                    if milestone_task.id not in other_task.successors_ids: # Avoid duplicates
                        other_task.successors_ids.append(milestone_task.id)
                        # milestone_task.predecessors.append(other_task) # Will be rebuilt in second pass
                
                # Sort successors_ids for consistency
                milestone_task.successors_ids = sorted(list(set(milestone_task.successors_ids)))
                # milestone_task.predecessors = sorted(milestone_task.predecessors, key=lambda t: t.id) # Will be rebuilt below
            
            for task in final_tasks_for_milestone:
                # Clear existing dependency lists before rebuilding (important if milestone_task was modified)
                task.successors_tasks.clear()
                task.predecessors.clear()

                new_successors_ids_for_task = set()
                for original_successor_id in task.successors_ids: # These are still original CSV IDs
                    if original_successor_id in original_id_to_new_ids_map:
                        # Add all new IDs this original successor mapped to
                        for mapped_new_id in original_id_to_new_ids_map[original_successor_id]:
                            if mapped_new_id != task.id: # Avoid self-loops
                                new_successors_ids_for_task.add(mapped_new_id)
                    else:
                        # If an original successor ID doesn't have a new mapping,
                        # it means it might have been filtered out (e.g., a variant that didn't materialize)
                        # or it's a global task that exists under its original ID in new_id_to_task_map.
                        # We need to ensure it's still a valid ID in the new system.
                        if original_successor_id in new_id_to_task_map and original_successor_id != task.id:
                            new_successors_ids_for_task.add(original_successor_id)
                        else:
                            print(f"Warning: Original successor ID {original_successor_id} for new task {task.id} (part_num {task.part_number}) not found or filtered out in new task map.")

                task.successors_ids = sorted(list(new_successors_ids_for_task))

            # Second pass to populate actual Task object references (predecessors and successors_tasks)
            for task in final_tasks_for_milestone:
                for successor_id in task.successors_ids:
                    if successor_id in new_id_to_task_map:
                        successor_task = new_id_to_task_map[successor_id]
                        task.successors_tasks.append(successor_task)
                        successor_task.predecessors.append(task)
                    else:
                        print(f"Error: Successor task {successor_id} for task {task.id} not found in new_id_to_task_map during final rebuild.")

            # Ensure all relevant tasks have their part_number updated to the milestone_name
            for task in final_tasks_for_milestone:
                # Update part_number for tasks that initially have "70000" and are not consolidated drawings
                if task.part_number == "70000" and not \
                   (task.task_type.description == TaskType.DRAWING.description and task.task_type.strategy == "consolidated"):
                    task.part_number = str(milestone_data.get('milestone_name', "UNKNOWN_MILESTONE"))
                    if DEBUG:
                        print(f"DEBUG: Final check: Task {task.id} part_number set to '{task.part_number}' (from 70000)")
                # For the special case of the milestone task itself, ensure it's set correctly.
                # This ensures the milestone task specifically gets its name, even if its original part_number wasn't "70000".
                if task.task_type.description == TaskType.MILESTONE.description:
                    task.part_number = str(milestone_data.get('milestone_name', "UNKNOWN_MILESTONE"))
                    if DEBUG:
                        print(f"DEBUG: Final check: Milestone task {task.id} part_number explicitly set to '{task.part_number}'")


            if DEBUG:
                print(f"DEBUG: Final tasks for milestone '{milestone_data.get('milestone_name')}':")
                for task in final_tasks_for_milestone:
                    print(f"  Task ID: {task.id}, Part Number: {task.part_number}, Successors: {task.successors_ids}")
            return final_tasks_for_milestone

        except Exception as e: # Simplified exception handling
            print(f"An error occurred in _process_milestone_tasks: {e}")
            return [] # Return empty list on error


    def _read_customization_duration(self, customization_file_path: Path, customization_name: str, customization_value: Any, task_name: str, task_type_description: str) -> Optional[int]:
        """
        Reads a customization CSV file, finds the task_name, and returns its _st duration.
        Filters by customization_value if a corresponding '{customization_name}_value' column exists.
        Assumes the customization file has a column for task name and a column named f'{task_type_description}_st'.
        """
        try:
            df = pd.read_csv(customization_file_path, delimiter=';')

            # Find the column that likely contains the task names (e.g., 'task_description', 'name')
            task_name_column = None
            possible_task_name_columns = ['task_description', 'name', 'document_name']
            for col in possible_task_name_columns:
                if col in df.columns:
                    task_name_column = col
                    break
            
            if not task_name_column:
                return None

            # Construct the specific _st column name using task_type_description
            st_column = f"{task_type_description}_st"
            
            if st_column not in df.columns:
                return 10 # Return default duration if specific _st column is not found

            # Find all rows matching the task_name in the DataFrame
            matching_rows = df[df[task_name_column] == task_name]

            if not matching_rows.empty:
                applicable_st_durations = []
                for _, row in matching_rows.iterrows():
                    duration_value = row[st_column]
                    if pd.notna(duration_value):
                        applicable_st_durations.append(int(duration_value))
                
                if applicable_st_durations:
                    actual_duration = max(applicable_st_durations)

                    return actual_duration
                else:
                    return 10 # Fallback to default duration if values are missing
            else:
                return None # No customization data for this specific task in this file
        except FileNotFoundError:
            print(f"Error: Customization file not found at {customization_file_path}.")
            return None
        except Exception as e:
            print(f"An error occurred reading customization file {customization_file_path} for task '{task_name}' with value '{customization_value}': {e}")
            return None

    def _apply_customization_durations(self, global_applied_customization_names: List[str]):
        """
        Applies customization durations to tasks based on the provided list of customization names.
        Tasks with a final duration of 0 minutes are removed from the schedule.
        When a task is removed, its predecessors become predecessors of its successors.
        """

        customization_map = {ct.name: ct for ct in self.customization_types}
        
        original_tasks_map = {task.id: task for task in self.tasks}
        tasks_to_keep: List[Task] = []
        
        # Store info about removed tasks to re-wire dependencies later
        removed_task_info: Dict[int, Dict[str, List[int]]] = {}

        for task in self.tasks:
            applicable_durations = []
            
            # Determine which customizations apply to this specific task
            # Prioritize variant-specific customizations if present, otherwise use global ones
            task_specific_customization_names = list(task.variant_customizations.keys()) \
                                                if task.variant_customizations else global_applied_customization_names

            for customization_name in task_specific_customization_names:
                if customization_name in customization_map:
                    customization_type = customization_map[customization_name]
                    # Pass task.task_type.description to get the correct _st column
                    # Determine the customization value to pass
                    current_customization_value = None
                    if task.variant_customizations and customization_name in task.variant_customizations:
                        current_customization_value = task.variant_customizations[customization_name]
                    else: # If not variant-specific, try to get from global project requirements
                        for entry in self.project_requirements_data:
                            if 'customizations' in entry and customization_name in entry['customizations']:
                                current_customization_value = entry['customizations'][customization_name]
                                break
                    
                    if current_customization_value is not None:
                        duration = self._read_customization_duration(
                            customization_type.file_path, 
                            customization_name, 
                            current_customization_value, 
                            task.name, 
                            task.task_type.description
                        )
                        if duration is not None:
                            applicable_durations.append(duration)
            
            final_duration = task.duration # Start with current duration (default 10)
            if applicable_durations:
                max_custom_duration = max(applicable_durations)

                if max_custom_duration == 0:

                    # Capture predecessors and successors before removing
                    removed_task_info[task.id] = {
                        'predecessors': [p.id for p in task.predecessors],
                        'successors': task.successors_ids
                    }
                    continue # Skip this task, effectively removing it
                else:
                    final_duration = max_custom_duration
            
            task.duration = final_duration
            tasks_to_keep.append(task)
        
        self.tasks = tasks_to_keep
        
        # Now, re-wire successors_ids for the remaining tasks
        # and then rebuild full relationships based on the new graph structure.

        # Rebuild the task_id_to_task_map with only the remaining tasks
        task_id_to_task_map = {task.id: task for task in self.tasks}

        # First pass: Adjust successors_ids for remaining tasks
        for task in self.tasks:
            new_successors_ids = set()
            for original_successor_id in task.successors_ids:
                if original_successor_id in task_id_to_task_map:
                    # Successor still exists, keep the direct link
                    new_successors_ids.add(original_successor_id)
                elif original_successor_id in removed_task_info:
                    # Successor was removed, re-route to its successors
                    removed_succ_info = removed_task_info[original_successor_id]
                    for indirect_successor_id in removed_succ_info['successors']:
                        if indirect_successor_id in task_id_to_task_map:
                            new_successors_ids.add(indirect_successor_id)
                # else: Successor was removed and had no further valid successors, or already processed (shouldn't happen with sets)
            task.successors_ids = sorted(list(new_successors_ids)) # Keep consistent order

        # Second pass: Clear and rebuild all successors_tasks and predecessors lists based on updated successors_ids
        # Clear existing successor_tasks and predecessors for all remaining tasks
        for task in self.tasks:
            task.predecessors.clear()
            task.successors_tasks.clear() 

        # Rebuild relationships based on the updated successors_ids
        for task in self.tasks:
            for successor_id in task.successors_ids:
                if successor_id in task_id_to_task_map: # Corrected from task_id_to_final_task_map
                    successor_task = task_id_to_task_map[successor_id] # Corrected from task_id_to_final_task_map
                    task.successors_tasks.append(successor_task)
                    successor_task.predecessors.append(task)
                # else: Successor was removed and its re-routing should have been handled in the first pass
                #       or it was a legitimate removal, so we don't need to link to it.


    def _load_customization_types(self, file_path: Path) -> List[CustomizationType]:
        """Reads customization types from a CSV file and constructs their file paths."""
        try:
            df = pd.read_csv(file_path, delimiter=';')
            customization_types = []
            for _, row in df.iterrows():
                name = row['customization_type']
                file_path = f"customization_{name}.csv"
                customization_types.append(CustomizationType(name=name, file_path=file_path))
            return customization_types
        except FileNotFoundError:
            print(f"Error: Customization overview file not found at {file_path}")
            return []
        except Exception as e:
            print(f"An error occurred while loading customization types from {file_path}: {e}")
            return []

    def _group_drawing_tasks(self):
        """
        Consolidates TaskType.DRAWING tasks that share the same base part_number into a single task.
        It re-wires dependencies to point to the consolidated task and removes the original drawing variants.
        """

        drawing_tasks_by_base_part_number: Dict[str, List[Task]] = {}
        for task in self.tasks:
            if task.task_type.description == TaskType.DRAWING.description:
                base_part_number = task.part_number.split('.')[0] # Extract base part number
                if base_part_number not in drawing_tasks_by_base_part_number:
                    drawing_tasks_by_base_part_number[base_part_number] = []
                drawing_tasks_by_base_part_number[base_part_number].append(task)
        
        consolidated_tasks: List[Task] = []
        original_drawing_id_to_consolidated_id_map: Dict[int, int] = {}

        for base_part_number, drawing_tasks in drawing_tasks_by_base_part_number.items():
            if len(drawing_tasks) > 1:
                consolidated_task = Task(
                    id=self._next_task_id,
                    part_number=base_part_number, # Use base part number for consolidated task
                    name=f"Consolidated Drawing for {base_part_number}",
                    successors_str="",
                    task_type=TaskType(description=TaskType.DRAWING.description, strategy="consolidated"),
                    milestone_id=drawing_tasks[0].milestone_id if drawing_tasks else None # Inherit milestone_id
                )
                self._next_task_id += 1
                
                sum_duration = 0 # This needs to be sum for consolidated drawing tasks
                for dt in drawing_tasks:
                    sum_duration += dt.duration
                    original_drawing_id_to_consolidated_id_map[dt.id] = consolidated_task.id
                consolidated_task.duration = sum_duration # Corrected to sum
                consolidated_tasks.append(consolidated_task)
            else:
                pass 

        # --- Phase 1: Update successors_ids for all tasks in the graph ---
        for task in self.tasks:
            new_successors_ids_set = set()
            for original_successor_id in task.successors_ids:
                if original_successor_id in original_drawing_id_to_consolidated_id_map:
                    new_successors_ids_set.add(original_drawing_id_to_consolidated_id_map[original_successor_id])
                else:
                    new_successors_ids_set.add(original_successor_id)
            task.successors_ids = sorted(list(new_successors_ids_set))

        # --- Phase 2: Filter and Extend self.tasks ---
        new_tasks_list: List[Task] = []
        all_original_drawing_task_ids_to_remove = set(original_drawing_id_to_consolidated_id_map.keys())

        for task in self.tasks:
            if task.id not in all_original_drawing_task_ids_to_remove:
                new_tasks_list.append(task)
        
        new_tasks_list.extend(consolidated_tasks)
        self.tasks = new_tasks_list
        
        task_id_to_task_map = {task.id: task for task in self.tasks}

        # --- Phase 3: Final Graph Rebuild (Clear and Re-populate predecessors and successors_tasks) ---
        for task in self.tasks:
            task.predecessors.clear()
            task.successors_tasks.clear()

        for task in self.tasks:
            for successor_id in task.successors_ids:
                if successor_id in task_id_to_task_map:
                    successor_task = task_id_to_task_map[successor_id]
                    task.successors_tasks.append(successor_task)
                    successor_task.predecessors.append(task)
                else:
                    print(f"Warning: Successor ID {successor_id} for Task {task.id} (part_num {task.part_number}) not found in task_id_to_task_map during final graph rebuild.")



    def _load_holidays(self, file_path: Path) -> Set[date]:
        """Loads holidays from a CSV file into a set of date objects."""
        holidays_set: Set[date] = set()
        try:
            with open(file_path, 'r') as f:
                for line in f:
                    try:
                        holiday_date = datetime.strptime(line.strip(), '%Y-%m-%d').date()
                        holidays_set.add(holiday_date)
                    except ValueError:
                        print(f"Warning: Could not parse date from line in holidays.csv: {line.strip()}")
            return holidays_set
        except FileNotFoundError:
            print(f"Error: Holidays file not found at {file_path}")
            return holidays_set
        except Exception as e:
            print(f"An unexpected error occurred while loading holidays from {file_path}: {e}")
            return []

    def _is_working_day(self, day: date) -> bool:
        """Checks if a given day is a weekday and not a holiday."""
        # Monday is 0, Sunday is 6
        if day.weekday() >= 5: # Weekend
            return False
        if day in self.holidays: # Holiday
            return False
        return True

    def _get_next_working_time(self, current_time: datetime, duration_minutes: int) -> datetime:
        """
        Calculates the end time by advancing current_time by duration_minutes,
        respecting working hours (8 AM to 4 PM), skipping weekends and holidays.
        """
        if duration_minutes == 0:
            return current_time # 0-duration tasks finish immediately

        remaining_minutes = duration_minutes
        
        # Adjust start time to the next working hour if outside
        if current_time.hour < self.WORKING_START_HOUR:
            current_time = current_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0)
        elif current_time.hour >= self.WORKING_END_HOUR:
            current_time = current_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0) + timedelta(days=1)
        
        # Ensure current_time is on a working day at a working hour
        while not self._is_working_day(current_time.date()) or current_time.hour < self.WORKING_START_HOUR or current_time.hour >= self.WORKING_END_HOUR:
            if current_time.hour >= self.WORKING_END_HOUR:
                current_time += timedelta(days=1)
                current_time = current_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0)
            elif current_time.hour < self.WORKING_START_HOUR:
                current_time = current_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0)
            elif not self._is_working_day(current_time.date()):
                current_time += timedelta(days=1)
                current_time = current_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0)
            
        end_time = current_time

        while remaining_minutes > 0:
            minutes_to_end_of_working_day = (self.WORKING_END_HOUR - end_time.hour) * 60 - end_time.minute

            if minutes_to_end_of_working_day > 0:
                # Can fit some or all remaining minutes in current working day
                if remaining_minutes <= minutes_to_end_of_working_day:
                    end_time += timedelta(minutes=remaining_minutes)
                    remaining_minutes = 0
                else:
                    end_time += timedelta(minutes=minutes_to_end_of_working_day)
                    remaining_minutes -= minutes_to_end_of_working_day
            
            if remaining_minutes > 0:
                # Move to the next working day
                end_time += timedelta(days=1)
                end_time = end_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0)
                while not self._is_working_day(end_time.date()):
                    end_time += timedelta(days=1)
                    end_time = end_time.replace(hour=self.WORKING_START_HOUR, minute=0, second=0, microsecond=0)
        
        return end_time

    def _calculate_task_dates(self, project_start_date: datetime):
        """
        Calculates the initiation and end dates for all tasks in the project schedule,
        respecting task dependencies, working days/hours, and available resources.
        Implements a resource-constrained scheduling algorithm.
        """
        if not self.tasks:
            return



        in_degree: Dict[int, int] = {task.id: 0 for task in self.tasks}
        task_map: Dict[int, Task] = {task.id: task for task in self.tasks}

        for task in self.tasks:
            for successor in task.successors_tasks:
                if successor.id not in in_degree: # Handle cases where successor might have been removed
                    print(f"Warning: Successor {successor.id} of task {task.id} not found in in_degree map. Skipping.")
                    continue
                in_degree[successor.id] += 1

        # Priority queue for ready tasks: (earliest_start_time, task_id)
        ready_tasks_pq: List[Tuple[datetime, int]] = []

        # Store the earliest possible start time for each task based on its predecessors.
        # This is updated as predecessors complete.
        earliest_start_from_predecessors: Dict[int, datetime] = {
            task.id: project_start_date for task in self.tasks
        }

        # Identify initially ready tasks (in_degree 0)
        for task in self.tasks:
            if in_degree[task.id] == 0:
                task_start_time = self._get_next_working_time(project_start_date, 0)
                heapq.heappush(ready_tasks_pq, (task_start_time, task.id))
        


        # Track currently active tasks and their finish times (min-heap: (finish_time, task_id))
        active_tasks_finish_times: List[Tuple[datetime, int]] = []
        num_active_resources = 0 # Currently utilized resources

        completed_tasks_count = 0
        
        while completed_tasks_count < len(self.tasks):

            next_ready_event_time = ready_tasks_pq[0][0] if ready_tasks_pq else datetime.max
            next_finish_event_time = active_tasks_finish_times[0][0] if active_tasks_finish_times else datetime.max

            # Determine the next event time
            # If resources are full, we *must* wait for a task to finish
            if num_active_resources == self.num_resources:
                current_event_time = next_finish_event_time
            else:
                current_event_time = min(next_ready_event_time, next_finish_event_time)

            if current_event_time == datetime.max:
                print(f"Warning: ProjectSchedule._calculate_task_dates got stuck.")
                print(f"  {len(self.tasks) - completed_tasks_count} tasks remaining unscheduled.")
                print(f"  Ready tasks PQ empty: {not bool(ready_tasks_pq)}")
                print(f"  Active tasks finish times empty: {not bool(active_tasks_finish_times)}")
                print(f"  Possible circular dependencies or logical error preventing tasks from becoming ready or completing.")
                print(f"  Remaining unscheduled tasks IDs: {[task.id for task in self.tasks if task.init_date is None]}")
                break
            


            # 1. Process tasks that are finishing at or before current_event_time
            while active_tasks_finish_times and active_tasks_finish_times[0][0] <= current_event_time:
                finished_time, finished_task_id = heapq.heappop(active_tasks_finish_times)
                num_active_resources -= 1
                
                finished_task = task_map[finished_task_id]
                completed_tasks_count += 1
                
                # Update in-degrees for successors and add new ready tasks to PQ
                for successor in finished_task.successors_tasks:
                    if successor.id not in earliest_start_from_predecessors: # Defensive check
                        print(f"Warning: Successor {successor.id} of finished task {finished_task.id} not found in earliest_start_from_predecessors. Skipping update.")
                        continue
                    earliest_start_from_predecessors[successor.id] = max(
                        earliest_start_from_predecessors[successor.id],
                        finished_task.end_date
                    )
                    in_degree[successor.id] -= 1
                    if in_degree[successor.id] == 0:
                        successor_ready_time = self._get_next_working_time(earliest_start_from_predecessors[successor.id], 0)
                        heapq.heappush(ready_tasks_pq, (successor_ready_time, successor.id))
            
            # 2. Schedule new tasks if resources are available
            while ready_tasks_pq and num_active_resources < self.num_resources:
                task_earliest_start_candidate, task_id_to_schedule = heapq.heappop(ready_tasks_pq)
                task_to_schedule = task_map[task_id_to_schedule]
                
                # A task can only start if its predecessor-determined earliest start is <= current_event_time,
                # AND there's a resource free now.
                # If the task_earliest_start_candidate (from PQ) is *after* the current_event_time,
                # it means we advanced time due to a task finishing, but this ready task isn't ready *yet*.
                # Put it back and break from scheduling new tasks for this event cycle.
                if task_earliest_start_candidate > current_event_time:
                    heapq.heappush(ready_tasks_pq, (task_earliest_start_candidate, task_id_to_schedule))
                    break
                
                actual_start_time = max(
                    earliest_start_from_predecessors[task_to_schedule.id],
                    current_event_time
                )
                
                task_to_schedule.init_date = self._get_next_working_time(actual_start_time, 0)
                task_to_schedule.end_date = self._get_next_working_time(task_to_schedule.init_date, task_to_schedule.duration)
                
                heapq.heappush(active_tasks_finish_times, (task_to_schedule.end_date, task_to_schedule.id))
                num_active_resources += 1

            
            # This loop iteration has done all it can at current_event_time.
            # If no tasks were completed and no new tasks were scheduled in an iteration, it's stuck.
            # This check is implicitly covered by the main while loop condition.

        # Final pass to ensure all tasks have dates, even if scheduling got stuck for some
        # (e.g., due to circular dependencies or unhandled edge cases).
        for task in self.tasks:
            if task.init_date is None:
                task.init_date = self._get_next_working_time(project_start_date, 0)
                task.end_date = self._get_next_working_time(task.init_date, task.duration)
        
        self.tasks.sort(key=lambda t: t.init_date if t.init_date else datetime.min)

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

    def export_tasks_to_csv(self, file_path: str):
        """
        Exports all tasks with their related information to a CSV file.
        """
        try:
            # Collect all unique customization keys first
            all_customization_keys = set()
            for task in self.tasks:
                if task.variant_customizations:
                    all_customization_keys.update(task.variant_customizations.keys())
            
            data = []
            for task in self.tasks:
                row = {
                    'Task ID': task.id,
                    'Part Number': task.part_number,
                    'Task Name': task.name,
                    'Task Type Description': task.task_type.description,
                    'Task Type Strategy': task.task_type.strategy,
                    'Duration (minutes)': task.duration,
                    'Start Date': task.init_date.strftime('%Y-%m-%d %H:%M') if task.init_date else '',
                    'End Date': task.end_date.strftime('%Y-%m-%d %H:%M') if task.end_date else '',
                    'Predecessor IDs': ', '.join(str(p.id) for p in task.predecessors),
                    'Successor IDs': ', '.join(str(s.id) for s in task.successors_tasks),
                    'Variant Name': task.variant_name if task.variant_name else ''
                }
                
                # Add Milestone ID column
                if task.task_type.strategy == "consolidated":
                    row['Milestone ID'] = '' # Consolidated drawings have empty milestone ID
                else:
                    row['Milestone ID'] = task.milestone_id if task.milestone_id else ''
                
                # Add dynamic customization columns
                for key in all_customization_keys:
                    row[f'Customization_{key}'] = task.variant_customizations.get(key, '')
                
                data.append(row)

            df = pd.DataFrame(data)
            df.to_csv(file_path, index=False)
            if DEBUG:
                print(f"Successfully exported {len(self.tasks)} tasks to {file_path}")

        except Exception as e:
            print(f"Error exporting tasks to CSV: {e}")