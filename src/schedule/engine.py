from typing import List, Dict, Tuple, Set, Optional
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
    free_slots: List[int] = list(range(1, num_resources + 1))  # resource slot IDs 1..N
    
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
            finished_time, finished_task_id, finished_slot = heapq.heappop(active_tasks_finish_times)
            num_active_resources -= 1
            free_slots.append(finished_slot)
            
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
            
            slot = free_slots.pop(0)
            task_to_schedule.resource_id = slot
            heapq.heappush(active_tasks_finish_times, (task_to_schedule.end_date, task_to_schedule.id, slot))
            num_active_resources += 1

    # [Req: RF-10.7] — Safety pass: assign dates to any task missed by the main loop (edge cases)
    fallback_slot = 1
    for task in tasks:
        if task.init_date is None:
            task.init_date = get_next_working_time(project_start_date, 0, holidays, working_start_hour, working_end_hour)
            task.end_date = get_next_working_time(task.init_date, task.duration_minutes, holidays, working_start_hour, working_end_hour)
            task.resource_id = fallback_slot
            fallback_slot = (fallback_slot % num_resources) + 1
    
    # [Req: RF-12, RF-12.1, RF-12.2, RF-12.3, RF-12.4, RF-12.5, RF-12.6] — Identify both Structural Critical Path (CPM) and Resource Critical Chain (CCPM)
    compute_critical_path(tasks)

    # [Req: RF-12.6] — Final chronological sort used by all exporters
    tasks.sort(key=lambda t: t.init_date if t.init_date else datetime.min)


def compute_structural_critical_path(tasks: List[Task]) -> List[Task]:
    """Computes the Structural Critical Path (CPM) through the DAG.
    
    This is the longest dependency path through blueprint tasks from root to milestone
    without resource queueing constraints.
    """
    if not tasks:
        return []

    memo: Dict[int, Tuple[int, datetime]] = {}
    next_node: Dict[int, Optional[Task]] = {}

    def get_longest(t: Task) -> Tuple[int, datetime]:
        if t.id in memo:
            return memo[t.id]
        if not getattr(t, 'successors_tasks', []):
            end_val = t.end_date if t.end_date else datetime.min
            memo[t.id] = (t.duration_minutes, end_val)
            next_node[t.id] = None
            return memo[t.id]

        best_val = (-1, datetime.min)
        best_succ = None
        for s in t.successors_tasks:
            dur, end = get_longest(s)
            val = (t.duration_minutes + dur, end)
            if val > best_val:
                best_val = val
                best_succ = s

        memo[t.id] = best_val
        next_node[t.id] = best_succ
        return memo[t.id]

    roots = [t for t in tasks if not getattr(t, 'predecessors', [])]
    if not roots:
        roots = tasks

    best_root = max(roots, key=lambda r: get_longest(r))
    path: List[Task] = []
    curr: Optional[Task] = best_root
    while curr:
        path.append(curr)
        curr = next_node.get(curr.id)

    return path


def compute_resource_critical_chain(tasks: List[Task]) -> List[Task]:
    """Computes the Resource Critical Chain (CCPM) by tracing the driving predecessors
    (both dependency blockers and resource queue blockers) backwards from the terminal task.
    
    This forms an unbroken, gap-free chain of tasks that directly determined the final project delivery date.
    """
    if not tasks:
        return []

    final_task = max(tasks, key=lambda t: t.end_date if t.end_date else datetime.min)
    chain: List[Task] = []
    visited: Set[int] = set()
    curr: Optional[Task] = final_task

    while curr and curr.id not in visited:
        visited.add(curr.id)
        chain.append(curr)

        candidates: List[Tuple[str, Task, datetime]] = []

        # Graph dependencies that finished before/at curr start
        for p in getattr(curr, 'predecessors', []):
            if p.end_date and p.end_date <= curr.init_date:
                candidates.append(('dependency', p, p.end_date))

        # Same resource tasks that finished before/at curr start
        res_tasks = [
            t for t in tasks
            if getattr(t, 'resource_id', None) == getattr(curr, 'resource_id', None)
            and t.end_date and t.end_date <= curr.init_date
            and t.id != curr.id
        ]
        if res_tasks:
            prev_res = max(res_tasks, key=lambda t: t.end_date)
            candidates.append(('resource', prev_res, prev_res.end_date))

        if not candidates:
            break

        candidates.sort(key=lambda x: x[2], reverse=True)
        curr = candidates[0][1]

    chain.reverse()
    return chain


def compute_critical_path(tasks: List[Task]) -> List[Task]:
    """Computes both Structural Critical Path (CPM) and Resource Critical Chain (CCPM).
    
    Sets the following boolean attributes on each task:
    - `is_structural_critical`: True if on the 11-step pure DAG dependency longest path.
    - `is_resource_critical`: True if on the continuous resource-constrained critical chain.
    - `is_critical`: Default critical flag (matches structural critical).
    """
    for t in tasks:
        t.is_critical = False
        t.is_structural_critical = False
        t.is_resource_critical = False
        t.slack = 0

    if not tasks:
        return []

    struct_path = compute_structural_critical_path(tasks)
    struct_set = {t.id for t in struct_path}

    res_chain = compute_resource_critical_chain(tasks)
    res_set = {t.id for t in res_chain}

    for t in tasks:
        t.is_structural_critical = (t.id in struct_set)
        t.is_resource_critical = (t.id in res_set)
        t.is_critical = t.is_structural_critical

    return struct_path
