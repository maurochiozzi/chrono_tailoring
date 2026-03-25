from typing import List, Dict, Tuple, Set
from datetime import datetime, date
import heapq

from src.core.models import Task
from src.core.time_calc import get_next_working_time

# [Req: RF-10, RF-11, RF-12] — Main scheduling engine: cycle detection, resource-constrained dispatch, critical path
def calculate_task_dates(
    tasks: List[Task], 
    project_start_date: datetime, 
    holidays: Set[date],
    num_resources: int,
    working_start_hour: int = 8,
    working_end_hour: int = 16,
) -> None:
    """Calculates the initiation and end dates for all tasks in the given list,
    respecting dependencies, working days/hours, and resource availability limits.

    .. mermaid::

       graph TD
           A[Start] --> B["Reset Tasks Slack/Dates"]
           B --> C["Identify Ready Tasks<br/>(In-Degree = 0)"]
           C --> D{Ready Queue?}
           D -- Yes --> E["Pop task with min earliest_start"]
           E --> F{Resource Available?}
           F -- Yes --> G[Schedule Task]
           G --> H["Update Successors<br/>Decrement In-Degree"]
           H --> D
           F -- No --> I[Wait for next task finish]
           I --> D
           D -- No --> J["Backward Pass: Critical Path"]
           J --> End

    The scheduling process uses Kahn's algorithm for topological sorting.
    A task's **In-Degree** is the number of its unfinished predecessors. 
    When a task's in-degree reaches 0, it means all its dependencies are satisfied.

    Args:
        tasks (List[Task]): The overall project task sequence graph. These instances are mutated in place.
        project_start_date (datetime): Baseline timestamp for project progression.
        holidays (Set[date]): Days that will be entirely avoided when counting working time.
        num_resources (int): System-wide constraints setting parallel task limit execution.
        working_start_hour (int, optional): Factory shift start. Defaults to 8.
        working_end_hour (int, optional): Factory shift end. Defaults to 16.

    Raises:
        RuntimeError: If Kahn's algorithm detects cycles in the task dependencies.
        RuntimeError: If the scheduler inexplicably hangs without advancing all items.
    """
    if not tasks:
        return

    # --- Cycle Detection (Kahn's Algorithm) ---
    # [Req: RF-11, RF-11.1] — Kahn's algorithm: detect cycles before scheduling begins
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

    if visited_count != len(tasks):  # [Req: RF-11.2] — Fewer visited than total implies a cycle
        raise RuntimeError(f"Circular dependency detected in project schedule! "
                           f"Could only resolve {visited_count} out of {len(tasks)} tasks.")

    # --- Resource Allocation & Scheduling Engine ---
    # [Req: RF-10, RF-10.1, RF-10.2] — Resource allocation setup: in-degrees, ready-task heap, active-task heap
    in_degree: Dict[int, int] = {task.id: 0 for task in tasks}
    task_map: Dict[int, Task] = {task.id: task for task in tasks}

    for task in tasks:
        for successor in task.successors_tasks:
            if successor.id not in in_degree:
                print(f"Warning: Successor {successor.id} of task {task.id} not found. Skipping.")
                continue
            in_degree[successor.id] += 1

    # [Req: RF-10.1] — Priority queue for ready tasks ordered by earliest_start_time (heapq)
    ready_tasks_pq: List[Tuple[datetime, int]] = []

    earliest_start_from_predecessors: Dict[int, datetime] = {
        task.id: project_start_date for task in tasks
    }

    # Identify initially ready tasks (in_degree 0)
    for task in tasks:
        if in_degree[task.id] == 0:
            task_start_time = get_next_working_time(project_start_date, 0, holidays, working_start_hour, working_end_hour)
            heapq.heappush(ready_tasks_pq, (task_start_time, task.id))
    
    # [Req: RF-10.2] — Track currently active tasks and their finish times in a min-heap
    active_tasks_finish_times: List[Tuple[datetime, int]] = []
    num_active_resources = 0
    completed_tasks_count = 0
    
    # [Req: RF-10.3] — Event-driven loop: advance to the next relevant event (start or finish)
    while completed_tasks_count < len(tasks):
        next_ready_event_time = ready_tasks_pq[0][0] if ready_tasks_pq else datetime.max
        next_finish_event_time = active_tasks_finish_times[0][0] if active_tasks_finish_times else datetime.max

        if num_active_resources == num_resources:  # [Req: RF-10.4] — All slots used; must wait for a finish event
            current_event_time = next_finish_event_time
        else:
            current_event_time = min(next_ready_event_time, next_finish_event_time)

        if current_event_time == datetime.max:
            raise RuntimeError(
                f"Scheduler engine got stuck. "
                f"Remaining units: {len(tasks) - completed_tasks_count}. "
            )
        
        # [Req: RF-10.6] — Process finished tasks; propagate earliest_start to successors; release slots
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
                    successor_ready_time = get_next_working_time(earliest_start_from_predecessors[successor.id], 0, holidays, working_start_hour, working_end_hour)
                    heapq.heappush(ready_tasks_pq, (successor_ready_time, successor.id))
        
        # [Req: RF-10.4, RF-10.5] — Dispatch ready tasks up to resource limit; set init/end dates
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
            
            task_to_schedule.init_date = get_next_working_time(actual_start_time, 0, holidays, working_start_hour, working_end_hour)
            task_to_schedule.end_date = get_next_working_time(task_to_schedule.init_date, task_to_schedule.duration_minutes, holidays, working_start_hour, working_end_hour)
            
            heapq.heappush(active_tasks_finish_times, (task_to_schedule.end_date, task_to_schedule.id))
            num_active_resources += 1

    # [Req: RF-10.7] — Safety pass: assign dates to any task missed by the main loop (edge cases)
    for task in tasks:
        if task.init_date is None:
            task.init_date = get_next_working_time(project_start_date, 0, holidays, working_start_hour, working_end_hour)
            task.end_date = get_next_working_time(task.init_date, task.duration_minutes, holidays, working_start_hour, working_end_hour)
    
    # [Req: RF-12, RF-12.1, RF-12.2, RF-12.3, RF-12.4, RF-12.5, RF-12.6] — Critical Path: backward pass to compute slack and flag critical tasks
    if tasks:
        # [Req: RF-12.1] — project_end = latest end_date across all tasks
        project_end = max(t.end_date for t in tasks)
        
        # [Req: RF-12.2] — Terminal tasks (no successors) anchor the backward pass at project_end
        latest_end_times: Dict[int, datetime] = {}
        terminal_tasks = [t for t in tasks if not t.successors_tasks]
        for t in terminal_tasks:
            latest_end_times[t.id] = project_end
            
        # 3. Traverse backwards (reverse Kahn's) to find Latest End Times
        # We process tasks only after all their successors are processed.
        out_degree: Dict[int, int] = {t.id: len(t.successors_tasks) for t in tasks}
        
        # Queue initialized with terminal tasks
        ready_for_backward = [t.id for t in terminal_tasks]
        
        pred_map: Dict[int, List[Task]] = {t.id: [] for t in tasks}
        for task in tasks:
            for s in task.successors_tasks:
                if s.id in pred_map:
                    pred_map[s.id].append(task)
                    
        # [Req: RF-12.3] — Reverse Kahn traversal: propagate latest_end_times backwards via out_degree
        while ready_for_backward:
            curr_id = ready_for_backward.pop(0)
            curr_task = task_map[curr_id]
            curr_lf = latest_end_times.get(curr_id, curr_task.end_date)
            # Latest Start Time for current task
            curr_ls = curr_task.init_date + (curr_lf - curr_task.end_date) # Shift backwards by slack
            
            for p in pred_map[curr_id]:
                if p.id not in latest_end_times or latest_end_times[p.id] > curr_ls:
                    latest_end_times[p.id] = curr_ls
                
                out_degree[p.id] -= 1
                if out_degree[p.id] == 0:
                    ready_for_backward.append(p.id)
                    
        # 4. Mark tasks as critical if Early Finish == Late Finish
        # [Req: RF-12.4, RF-12.5] — slack in minutes; is_critical=True when slack==0
        for task in tasks:
            task.slack = max(0, int((latest_end_times.get(task.id, task.end_date) - task.end_date).total_seconds() / 60))
            task.is_critical = (task.slack == 0)

    # [Req: RF-12.6] — Final chronological sort used by all exporters
    tasks.sort(key=lambda t: t.init_date if t.init_date else datetime.min)
