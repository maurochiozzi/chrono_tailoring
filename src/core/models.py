from typing import List, Optional, Dict, Any, Set
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

# [Req: RF-02.5] — TaskType cached by (description, strategy) to avoid duplicate objects
class TaskType:
    """Represents the type of a task, optionally indicating a specialized mapping strategy.

    Attributes:
        description (str): The main classification of the task (e.g., 'release', 'drawing').
        strategy (Optional[str]): Used when a specific processing logic overrides standard behaviour (e.g., 'consolidated').
    """
    def __init__(self, description: str, strategy: Optional[str] = None):
        self.description = description
        self.strategy = strategy

# [Req: RF-06.1] — CustomizationType maps a customization name to its input CSV file path
@dataclass
class CustomizationType:
    """Maps a customization tag to its configuration file and cached dictionary data.

    Attributes:
        name (str): The unique name of the customization.
        file_path (Path): Path to the underlying CSV file.
        df (Optional[Any]): Internal hashed dictionary containing configuration logic.
    """
    name: str
    file_path: Path
    df: Optional[Any] = None

# [Req: RF-02.1, RF-03.4, RF-04.3] — Core domain object; duration_minutes stored in minutes; variant_name tracks part suffix
class Task:
    """Core domain object representing an individual deliverable or manufacturing operation.

    Attributes:
        id (int): Unique identifier for the task instance.
        part_number (str): Associated product or module code.
        name (str): Human-readable name of the task.
        task_type (TaskType): Classification and processing strategy for the task.
        successors_str (str): Raw string of successor IDs prior to resolution.
        variant_name (Optional[str]): Distinguishes tasks generated for particular product variants.
        variant_customizations (Optional[Dict[str, Any]]): Variable overrides applied during timeline building.
        milestone_id (Optional[Any]): The ID of the milestone this task belongs to.
        duration_minutes (int): The estimated time required to execute this operation (in minutes).
    """
    def __init__(self, id: int, part_number: str,
                 name: str, task_type: TaskType,
                 successors_str: str = "",
                 variant_name: Optional[str] = None,
                 variant_customizations: Optional[Dict[str, Any]] = None,
                 milestone_id: Optional[Any] = None,
                 duration_minutes: int = 10):
        self.id = int(id)
        self.part_number = part_number
        self.name = name
        self.successors_str = successors_str
        self.successors_ids = self._parse_successor_ids(successors_str)
        self.type = task_type
        self.successors_tasks: List['Task'] = []
        self.init_date: Optional[datetime] = None
        self.end_date: Optional[datetime] = None
        self.predecessors: List['Task'] = []
        self.duration_minutes: int = duration_minutes
        self.variant_name = variant_name
        self.variant_customizations = variant_customizations if variant_customizations is not None else {}
        self.milestone_id = milestone_id


    # [Req: RF-02.3, RNF-11] — Tolerates NaN, floats and non-numeric values in the successors field
    def _parse_successor_ids(self, successors_str: str) -> List[int]:
        """Parses a comma-separated string of successor IDs into a list of integers."""
        if not successors_str:
            return []
        if isinstance(successors_str, (int, float)):
             return [int(successors_str)]
        result = []
        for s in str(successors_str).split(','):
            s = s.strip()
            if s and s.lstrip('-').isdigit():
                result.append(int(s))
        return result

    def __repr__(self):
        init_date_str = self.init_date.strftime('%Y-%m-%d %H:%M') if self.init_date else 'None'
        end_date_str = self.end_date.strftime('%Y-%m-%d %H:%M') if self.end_date else 'None'
        
        repr_str = (f"Task(id={self.id}, type='{self.type.description}', "
                    f"name='{self.name}', part_number='{self.part_number}', "
                    f"successors_ids={self.successors_ids}, init_date='{init_date_str}', "
                    f"end_date='{end_date_str}', duration={self.duration_minutes}")
        if self.variant_name:
            repr_str += f", variant_name='{self.variant_name}'"
        if self.variant_customizations:
            repr_str += f", variant_customizations={self.variant_customizations}"
        repr_str += ")"
        return repr_str

    # [Req: RF-03, RF-04] — Shallow clone used when copying template tasks per milestone/variant
    def clone(self) -> 'Task':
        """Creates a shallow copy without duplicating the entire task graph."""
        new_task = Task(
            id=self.id,
            part_number=self.part_number,
            name=self.name,
            successors_str=self.successors_str,
            task_type=self.type,
            variant_name=self.variant_name,
            variant_customizations=self.variant_customizations.copy() if self.variant_customizations else {},
            milestone_id=self.milestone_id,
            duration_minutes=self.duration_minutes
        )
        # explicitly maintain old dependency pointers for cloning
        new_task.successors_ids = list(self.successors_ids)
        return new_task

    # [Req: RF-02.4, RF-03.6] — Materialises successor object references from IDs after graph re-wiring
    def resolve_successors(self, task_map: Dict[int, 'Task']):
        """
        Links this task's 'successors_tasks' list to the actual Task objects
        found in the provided task_map based on 'successors_ids'.
        """
        self.successors_tasks = []
        for s_id in self.successors_ids:
            if s_id in task_map:
                self.successors_tasks.append(task_map[s_id])
            else:
                pass


# [Req: RF-03.5] — Groups tasks under a milestone; milestone_id used for filtering in export/visualisation
class ProjectMilestone:
    """Groups a logical subset of tasks representing a major project milestone or deliverable.

    Attributes:
        milestone_id (Any): Unique identifier for this milestone phase.
        name (str): Display name representing the milestone objective.
        milestone_data (Dict[str, Any]): Dictionary of overrides and settings specific to this milestone group.
    """
    def __init__(self, milestone_id: Any, name: str, milestone_data: Dict[str, Any]):
        self.milestone_id = milestone_id
        self.name = name
        self.milestone_data = milestone_data
        self.tasks: List[Task] = []

    def __repr__(self):
        return f"ProjectMilestone(id={self.milestone_id}, name='{self.name}', num_tasks={len(self.tasks)})"
