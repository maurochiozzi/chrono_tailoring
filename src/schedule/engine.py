from typing import List, Dict, Tuple, Set
from datetime import datetime, date
import heapq

from src.core.models import Task
from src.core.time_calc import get_next_working_time

def calculate_task_dates(
    tasks: List[Task], 
    project_start_date: datetime, 
    holidays: Set[date],
    num_resources: int
) -> None:
    """
    Calculates the initiation and end dates for all tasks in the given list,
    respecting dependencies, working days/hours, and resource availability limits.
    """
    if not tasks:
        return

    # --- Cycle Detection (Kahn's Algorithm) ---
    in_degree_check: Dict[int, int] = {task.id: 0 for task in tasks}
    for task in tasks:
        for successor in task.successors_tasks:
            if successor.id in in_degree_check:
                in_degree_check[successor.id] += 1
    
    zero_in_degree_queue = [tid for tid, degree in in_degree_check.items() if degree == 0]
    visited_count = 0
    
    while zero_in_degree_queue:
        u_id = zero_in_degree_queue.pop(0)
        visited_count += 1
        u_task = next((t for t in tasks if t.id == u_id), None)
        if u_task:
            for successor in u_task.successors_tasks:
                if successor.id in in_degree_check:
                    in_degree_check[successor.id] -= 1
                    if in_degree_check[successor.id] == 0:
                        zero_in_degree_queue.append(successor.id)

    if visited_count != len(tasks):
        raise RuntimeError(f"Circular dependency detected in project schedule! "
                           f"Could only resolve {visited_count} out of {len(tasks)} tasks.")

    # --- Resource Allocation & Scheduling Engine ---
    in_degree: Dict[int, int] = {task.id: 0 for task in tasks}
    task_map: Dict[int, Task] = {task.id: task for task in tasks}

    for task in tasks:
        for successor in task.successors_tasks:
            if successor.id not in in_degree:
                print(f"Warning: Successor {successor.id} of task {task.id} not found. Skipping.")
                continue
            in_degree[successor.id] += 1

    # Priority queue for ready tasks: (earliest_start_time, task_id)
    ready_tasks_pq: List[Tuple[datetime, int]] = []

    earliest_start_from_predecessors: Dict[int, datetime] = {
        task.id: project_start_date for task in tasks
    }

    # Identify initially ready tasks (in_degree 0)
    for task in tasks:
        if in_degree[task.id] == 0:
            task_start_time = get_next_working_time(project_start_date, 0, holidays)
            heapq.heappush(ready_tasks_pq, (task_start_time, task.id))
    
    # Track currently active tasks: (finish_time, task_id)
    active_tasks_finish_times: List[Tuple[datetime, int]] = []
    num_active_resources = 0
    completed_tasks_count = 0
    
    while completed_tasks_count < len(tasks):
        next_ready_event_time = ready_tasks_pq[0][0] if ready_tasks_pq else datetime.max
        next_finish_event_time = active_tasks_finish_times[0][0] if active_tasks_finish_times else datetime.max

        if num_active_resources == num_resources:
            current_event_time = next_finish_event_time
        else:
            current_event_time = min(next_ready_event_time, next_finish_event_time)

        if current_event_time == datetime.max:
            raise RuntimeError(
                f"Scheduler engine got stuck. "
                f"Remaining units: {len(tasks) - completed_tasks_count}. "
            )
        
        # 1. Process tasks finishing at or before current_event_time
        while active_tasks_finish_times and active_tasks_finish_times[0][0] <= current_event_time:
            finished_time, finished_task_id = heapq.heappop(active_tasks_finish_times)
            num_active_resources -= 1
            
            finished_task = task_map[finished_task_id]
            completed_tasks_count += 1
            
            for successor in finished_task.successors_tasks:
                if successor.id not in earliest_start_from_predecessors:
                    continue
                earliest_start_from_predecessors[successor.id] = max(
                    earliest_start_from_predecessors[successor.id],
                    finished_task.end_date
                )
                in_degree[successor.id] -= 1
                if in_degree[successor.id] == 0:
                    successor_ready_time = get_next_working_time(earliest_start_from_predecessors[successor.id], 0, holidays)
                    heapq.heappush(ready_tasks_pq, (successor_ready_time, successor.id))
        
        # 2. Schedule new tasks
        while ready_tasks_pq and num_active_resources < num_resources:
            task_earliest_start_candidate, task_id_to_schedule = heapq.heappop(ready_tasks_pq)
            task_to_schedule = task_map[task_id_to_schedule]
            
            if task_earliest_start_candidate > current_event_time:
                heapq.heappush(ready_tasks_pq, (task_earliest_start_candidate, task_id_to_schedule))
                break
            
            actual_start_time = max(
                earliest_start_from_predecessors[task_to_schedule.id],
                current_event_time
            )
            
            task_to_schedule.init_date = get_next_working_time(actual_start_time, 0, holidays)
            task_to_schedule.end_date = get_next_working_time(task_to_schedule.init_date, task_to_schedule.duration_minutes, holidays)
            
            heapq.heappush(active_tasks_finish_times, (task_to_schedule.end_date, task_to_schedule.id))
            num_active_resources += 1

    # Final pass to ensure all tasks have dates (defense against edge cases)
    for task in tasks:
        if task.init_date is None:
            task.init_date = get_next_working_time(project_start_date, 0, holidays)
            task.end_date = get_next_working_time(task.init_date, task.duration_minutes, holidays)
    
    tasks.sort(key=lambda t: t.init_date if t.init_date else datetime.min)
