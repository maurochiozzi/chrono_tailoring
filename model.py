# model.py

from typing import List, Optional, Dict, Any
from datetime import datetime

class Task:
    def __init__(self, id: int, part_number: str,
                 name: str, successors_str: str, task_type: 'TaskType',
                 variant_name: Optional[str] = None,
                 variant_customizations: Optional[Dict[str, Any]] = None,
                 milestone_id: Optional[Any] = None):
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
        self.milestone_id = milestone_id


    def _parse_successor_ids(self, successors_str: str) -> List[int]:
        """Parses a comma-separated string of successor IDs into a list of integers."""
        if not successors_str:
            return []
        return [int(s.strip()) for s in str(successors_str).split(',') if s.strip()]

    def __repr__(self):
        init_date_str = self.init_date.strftime('%Y-%m-%d %H:%M') if self.init_date else 'None'
        end_date_str = self.end_date.strftime('%Y-%m-%d %H:%M') if self.end_date else 'None'
        
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
    DRAWING: 'TaskType' # Forward declaration

    def __init__(self, description: str, strategy: Optional[str] = None):
        self.description = description
        self.strategy = strategy if strategy else None # Ensure empty string becomes None

    def __repr__(self):
        return f"TaskType(description='{self.description}', strategy='{self.strategy}')"

# Initialize predefined TaskType instances after class definition
TaskType.DRAWING = TaskType(description="drawing", strategy="1")
TaskType.MILESTONE = TaskType(description="milestone", strategy="1")

class CustomizationType:
    def __init__(self, name: str, file_path: str):
        self.name = name
        self.file_path = file_path
    
    def __repr__(self):
        return f"CustomizationType(name='{self.name}', file_path='{self.file_path}')"

class ProjectMilestone:
    def __init__(self, milestone_id: Any, name: str, milestone_data: Dict[str, Any]):
        self.milestone_id = milestone_id
        self.name = name
        self.milestone_data = milestone_data
        self.tasks: List[Task] = []

    def __repr__(self):
        return f"ProjectMilestone(id={self.milestone_id}, name='{self.name}', tasks_count={len(self.tasks)})"