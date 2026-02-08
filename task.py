import pandas as pd
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from collections import deque
from pathlib import Path
import copy
import json
import os
import heapq

class Task:
    def __init__(self, id: int, part_number: str,
                 name: str, successors_str: str, task_type: TaskType,
                 variant_name: Optional[str] = None,
                 variant_customizations: Optional[Dict[str, Any]] = None):
        self.id = int(id)
        self.part_number = part_number
        self.name = name
        self.successors_str = successors_str
        self.successors_ids = self._parse_successor_ids(successors_str)
        self.task_type = task_type
        self.successors_tasks: List['Task'] = []
        self.init_date: Optional[datetime] = None
        self.end_date: Optional[datetime] = None
        self.predecessors: List['Task'] = []
        self.duration: int = 10
        self.variant_name = variant_name
        self.variant_customizations = variant_customizations if variant_customizations is not None else {}


    def _parse_successor_ids(self, successors_str: str) -> List[int]:
        """Parses a comma-separated string of successor IDs into a list of integers."""
        if not successors_str:
            return []
        return [int(s.strip()) for s in str(successors_str).split(',') if s.strip()]

    def __repr__(self):
        init_date_str = self.init_date.strftime('%Y-%m-%d') if self.init_date else 'None'
        end_date_str = self.end_date.strftime('%Y-%m-%d') if self.end_date else 'None'
        
        repr_str = (f"Task(id={self.id}, type='{self.task_type.description}', "
                    f"name='{self.name}', part_number='{self.part_number}', "
                    f"successors_ids={self.successors_ids}, init_date='{init_date_str}', "
                    f"end_date='{end_date_str}', duration={self.duration}")
        if self.variant_name:
            repr_str += f", variant_name='{self.variant_name}'"
        if self.variant_customizations:
            repr_str += f", variant_customizations={self.variant_customizations}"
        repr_str += ")"
        return repr_str

    def resolve_successors(self, all_tasks_map: Dict[int, 'Task']):
        """Resolves successor IDs into actual Task objects."""
        for successor_id in self.successors_ids:
            if successor_id in all_tasks_map:
                self.successors_tasks.append(all_tasks_map[successor_id])
            else:
                print(f"Warning: Successor ID {successor_id} for Task {self.id} not found.")

class TaskType:
    def __init__(self, description: str, strategy: Optional[str] = None):
        self.description = description
        self.strategy = strategy if strategy else None # Ensure empty string becomes None

    def __repr__(self):
        return f"TaskType(description='{self.description}', strategy='{self.strategy}')"

class CustomizationType:
    def __init__(self, name: str, file_path: str):
        self.name = name
        self.file_path = file_path
    
    def __repr__(self):
        return f"CustomizationType(name='{self.name}', file_path='{self.file_path}')"

class ProjectSchedule:
    def __init__(self, task_csv_path: Optional[str] = None, tasks: Optional[List[Task]] = None, num_resources: int = 1, 
                 customization_overview_csv_path: Optional[str] = None, 
                 project_requirements_path: Optional[str] = None):
        self.num_resources = num_resources
        self.project_requirements_data: List[Dict[str, Any]] = []

        if project_requirements_path:
            self.project_requirements_data = self._load_project_requirements(project_requirements_path)

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

        if applied_customizations_from_reqs:
            self._apply_customization_durations(applied_customizations_from_reqs)
        
        today_str = "2026-02-08"
        today_date_obj = datetime.strptime(today_str, '%Y-%m-%d')
        self._calculate_task_dates(today_date_obj)

    def _load_project_requirements(self, file_path: str) -> List[Dict]:
        """
        Reads project requirements from a JSON file.
        """
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

    def _load_tasks(self, file_path: str, project_requirements_data: Optional[List[Dict[str, Any]]] = None) -> List[Task]:
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
                # Resolve successors for base tasks temporarily to capture predecessor relationships
                # These will be cleared and rebuilt later for final_tasks
                task.resolve_successors(base_task_id_map)
            
            for task in base_tasks:
                for successor_task in task.successors_tasks:
                    successor_task.predecessors.append(task)

            final_tasks: List[Task] = []
            next_task_id = max(t.id for t in base_tasks) + 1 if base_tasks else 1
            
            # Map original ID to list of new IDs (could be just itself, or multiple variants)
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

            next_task_id = max(t.id for t in base_tasks) + 1 if base_tasks else 1

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
                nonlocal next_task_id

                # If this original_task has already been duplicated for this specific variant chain, return it.
                if original_task.id in duplication_context:
                    return duplication_context[original_task.id]

                # If we reach here, it means original_task is part of the component to be duplicated.
                new_task = copy.deepcopy(original_task)
                new_task.id = next_task_id
                next_task_id += 1

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
            # Other tasks (like 70000 storage_cabinet) will be added as original tasks later
            # if they are not predecessors of duplicated tasks.

            for base_task in base_tasks:
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
                                 # Current logic is that extra_args *define* variants, so they should always have a suffix.
                        
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

            # Now, add any original tasks that were not part of any duplication chain (neither as root nor as predecessor)
            # and were not added to final_task_map by the recursive calls
            for base_task in base_tasks:
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
                new_successors_ids_for_this_task = set()
                for original_successor_id in task.successors_ids:
                    if original_successor_id in original_id_to_final_ids_map:
                        # Add all new variant IDs if the successor was duplicated
                        new_successors_ids_for_this_task.update(original_id_to_final_ids_map[original_successor_id])
                    else:
                        # Successor was not duplicated or its ID is not in our mapping, keep its ID
                        new_successors_ids_for_this_task.add(original_successor_id)
                task.successors_ids = sorted(list(new_successors_ids_for_this_task))

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


    def _read_customization_duration(self, customization_file_path: str, customization_name: str, customization_value: Any, task_name: str, task_type_description: str) -> Optional[int]:
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
                # print(f"Warning: Could not find a suitable task name column in {customization_file_path}. "
                #      f"Expected one of {possible_task_name_columns}. Skipping duration for this customization.")
                return None

            # Construct the specific _st column name using task_type_description
            st_column = f"{task_type_description}_st"
            
            if st_column not in df.columns:
                # print(f"Warning: Could not find '{st_column}' duration column in {customization_file_path}. Returning default duration (10).")
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
                    # If task name is found but no valid duration for the st_column
                    # This case should ideally not happen if st_column is always present and has numeric data
                    return 10 # Fallback to default duration if values are missing
            else:
                # If task_name itself is not found in the DataFrame
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


    def _load_customization_types(self, file_path: str) -> List[CustomizationType]:
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

    def _calculate_task_dates(self, today_date: datetime):
        """
        Calculates init_date and end_date for all tasks based on dependencies and duration.
        Implements a topological sort for scheduling with resource constraints using a min-heap.
        """
        in_degree = {task.id: len(task.predecessors) for task in self.tasks}
        tasks_by_id = {task.id: task for task in self.tasks}

        # Initialize resource availability times
        resource_free_time = [today_date] * self.num_resources

        # tasks_earliest_start_by_pred stores the earliest time a task can start due to predecessor completion
        tasks_earliest_start_by_pred = {task.id: today_date for task in self.tasks}

        # Priority queue for tasks ready to be scheduled: (earliest_start_time, task_id)
        ready_to_schedule_pq = [] 

        # Initialize ready_to_schedule_pq with tasks that have no predecessors
        for task in self.tasks:
            if in_degree[task.id] == 0:
                # Use today_date as the earliest start for tasks with no predecessors
                heapq.heappush(ready_to_schedule_pq, (today_date, task.id))

        scheduled_tasks_count = 0
        while ready_to_schedule_pq:
            earliest_start_time, task_id = heapq.heappop(ready_to_schedule_pq)
            task = tasks_by_id[task_id]

            # Find the earliest time a resource is available for this task
            earliest_resource_free_time = min(resource_free_time)
            assigned_resource_index = resource_free_time.index(earliest_resource_free_time)

            # Actual start time is max of when task is ready (pred completion) and when resource is free
            actual_start_time = max(earliest_start_time, earliest_resource_free_time)
            
            task.init_date = actual_start_time
            task.end_date = actual_start_time + timedelta(minutes=task.duration)
            task.resources = assigned_resource_index + 1 # Store which resource scheduled it

            # Update resource's free time
            resource_free_time[assigned_resource_index] = task.end_date
            scheduled_tasks_count += 1

            # Update successors
            for successor_task in task.successors_tasks:
                in_degree[successor_task.id] -= 1
                
                # Successor cannot start before current task finishes
                tasks_earliest_start_by_pred[successor_task.id] = max(
                    tasks_earliest_start_by_pred[successor_task.id],
                    task.end_date
                )

                if in_degree[successor_task.id] == 0:
                    heapq.heappush(ready_to_schedule_pq, (tasks_earliest_start_by_pred[successor_task.id], successor_task.id))
        
        # Diagnostic prints
        # print(f"DEBUG: Scheduled {scheduled_tasks_count} out of {len(self.tasks)} tasks.")
        if scheduled_tasks_count != len(self.tasks):
            print(f"Warning: Only {scheduled_tasks_count} out of {len(self.tasks)} tasks were scheduled. "
                  "This might indicate a problem with dependencies (e.g., cycles) or data.")
            for task in self.tasks:
                if task.init_date is None:
                    print(f"DEBUG: Unscheduled task: {task.name} (ID: {task.id})")
        self.scheduled_tasks_count = scheduled_tasks_count

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

def update_customization_overview_csv(file_path: str):
    """
    Reads customization_overview.csv, adds 'path' and 'status' columns,
    and writes the updated DataFrame back to the CSV.
    """
    try:
        df = pd.read_csv(file_path, delimiter=';')
        
        # Drop any unnamed columns that pandas might create (e.g., from trailing delimiters)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        
        # Add 'path' column
        df['path'] = df['customization_type'].apply(lambda name: f"customization_{name}.csv")
        
        # Add 'status' column
        df['status'] = df['path'].apply(lambda p: 'ok' if os.path.exists(p) else 'nok')
        
        # Write the updated DataFrame back to the CSV
        df.to_csv(file_path, sep=';', index=False)
        print(f"Updated {file_path} with 'path' and 'status' columns.")

    except FileNotFoundError:
        print(f"Error: Customization overview file not found at {file_path}")
    except Exception as e:
        print(f"An error occurred while updating {file_path}: {e}")

def export_tasks_to_mermaid_graph(tasks: List[Task], output_file_path: Optional[Path] = None, detail_level: str = 'full') -> str:
    """
    Generates a Mermaid flowchart (graph TD) representation of tasks.
    Can generate a detailed graph of individual tasks or a high-level graph based on task types.
    """
    mermaid_lines = ["graph TD"]

    if detail_level == 'full':
        node_styles = [] # Collect style directives here

        # Define color mapping for task types
        task_type_colors = {
            'release': 'fill:#F96',        # Orange
            'drawing': 'fill:#9F6',        # Light Green
            'part_model': 'fill:#69F',     # Light Blue
            'part_list': 'fill:#FC6',      # Yellow-Orange
            'milestone': 'fill:#C6F'       # Purple
        }

        # Define nodes with details and shapes for individual tasks
        for task in tasks:
            init_date_str = task.init_date.strftime('%Y-%m-%d') if task.init_date else 'None'
            end_date_str = task.end_date.strftime('%Y-%m-%d') if task.end_date else 'None'

            shape_map = {
                'release': '[[{}]]',
                'drawing': '({})',
                'part_model': '({})',
                'part_list': '{{{}}}',
                'milestone': '(( {} ))'
            }
            shape_template = shape_map.get(task.task_type.description, '[{}]')

            node_label_content = (f"{task.name}<br>"
                                  f"Type: {task.task_type.description}<br>"
                                  f"Part No: {task.part_number}<br>"
                                  f"Init: {init_date_str}<br>"
                                  f"End: {end_date_str}<br>"
                                  f"Dur: {task.duration}min")
            
            node_definition = f"{task.id}{shape_template.format(node_label_content)}"
            mermaid_lines.append(f"    {node_definition}")

            # Add style directive for the node
            color_style = task_type_colors.get(task.task_type.description, 'fill:#CCC') # Default light gray
            node_styles.append(f"    style {task.id} {color_style}")

        # Define edges (dependencies) for individual tasks
        for task in tasks:
            for successor_task in task.successors_tasks:
                mermaid_lines.append(f"    {task.id} --> {successor_task.id}")
        
        # Append node styles after all nodes and edges
        mermaid_lines.extend(node_styles)

    elif detail_level == 'type':
        # Collect unique task types and their connections
        unique_task_types = set()
        type_dependencies = set() # Stores (source_type_desc, target_type_desc)

        for task in tasks:
            source_type_desc = task.task_type.description
            unique_task_types.add(source_type_desc)

            for successor_task in task.successors_tasks:
                target_type_desc = successor_task.task_type.description
                unique_task_types.add(target_type_desc)
                type_dependencies.add((source_type_desc, target_type_desc))

        # Define nodes for each unique task type description
        def sanitize_id(text: str) -> str:
            return text.replace(" ", "_").replace("-", "_").replace(".", "").lower()

        for type_desc in sorted(list(unique_task_types)):
            sanitized_id = sanitize_id(type_desc)
            mermaid_lines.append(f"    {sanitized_id}[{type_desc}]")

        # Define edges between task types
        for source_type_desc, target_type_desc in sorted(list(type_dependencies)):
            sanitized_source_id = sanitize_id(source_type_desc)
            sanitized_target_id = sanitize_id(target_type_desc)
            mermaid_lines.append(f"    {sanitized_source_id} --> {sanitized_target_id}")

    else:
        raise ValueError(f"Unknown detail_level: {detail_level}. Expected 'full' or 'type'.")
            
    mermaid_syntax = "\n".join(mermaid_lines)

    if output_file_path:
        try:
            output_file_path.write_text(mermaid_syntax)
            print(f"Mermaid graph exported to: {output_file_path}")
        except Exception as e:
            print(f"Error exporting Mermaid graph to {output_file_path}: {e}")
            
    return mermaid_syntax

def export_tasks_to_mermaid_gantt(tasks: List[Task], output_file_path: Optional[Path] = None, detail_level: str = 'full') -> str:
    """
    Generates a Mermaid Gantt chart representation of tasks.
    Can generate a detailed chart of individual tasks or a high-level chart based on task types.
    """
    mermaid_lines = [
        "gantt",
        "    dateFormat  YYYY-MM-DD HH:mm",
        "    axisFormat %H:%M",
        "    title       Task Schedule Overview"
    ]

    # Define color mapping for task types
    task_type_colors = {
        'release': 'fill:#F96',        # Orange
        'drawing': 'fill:#9F6',        # Light Green
        'part_model': 'fill:#69F',     # Light Blue
        'part_list': 'fill:#FC6',      # Yellow-Orange
        'milestone': 'fill:#C6F'       # Purple
    }

    # Helper to sanitize ID for Mermaid class names (if needed for type-level)
    def sanitize_id(text: str) -> str:
        return text.replace(" ", "_").replace("-", "_").replace(".", "").lower()

    # SECTION: Full Detail Gantt Chart
    if detail_level == 'full':
        mermaid_lines.append("    section All Tasks")
        gantt_styles = [] # Collect style directives here

        for task in tasks:
            init_date_str = task.init_date.strftime('%Y-%m-%d %H:%M') if task.init_date else 'None'
            end_date_str = task.end_date.strftime('%Y-%m-%d %H:%M') if task.end_date else 'None'

            # Task label for the Gantt bar
            task_label = f"{task.name} ({task.part_number}) ({task.task_type.description})"

            # Gantt task syntax: Task Name :id, start_date, end_date
            if task.init_date and task.end_date:
                mermaid_lines.append(f"    {task_label} :{task.id}, {init_date_str}, {end_date_str}")
            else:
                # Fallback for tasks without calculated dates (should not happen with scheduling logic)
                mermaid_lines.append(f"    {task_label} :{task.id}, {init_date_str}, {task.duration}min") 

            # Add style directive for the task
            color_style = task_type_colors.get(task.task_type.description, 'fill:#CCC') # Default light gray
            gantt_styles.append(f"    style {task.id} {color_style},stroke:#333")

        # Append style directives
        mermaid_lines.extend(gantt_styles)

    # SECTION: Type Detail Gantt Chart
    elif detail_level == 'type':
        mermaid_lines.append("    section Task Types Overview")
        type_date_spans = {} # {type_desc: {'min_init': datetime, 'max_end': datetime}}

        for task in tasks:
            type_desc = task.task_type.description
            if type_desc not in type_date_spans:
                type_date_spans[type_desc] = {'min_init': task.init_date, 'max_end': task.end_date}
            
            # Update min_init_date for the type
            if task.init_date and (type_date_spans[type_desc]['min_init'] is None or task.init_date < type_date_spans[type_desc]['min_init']):
                type_date_spans[type_desc]['min_init'] = task.init_date
            
            # Update max_end_date for the type
            if task.end_date and (type_date_spans[type_desc]['max_end'] is None or type_date_spans[type_desc]['max_end'] < task.end_date):
                type_date_spans[type_desc]['max_end'] = task.end_date
        
        gantt_styles = [] # Collect style directives for types
        for type_desc in sorted(type_date_spans.keys()):
            type_info = type_date_spans[type_desc]
            type_id = sanitize_id(type_desc) # Use sanitized ID for Gantt bar
            min_init_str = type_info['min_init'].strftime('%Y-%m-%d %H:%M') if type_info['min_init'] else 'None'
            max_end_str = type_info['max_end'].strftime('%Y-%m-%d %H:%M') if type_info['max_end'] else 'None'

            if type_info['min_init'] and type_info['max_end']:
                mermaid_lines.append(f"    {type_desc} :{type_id}, {min_init_str}, {max_end_str}")
            else:
                mermaid_lines.append(f"    {type_desc} :{type_id}, {min_init_str}, 0min") # Fallback for types without calculated dates

            color_style = task_type_colors.get(type_desc, 'fill:#CCC') # Default light gray
            gantt_styles.append(f"    style {type_id} {color_style},stroke:#333")
        
        mermaid_lines.extend(gantt_styles)

    else:
        raise ValueError(f"Unknown detail_level: {detail_level}. Expected 'full' or 'type'.")
            
    mermaid_syntax = "\n".join(mermaid_lines)

    if output_file_path:
        try:
            output_file_path.write_text(mermaid_syntax)
            print(f"Mermaid Gantt chart exported to: {output_file_path}")
        except Exception as e:
            print(f"Error exporting Mermaid Gantt chart to {output_file_path}: {e}") # Corrected this line
            
    return mermaid_syntax

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    print("Warning: Matplotlib not found. Plotting will be skipped. Install with 'pip install matplotlib'.")
    MATPLOTLIB_AVAILABLE = False

def plot_resource_vs_duration(
    task_csv_path: str,
    customization_overview_csv_path: Optional[str] = None,
    max_resources: int = 10,
    output_plot_path: Optional[Path] = None,
    project_requirements_path: Optional[str] = None # Changed parameter
):
    """
    Runs scheduling for 1 to max_resources, collects total durations, and plots the results.
    """
    num_resources_list = []
    total_duration_minutes_list = []

    print(f"\n--- Analyzing Resource vs. Duration (1 to {max_resources} Resources) ---")
    
    for num_res in range(1, max_resources + 1):
        temp_project_schedule = ProjectSchedule(
            task_csv_path=task_csv_path, # Pass the original task CSV path
            num_resources=num_res,
            customization_overview_csv_path=customization_overview_csv_path,
            project_requirements_path=project_requirements_path # Ensure project requirements path is passed
        )
        
        # Diagnostic prints to show scheduling status for each resource run
        print(f"DEBUG (Resource Analysis): Scheduled {temp_project_schedule.scheduled_tasks_count} out of {len(temp_project_schedule.tasks)} tasks for {num_res} resources.")

        total_duration = temp_project_schedule.get_total_duration()
        if total_duration:
            # Convert timedelta to total minutes for plotting
            total_duration_minutes = total_duration.total_seconds() / 60
            num_resources_list.append(num_res)
            total_duration_minutes_list.append(total_duration_minutes)
            print(f"  Resources: {num_res}, Total Duration: {total_duration_minutes:.2f} minutes")
        else:
            print(f"  Resources: {num_res}, Could not calculate total duration.")

    if MATPLOTLIB_AVAILABLE:
        plt.figure(figsize=(10, 6))
        plt.plot(num_resources_list, total_duration_minutes_list, marker='o', linestyle='-')
        plt.title('Project Duration vs. Number of Resources')
        plt.xlabel('Number of Resources')
        plt.ylabel('Total Project Duration (minutes)')
        plt.grid(True)
        plt.xticks(num_resources_list)
        plt.tight_layout()

        if output_plot_path:
            plt.savefig(output_plot_path)
            print(f"Plot saved to: {output_plot_path}")
        else:
            plt.show()
    else:
        print("\nRaw Data (Number of Resources, Total Duration in Minutes):")
        for i in range(len(num_resources_list)):
            print(f"{num_resources_list[i]}, {total_duration_minutes_list[i]:.2f}")
