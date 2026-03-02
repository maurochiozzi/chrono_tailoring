"""
Unit tests for src/core/models.py
Tests Task, TaskType, CustomizationType, and ProjectMilestone classes.
"""
import pytest
from src.core.models import Task, TaskType, CustomizationType, ProjectMilestone


class TestTaskType:
    def test_basic_creation(self):
        tt = TaskType(description="drawing", strategy="1")
        assert tt.description == "drawing"
        assert tt.strategy == "1"

    def test_no_strategy_defaults_to_none(self):
        tt = TaskType(description="release")
        assert tt.strategy is None

    def test_different_types_are_distinct(self):
        tt1 = TaskType(description="drawing")
        tt2 = TaskType(description="release")
        assert tt1.description != tt2.description


class TestTask:
    def _make_task(self, **kwargs):
        defaults = dict(
            id=1,
            part_number="60010",
            name="assembly_door",
            task_type=TaskType(description="drawing"),
            duration_minutes=60
        )
        defaults.update(kwargs)
        return Task(**defaults)

    def test_basic_creation(self):
        t = self._make_task()
        assert t.id == 1
        assert t.part_number == "60010"
        assert t.name == "assembly_door"
        assert t.duration_minutes == 60

    def test_successors_str_parsed(self):
        t = self._make_task(successors_str="2,3,4")
        assert t.successors_ids == [2, 3, 4]

    def test_empty_successors_str(self):
        t = self._make_task(successors_str="")
        assert t.successors_ids == []

    def test_nan_successors_str(self):
        # CSV NaN values come as float 'nan' strings from pandas
        t = self._make_task(successors_str="nan")
        # _parse_successor_ids should gracefully skip non-digit items
        assert t.successors_ids == []

    def test_clone_produces_independent_copy(self):
        original = self._make_task(id=10, duration_minutes=120, successors_str="5,6")
        clone = original.clone()
        assert clone.id == original.id
        assert clone.duration_minutes == original.duration_minutes
        assert clone.successors_ids == original.successors_ids
        # Mutating clone does not affect original
        clone.id = 99
        clone.successors_ids.append(100)
        assert original.id == 10
        assert 100 not in original.successors_ids

    def test_clone_has_empty_predecessor_list(self):
        original = self._make_task()
        original.predecessors = [self._make_task(id=2)]
        clone = original.clone()
        # Clones should not inherit predecessor links — they're re-wired downstream
        assert clone.predecessors == []

    def test_milestone_id_default_is_none(self):
        t = self._make_task()
        assert t.milestone_id is None

    def test_repr_contains_id_and_name(self):
        t = self._make_task()
        r = repr(t)
        assert "id=1" in r
        assert "assembly_door" in r

    def test_resolve_successors_links_tasks(self):
        t1 = self._make_task(id=1, successors_str="2")
        t2 = self._make_task(id=2, successors_str="")
        task_map = {1: t1, 2: t2}
        t1.resolve_successors(task_map)
        assert t2 in t1.successors_tasks

    def test_resolve_successors_skips_unknown_ids(self):
        t1 = self._make_task(id=1, successors_str="999")
        task_map = {1: t1}
        t1.resolve_successors(task_map)
        assert t1.successors_tasks == []


class TestCustomizationType:
    def test_basic_creation(self):
        ct = CustomizationType(name="length", file_path="/input/customization_length.csv")
        assert ct.name == "length"
        assert ct.file_path == "/input/customization_length.csv"


class TestProjectMilestone:
    def test_basic_creation(self):
        m = ProjectMilestone(milestone_id=1, name="70015", milestone_data={})
        assert m.milestone_id == 1
        assert m.name == "70015"
        assert m.tasks == []

    def test_repr_shows_task_count(self):
        m = ProjectMilestone(milestone_id=1, name="70015", milestone_data={})
        r = repr(m)
        assert "num_tasks=0" in r
