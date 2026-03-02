# config.py

from pathlib import Path

# Define file paths
# These paths will be used throughout the project.
# Using Path objects makes path manipulation cleaner.
BASE_DIR = Path(__file__).parent

TASK_CSV_PATH = BASE_DIR / 'deliverable_structure.csv'
CUSTOMIZATION_OVERVIEW_CSV_PATH = BASE_DIR / 'customization_overview.csv'
PROJECT_REQUIREMENTS_PATH = BASE_DIR / 'project_requirements.txt'
HOLIDAYS_PATH = BASE_DIR / 'holidays.csv'

# Other configuration settings can be added here
PROJECT_START_DATE_STR = "2026-02-08"

# Debugging flag
DEBUG = True