# scheduler.py

import pandas as pd
from typing import List, Optional, Dict, Any, Set, Tuple
from datetime import datetime, timedelta, date
from pathlib import Path
import json
import heapq
import copy # Needed for deepcopy in _load_tasks

from model import Task, TaskType, CustomizationType # Import classes from model.py
import config # Import config for constants

class ProjectSchedule:
    WORKING_START_HOUR = 8
    WORKING_END_HOUR = 16 # 8 hours total (16-8)
    HOURS_PER_DAY = 8 # (16-8)

    def __init__(self, task_csv_path: Optional[Path] = None, tasks: Optional[List[Task]] = None, num_resources: int = 1, 
                 customization_overview_csv_path: Optional[Path] = None, 
                 project_requirements_path: Optional[Path] = None,
                 holidays_path: Optional[Path] = None,
                 project_start_date: Optional[datetime] = None): # Make project_start_date configurable
        self.num_resources = num_resources
        self.project_requirements_data: List[Dict[str, Any]] = []
        self.holidays: Set[date] = set()
        self.scheduled_tasks_count = 0 

        if project_requirements_path:
            self.project_requirements_data = self._load_project_requirements(project_requirements_path)

        if holidays_path:
            self.holidays = self._load_holidays(holidays_path)

        if tasks is not None:
            self.tasks = tasks
        elif task_csv_path:
            self.tasks = self._load_tasks(task_csv_path, self.project_requirements_data)
        else:
            raise ValueError("Either 'tasks' or 'task_csv_path' must be provided.")

        self.customization_types: List[CustomizationType] = []
        if customization_overview_csv_path:
            self.customization_types = self._load_customization_types(customization_overview_csv_path)
        
        unique_customization_names = set()
        for entry in self.project_requirements_data:
            if 'customizations' in entry:
                unique_customization_names.update(entry['customizations'].keys())
            if 'extra_args' in entry:
                for arg in entry['extra_args']:
                    if 'customizations' in arg:
                        unique_customization_names.update(arg['customizations'].keys())
        applied_customizations_from_reqs = list(unique_customization_names)

        self._group_drawing_tasks()

        if applied_customizations_from_reqs:
            self._apply_customization_durations(applied_customizations_from_reqs)

        # Use project_start_date from argument or config
        if project_start_date is None:
            project_start_date = datetime.strptime(config.PROJECT_START_DATE_STR, '%Y-%m-%d')
        self._calculate_task_dates(project_start_date)

    # --- Internal Helper Methods (Loading/Processing) ---
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

    def _load_tasks(self, file_path: Path, project_requirements_data: Optional[List[Dict[str, Any]]] = None) -> List[Task]:
        """
        Reads tasks from a semicolon-delimited CSV file, handles task duplication based on project requirements,
        and re-wires dependencies accordingly.
        """
        try:
            df = pd.read_csv(file_path, delimiter=';')
            df['strategy'] = df['strategy'].fillna('')
            df.fillna('', inplace=True)

            task_type_cache = {}
            base_tasks: List[Task] = []

            for _, row in df.iterrows():
                description = row['document_type']
                strategy = row['strategy'] if row['strategy'] else None

                cache_key = (description, strategy)
                if cache_key not in task_type_cache:
                    task_type_cache[cache_key] = TaskType(description=description, strategy=strategy)
                
                current_task_type = task_type_cache[cache_key]
                task_id = int(row['document_id'])
                part_num = str(row['document_part_number'])

                # Store original successors_str to re-parse later after potential ID re-mapping
                successors_str = row['successors']

                task = Task(
                    id=task_id,
                    part_number=part_num,
                    name=row['document_name'],
                    successors_str=successors_str, # Store original string
                    task_type=current_task_type
                )
                base_tasks.append(task)
            
            # Build initial ID to Task map for base tasks for successor resolution
            base_task_id_map = {task.id: task for task in base_tasks}
            for task in base_tasks:
                task.successors_ids = task._parse_successor_ids(task.successors_str)
                # These will be cleared and rebuilt later for final_tasks
                task.resolve_successors(base_task_id_map)
            
            for task in base_tasks:
                for successor_task in task.successors_tasks:
                    successor_task.predecessors.append(task)

            self._next_task_id = max(t.id for t in base_tasks) + 1 if base_tasks else 1
            
            # Map original ID to list of new IDs (could be just itself, or multiple variants). Globally tracks all mappings.
            original_id_to_final_ids_map: Dict[int, List[int]] = {}
            # Map part_number to its base tasks (there might be multiple tasks for one part_number in deliverable_structure, although unlikely for 60010)
            base_tasks_by_part_number: Dict[str, List[Task]] = {}
            for task in base_tasks:
                if task.part_number not in base_tasks_by_part_number:
                    base_tasks_by_part_number[task.part_number] = []
                base_tasks_by_part_number[task.part_number].append(task)

            part_number_to_extra_args: Dict[str, List[Dict[str, Any]]] = {}
            if project_requirements_data:
                for entry in project_requirements_data:
                    milestone_customizations = entry.get('customizations', {}) # Get milestone-level customizations
                    if 'extra_args' in entry:
                        for arg_entry in entry['extra_args']:
                            if isinstance(arg_entry, dict):
                                # Original format: {"part_number": "60010", "customizations": {"color": "red"}}
                                full_part_number_from_arg = str(arg_entry['part_number']) # This is "60010.1"
                                base_pn_for_lookup = full_part_number_from_arg.split('.')[0] # This is "60010"

                                if base_pn_for_lookup not in part_number_to_extra_args:
                                    part_number_to_extra_args[base_pn_for_lookup] = []
                                custom_from_arg = arg_entry.get('customizations', {})
                                if custom_from_arg:
                                    variant_customs = custom_from_arg
                                else:
                                    variant_customs = milestone_customizations
                                part_number_to_extra_args[base_pn_for_lookup].append({
                                    "part_number": full_part_number_from_arg, # Store "60010.1" here
                                    "customizations": variant_customs
                                })
                            elif isinstance(arg_entry, str):
                                # New format: "60010.1"
                                full_part_number = arg_entry
                                base_pn_for_lookup = arg_entry.split('.')[0] # e.g., "60010"
                                
                                if base_pn_for_lookup not in part_number_to_extra_args:
                                    part_number_to_extra_args[base_pn_for_lookup] = []
                                # Append an entry for the specific variant, inheriting milestone customizations
                                part_number_to_extra_args[base_pn_for_lookup].append({
                                    "part_number": full_part_number, # Store the full part_number.N
                                    "customizations": milestone_customizations # Inherit all milestone customizations
                                })

            # Dictionary to store the final tasks, mapped by their new IDs
            final_task_map: Dict[int, Task] = {}
            # Map original ID to list of new IDs (could be just itself, or multiple variants). Globally tracks all mappings.
            original_id_to_final_ids_map: Dict[int, List[int]] = {}
            # Keep track of which original tasks have been "consumed" by a duplication process
            # (either added as original or as a duplicated variant, or as a non-duplicated predecessor)
            consumed_original_task_ids: Set[int] = set()

            self._next_task_id = max(t.id for t in base_tasks) + 1 if base_tasks else 1

            # --- Recursive duplication helper function ---
            # This function will duplicate a task and its relevant predecessors for a specific variant chain.
            # It returns the newly duplicated task for the given variant.
            # `duplication_context` stores original_id -> new_variant_task mapping for the current specific variant's chain.
            # `current_variant_customizations` are the customizations to apply to this specific variant chain.
            # `original_task_map` is a map of original IDs to original Task objects for lookups.
            def _recursively_duplicate_task_and_ancestry(
                original_task: Task,
                variant_suffix: str, # e.g., ".1", ".2"
                current_variant_customizations: Dict[str, Any],
                duplication_context: Dict[int, Task], # original_id -> new_variant_task for this variant's chain
                original_task_map: Dict[int, Task] # All original tasks by ID
            ) -> Task:
                # If this original_task has already been duplicated for this specific variant chain, return it.
                if original_task.id in duplication_context:
                    return duplication_context[original_task.id]

                # If we reach here, it means original_task is part of the component to be duplicated.
                new_task = copy.deepcopy(original_task)
                new_task.id = self._next_task_id
                self._next_task_id += 1

                # Apply variant-specific attributes
                new_task.part_number = f"{original_task.part_number}{variant_suffix}" # CHANGED
                new_task.variant_name = variant_suffix.lstrip('.') # SET VARIANT NAME
                new_task.variant_customizations = current_variant_customizations

                # Reset predecessor/successor lists, they will be rebuilt recursively
                new_task.predecessors = []
                new_task.successors_tasks = [] # Will be rebuilt later by the main re-wiring logic

                # Store this duplicated task in the context and global mapping
                duplication_context[original_task.id] = new_task
                if original_task.id not in original_id_to_final_ids_map:
                    original_id_to_final_ids_map[original_task.id] = []
                original_id_to_final_ids_map[original_task.id].append(new_task.id)
                # Mark the *original* task ID as consumed globally so it's not processed again as a root or unique task
                consumed_original_task_ids.add(original_task.id)

                # Recursively duplicate predecessors and re-wire
                for original_predecessor_obj in original_task.predecessors: # Iterate through actual Task objects
                    duplicated_predecessor = _recursively_duplicate_task_and_ancestry(
                        original_predecessor_obj, # Pass the Task object
                        variant_suffix, # PASS THE VARIANT SUFFIX
                        current_variant_customizations,
                        duplication_context,
                        original_task_map
                    )
                    new_task.predecessors.append(duplicated_predecessor)
                    # Note: Successors of duplicated_predecessor will be set in the final re-wiring step

                return new_task

            # --- Process tasks for duplication ---
            # All tasks that are explicitly defined in extra_args (e.g., 60010)
            # and their full predecessor chains will be duplicated.

            for base_task in base_tasks:
                # If this original task has already been consumed as part of a *previous* duplication chain
                # (i.e., it was a predecessor of another root that was duplicated earlier in this loop), skip it.
                if base_task.id in consumed_original_task_ids:
                    continue

                if base_task.part_number in part_number_to_extra_args:
                    # This task is a "root" for duplication
                    
                    for extra_arg_entry in part_number_to_extra_args[base_task.part_number]:
                        duplication_context: Dict[int, Task] = {} # New context for each variant's chain
                        
                        root_variant_suffix = ""
                        # Determine variant suffix from extra_arg_entry["part_number"]
                        # If extra_arg_entry["part_number"] is "60010.1", suffix is ".1"
                        if '.' in extra_arg_entry["part_number"]:
                            root_variant_suffix = "." + extra_arg_entry["part_number"].split('.')[-1]
                        else:
                            # If no suffix in the extra_arg, use a default empty suffix or raise an error
                            # For now, let's assume extra_args will always have a suffix for variants
                            pass # If extra_arg_entry["part_number"] is just "60010", it means original task.
                                 # We need to make sure this path is not taken if we only want to duplicate for variants.
                        
                        duplicated_root_task = _recursively_duplicate_task_and_ancestry(
                            base_task,
                            root_variant_suffix, # PASS THE VARIANT SUFFIX
                            extra_arg_entry["customizations"],
                            duplication_context,
                            base_task_id_map # Pass the map of all original tasks
                        )
                        # All tasks in this specific variant's chain are now in duplication_context.
                        for new_variant_task in duplication_context.values():
                            final_task_map[new_variant_task.id] = new_variant_task
                            # consumed_original_task_ids is updated inside the recursive function (original_task.id)

                else:
                    # This base task is not explicitly duplicated. Add it to final tasks.
                    if base_task.id not in consumed_original_task_ids:
                        # This original task was never touched by any duplication process, add it as is
                        final_task_map[base_task.id] = base_task
                        original_id_to_final_ids_map[base_task.id] = [base_task.id]
                        consumed_original_task_ids.add(base_task.id) # Mark as consumed

            # Convert final_task_map values to a list for the rest of the processing
            final_tasks = list(final_task_map.values())



            # --- Re-wiring Dependencies for final_tasks ---
            # Step 1: Update successors_ids for all tasks in final_tasks based on the duplication map
            for task in final_tasks:
                new_successors_ids = set()
                for original_successor_id in task.successors_ids:
                    if original_successor_id in original_id_to_final_ids_map:
                        # Add all new variant IDs if the successor was duplicated
                        new_successors_ids.update(original_id_to_final_ids_map[original_successor_id])
                    else:
                        # Successor was not duplicated or its ID is not in our mapping, keep its ID
                        new_successors_ids.add(original_successor_id)
                task.successors_ids = sorted(list(new_successors_ids)) # Keep consistent order

            # Step 2: Rebuild task_id_to_final_task_map with only the tasks that made it into final_tasks
            task_id_to_final_task_map = {task.id: task for task in final_tasks}

            # Step 3: Clear and rebuild all successors_tasks and predecessors lists based on updated successors_ids
            # This handles both removed tasks and re-routed dependencies due to duplication.
            for task in final_tasks:
                task.successors_tasks.clear()
                task.predecessors.clear()

            for task in final_tasks:
                for successor_id in task.successors_ids:
                    if successor_id in task_id_to_final_task_map:
                        successor_task = task_id_to_final_task_map[successor_id]
                        task.successors_tasks.append(successor_task)
                        successor_task.predecessors.append(task)
                    else:
                        # This can happen if a successor was removed due to 0 duration earlier in the process
                        # or if it was an original task that was removed due to duplication and its variants
                        # don't exist (e.g., if extra_args was empty for that part_number, which it shouldn't be).
                        print(f"Warning: Successor ID {successor_id} for Task {task.id} (part_num {task.part_number}) not found in final tasks after re-wiring. Likely removed.")

            return final_tasks

        except FileNotFoundError:
            print(f"Error: File not found at {file_path}")
            return []
        except Exception as e:
            print(f"An error occurred in _load_tasks: {e}")
            raise # Re-raise for debugging purposes


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
            task.successors_tasks.clear()
            task.predecessors.clear() 

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
                    task_type=TaskType(description=TaskType.DRAWING.description, strategy="consolidated")
                )
                self._next_task_id += 1
                
                max_duration = 0
                for dt in drawing_tasks:
                    if dt.duration > max_duration:
                        max_duration = dt.duration
                    original_drawing_id_to_consolidated_id_map[dt.id] = consolidated_task.id
                consolidated_task.duration = max_duration
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
            data = []
            for task in self.tasks:
                data.append({
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
                    'Variant Name': task.variant_name if task.variant_name else '',
                    'Variant Customizations': json.dumps(task.variant_customizations) if task.variant_customizations else '{}'
                })

            df = pd.DataFrame(data)
            df.to_csv(file_path, index=False)
            print(f"Successfully exported {len(self.tasks)} tasks to {file_path}")

        except Exception as e:
            print(f"Error exporting tasks to CSV: {e}")