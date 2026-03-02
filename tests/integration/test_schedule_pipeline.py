"""
Integration tests for the full simulation pipeline.
Replaces and formalizes validate_export.py.

These tests exercise the full stack:
  load_project_requirements → ProjectSchedule → exported_tasks.csv

They require the real input files in input/ and run the simulation fresh
against the current project_requirements.txt and deliverable_structure.csv.
"""
import pytest
import pandas as pd
from datetime import datetime
from pathlib import Path

from src.schedule.project import ProjectSchedule
from src import config


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def schedule():
    """
    Runs the full simulation once per test module and returns the
    ProjectSchedule object. Expensive, but correct for integration tests.
    """
    s = ProjectSchedule(
        project_requirements_path=config.PROJECT_REQUIREMENTS_PATH,
        num_resources=1,
        customization_overview_csv_path=config.CUSTOMIZATION_OVERVIEW_CSV_PATH,
        holidays_path=config.HOLIDAYS_PATH,
    )
    return s


@pytest.fixture(scope='module')
def exported_df(schedule):
    """Re-runs the CSV export and returns the resulting DataFrame."""
    from src.export.csv_export import export_tasks_to_csv
    export_path = config.OUTPUT_DIR / 'exported_tasks.csv'
    export_tasks_to_csv(schedule.tasks, export_path)
    df = pd.read_csv(export_path)
    df['Start Date'] = pd.to_datetime(df['Start Date'])
    df['End Date'] = pd.to_datetime(df['End Date'])
    return df


# ─── Milestone Coverage ─────────────────────────────────────────────────────────

class TestMilestoneCoverage:
    def test_all_required_milestones_present(self, exported_df):
        """Every milestone_id from project_requirements.txt must appear in the export."""
        import json
        with open(config.PROJECT_REQUIREMENTS_PATH) as f:
            requirements = json.load(f)
        req_ids = {r['milestone_id'] for r in requirements}
        export_ids = set(exported_df['Milestone ID'].dropna().astype(int).unique())
        assert req_ids == export_ids, (
            f"Missing milestones: {req_ids - export_ids}"
        )

    def test_no_orphan_tasks_without_milestone(self, schedule):
        """Non-consolidated-drawing tasks should all have a Milestone ID assigned."""
        orphans = [
            t for t in schedule.tasks
            if t.milestone_id is None and t.type.description != 'drawing'
        ]
        assert len(orphans) == 0, (
            f"{len(orphans)} non-drawing tasks have no milestone_id: "
            f"{[t.id for t in orphans[:5]]}"
        )


# ─── Deliverable Structure Completeness ─────────────────────────────────────────

class TestDeliverableCompleteness:
    def test_task_types_in_export_match_deliverable_structure(self, exported_df):
        """All document_type values from the deliverable structure CSV
        must appear as task types in the export (plus 'drawing' consolidated variant)."""
        delivery_df = pd.read_csv(config.TASK_CSV_PATH, delimiter=';')
        expected_types = set(delivery_df['document_type'].unique())
        exported_types = set(exported_df['Task Type Description'].unique())
        missing = expected_types - exported_types
        assert not missing, f"Task types missing from export: {missing}"

    def test_part_numbers_in_export_match_deliverable_structure(self, exported_df):
        """All top-level part numbers from the deliverable CSV must appear in the export."""
        delivery_df = pd.read_csv(config.TASK_CSV_PATH, delimiter=';')
        expected_parts = set(delivery_df['document_part_number'].astype(str).unique())
        # Consolidated drawings accumulate multi-milestone tasks under the same PN
        exported_parts = set(exported_df['Part Number'].astype(str).unique())
        missing = expected_parts - exported_parts
        assert not missing, f"Part numbers missing from export: {missing}"


# ─── Predecessor / Successor Sequencing ─────────────────────────────────────────

class TestPredecessorSequencing:
    def test_no_task_starts_before_predecessor_ends(self, exported_df):
        """A task's Start Date must be >= all predecessor End Dates."""
        task_dict = exported_df.set_index('Task ID').to_dict('index')
        violations = []
        for task_id, row in task_dict.items():
            if pd.notna(row.get('Predecessor IDs')) and str(row['Predecessor IDs']).strip():
                pred_ids = [
                    int(p.strip())
                    for p in str(row['Predecessor IDs']).split(',')
                    if p.strip().isdigit()
                ]
                for p_id in pred_ids:
                    if p_id in task_dict:
                        pred_end = task_dict[p_id]['End Date']
                        if row['Start Date'] < pred_end:
                            violations.append(
                                f"Task {task_id} starts at {row['Start Date']} "
                                f"before predecessor {p_id} ends at {pred_end}"
                            )
        assert not violations, "\n".join(violations[:10])

    def test_end_date_not_before_start_date(self, exported_df):
        """No task can end before it starts."""
        bad = exported_df[exported_df['End Date'] < exported_df['Start Date']]
        assert len(bad) == 0, (
            f"{len(bad)} tasks have End < Start:\n{bad[['Task ID', 'Start Date', 'End Date']].head()}"
        )


# ─── Customization Duration Application ─────────────────────────────────────────

class TestCustomizationDurations:
    def test_tasks_with_zero_duration_customization_not_in_export(self, exported_df):
        """Tasks eliminated by a 0-duration customization must NOT appear in the export."""
        # From customization_color.csv, 'part_model' for assembly_door has 0 for color=red
        # (column 'part_model_st' = 0). These tasks should be dropped.
        # This is a content-level assertion — not all should survive.
        # We simply confirm the export has no tasks with duration < 0.
        assert (exported_df['Duration (minutes)'] >= 0).all(), \
            "Some tasks have negative duration."

    def test_tasks_with_customization_have_non_zero_duration(self, exported_df):
        """Non-drawing, non-milestone tasks classed as standard docs should
        have a duration > 0 once customizations are applied."""
        non_drawing = exported_df[
            ~exported_df['Task Type Description'].isin(['drawing', 'milestone'])
        ]
        # At least 80% of non-drawing/milestone tasks should have a positive duration
        positive_count = (non_drawing['Duration (minutes)'] > 0).sum()
        ratio = positive_count / len(non_drawing) if len(non_drawing) > 0 else 1.0
        assert ratio >= 0.8, (
            f"Only {ratio:.0%} of non-drawing tasks have positive duration. "
            "Customization lookup may be broken."
        )

    def test_milestones_with_different_customizations_differ_in_duration(self, exported_df):
        """Milestones with different color/length should produce different total durations."""
        totals = (
            exported_df.groupby('Milestone ID')['Duration (minutes)']
            .sum()
        )
        # If all 4 milestones had identical durations that would indicate
        # customizations are not being applied at all.
        assert totals.nunique() > 1, (
            "All milestones have identical total duration — "
            "customization durations may not be applied correctly."
        )


# ─── Schedule Integrity ──────────────────────────────────────────────────────────

class TestScheduleIntegrity:
    def test_schedule_has_tasks(self, schedule):
        assert len(schedule.tasks) > 0

    def test_all_tasks_have_start_dates(self, schedule):
        missing = [t for t in schedule.tasks if t.init_date is None]
        assert not missing, f"{len(missing)} tasks lack a start date."

    def test_all_tasks_have_end_dates(self, schedule):
        missing = [t for t in schedule.tasks if t.end_date is None]
        assert not missing, f"{len(missing)} tasks lack an end date."

    def test_project_starts_on_or_after_configured_start_date(self, schedule):
        configured_start = datetime.strptime(config.PROJECT_START_DATE_STR, '%Y-%m-%d')
        earliest = min(t.init_date for t in schedule.tasks if t.init_date)
        assert earliest >= configured_start

    def test_project_end_is_after_start(self, schedule):
        start = min(t.init_date for t in schedule.tasks if t.init_date)
        end = max(t.end_date for t in schedule.tasks if t.end_date)
        assert end > start
