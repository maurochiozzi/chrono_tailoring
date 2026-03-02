"""
Unit tests for src/schedule/loader.py
Tests CSV parsing for tasks, holidays, customization types, and duration lookup.
"""
import pytest
import tempfile
import csv
from pathlib import Path
from src.schedule.loader import (
    load_raw_tasks_from_csv,
    load_holidays,
    load_customization_types,
    read_customization_duration,
)


def _write_csv(path: Path, headers: list, rows: list, delimiter=';'):
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(headers)
        writer.writerows(rows)


class TestLoadHolidays:
    def test_loads_valid_dates(self, tmp_path):
        p = tmp_path / 'holidays.csv'
        p.write_text("2026-01-01\n2026-04-06\n")
        from datetime import date
        result = load_holidays(p)
        assert date(2026, 1, 1) in result
        assert date(2026, 4, 6) in result

    def test_skips_malformed_lines(self, tmp_path):
        p = tmp_path / 'holidays.csv'
        p.write_text("not-a-date\n2026-01-01\n")
        result = load_holidays(p)
        from datetime import date
        assert len(result) == 1
        assert date(2026, 1, 1) in result

    def test_returns_empty_set_for_missing_file(self, tmp_path):
        result = load_holidays(tmp_path / 'nonexistent.csv')
        assert result == set()


class TestLoadRawTasksFromCsv:
    def _make_delivery_csv(self, tmp_path, rows=None):
        p = tmp_path / 'deliverable_structure.csv'
        headers = ['document_id', 'document_type', 'document_part_number',
                   'document_name', 'successors', 'strategy']
        if rows is None:
            rows = [
                ['1', 'release', '70000', 'storage_cabinet', '2', ''],
                ['2', 'drawing', '70000', 'storage_cabinet', '1', '1'],
                ['3', 'part_model', '70000', 'storage_cabinet', '1', ''],
            ]
        _write_csv(p, headers, rows)
        return p

    def test_loads_correct_number_of_tasks(self, tmp_path):
        p = self._make_delivery_csv(tmp_path)
        tasks = load_raw_tasks_from_csv(p)
        assert len(tasks) == 3

    def test_task_ids_match_csv(self, tmp_path):
        p = self._make_delivery_csv(tmp_path)
        tasks = load_raw_tasks_from_csv(p)
        ids = {t.id for t in tasks}
        assert ids == {1, 2, 3}

    def test_task_names_parsed(self, tmp_path):
        p = self._make_delivery_csv(tmp_path)
        tasks = load_raw_tasks_from_csv(p)
        names = {t.name for t in tasks}
        assert 'storage_cabinet' in names

    def test_task_type_description_set(self, tmp_path):
        p = self._make_delivery_csv(tmp_path)
        tasks = load_raw_tasks_from_csv(p)
        types = {t.type.description for t in tasks}
        assert 'release' in types
        assert 'drawing' in types

    def test_successors_ids_parsed(self, tmp_path):
        p = self._make_delivery_csv(tmp_path)
        tasks = load_raw_tasks_from_csv(p)
        task_map = {t.id: t for t in tasks}
        # Task 1 has successor 2
        assert 2 in task_map[1].successors_ids

    def test_predecessor_back_links_built(self, tmp_path):
        p = self._make_delivery_csv(tmp_path)
        tasks = load_raw_tasks_from_csv(p)
        task_map = {t.id: t for t in tasks}
        # Task 2 should have task 1 as a predecessor
        pred_ids = {p.id for p in task_map[2].predecessors}
        assert 1 in pred_ids

    def test_returns_empty_list_for_missing_file(self, tmp_path):
        result = load_raw_tasks_from_csv(tmp_path / 'no_such_file.csv')
        assert result == []

    def test_duration_loaded_from_std_duration_column(self, tmp_path):
        p = tmp_path / 'deliverable_structure.csv'
        headers = ['document_id', 'document_type', 'document_part_number',
                   'document_name', 'successors', 'strategy', 'std_duration']
        # std_duration = 2 (hours) → 120 minutes
        rows = [['1', 'drawing', '70000', 'cabinet', '0', '1', '2']]
        _write_csv(p, headers, rows)
        tasks = load_raw_tasks_from_csv(p)
        assert len(tasks) == 1
        assert tasks[0].duration_minutes == 120


class TestReadCustomizationDuration:
    def _make_customization_csv(self, tmp_path, name='customization_length.csv'):
        p = tmp_path / name
        headers = ['id', 'document_part_number', 'document_name',
                   'drawing_st', 'release_st', 'part_model_st', 'part_list_st']
        rows = [
            ['1', '60010', 'assembly_door', '60', '120', '60', '10'],
            ['2', '60011', 'painted_door', '90', '150', '90', '20'],
        ]
        _write_csv(p, headers, rows)
        return p

    def test_returns_duration_for_known_task(self, tmp_path):
        p = self._make_customization_csv(tmp_path)
        result = read_customization_duration(
            p, 'length', '576', 'assembly_door', 'drawing'
        )
        assert result == 60

    def test_returns_none_for_unknown_task(self, tmp_path):
        p = self._make_customization_csv(tmp_path)
        result = read_customization_duration(
            p, 'length', '576', 'nonexistent_part', 'drawing'
        )
        assert result is None

    def test_returns_none_for_missing_file(self, tmp_path):
        result = read_customization_duration(
            tmp_path / 'no_such.csv', 'length', '576', 'assembly_door', 'drawing'
        )
        assert result is None
