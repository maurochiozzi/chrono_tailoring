import pytest
from bs4 import BeautifulSoup
from src.core.models import Task, TaskType
from src.export.gantt_interactive import export_interactive_gantt

class TestInteractiveGanttExport:
    @pytest.fixture
    def sample_tasks(self):
        # Create mock TaskType for simplicity
        task_type_model = TaskType(description="part_model")
        task_type_drawing = TaskType(description="drawing")

        # Create a set of sample tasks
        # Task 1 -> Task 2 (critical path)
        # Task 1 -> Task 3 (non-critical)
        # Task 3 -> Task 4 (non-critical)

        task1 = Task(id=1, name="Task 1", duration_minutes=60, part_number="P1", task_type=task_type_model)
        task2 = Task(id=2, name="Task 2", duration_minutes=120, part_number="P1", task_type=task_type_model)
        task3 = Task(id=3, name="Task 3", duration_minutes=90, part_number="P2", task_type=task_type_model)
        task4 = Task(id=4, name="Task 4", duration_minutes=30, part_number="P2", task_type=task_type_model)
        
        # Manually set init_date and end_date for simplicity, ensuring they are not None
        from datetime import datetime, timedelta
        start_date = datetime(2026, 3, 1, 9, 0)
        task1.init_date = start_date
        task1.end_date = start_date + timedelta(minutes=task1.duration_minutes)

        task2.init_date = task1.end_date
        task2.end_date = task2.init_date + timedelta(minutes=task2.duration_minutes)

        task3.init_date = start_date + timedelta(minutes=30)
        task3.end_date = task3.init_date + timedelta(minutes=task3.duration_minutes)

        task4.init_date = task3.end_date
        task4.end_date = task4.init_date + timedelta(minutes=task4.duration_minutes)


        # Set predecessors and successors
        task1.successors = [task2.id, task3.id]
        task1.successors_tasks = [task2, task3]
        task2.predecessors = [task1] # This should be a Task object
        task2.predecessors_tasks = [task1]

        task3.predecessors = [task1] # This should be a Task object
        task3.predecessors_tasks = [task1]
        task3.successors = [task4.id]
        task3.successors_tasks = [task4]

        task4.predecessors = [task3] # This should be a Task object
        task4.predecessors_tasks = [task3]

        # Mark Task 1 and Task 2 as critical
        task1.is_critical = True
        task2.is_critical = True

        return [task1, task2, task3, task4]

    def _get_links_from_html(self, html_content, var_name):
        import re
        import json
        match = re.search(f'const {var_name}\\s*=\\s*(\\[.*?\\]);', html_content, re.DOTALL)
        if not match:
            return []
        return json.loads(match.group(1))

    def test_gantt_export_with_critical_arrows_only(self, tmp_path, sample_tasks):
        output_path = tmp_path / "gantt_critical.html"
        export_interactive_gantt(sample_tasks, output_path, show_task_arrows=False)

        html_content = output_path.read_text()
        critical_links = self._get_links_from_html(html_content, 'CRITICAL_LINKS')

        # Expect only critical path arrows: Task 1 -> Task 2
        assert len(critical_links) == 1
        assert critical_links[0]['from'] == 1
        assert critical_links[0]['to'] == 2

    def test_gantt_export_with_all_task_arrows(self, tmp_path, sample_tasks):
        output_path = tmp_path / "gantt_all_arrows.html"
        export_interactive_gantt(sample_tasks, output_path, show_task_arrows=True)

        html_content = output_path.read_text()
        all_links = self._get_links_from_html(html_content, 'ALL_TASK_LINKS')
        critical_links = self._get_links_from_html(html_content, 'CRITICAL_LINKS')

        # Expect all task arrows: Task 1 -> Task 2, Task 1 -> Task 3, Task 3 -> Task 4
        assert len(all_links) == 3
        assert len(critical_links) == 1