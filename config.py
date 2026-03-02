# config.py

from pathlib import Path

# Define file paths
# These paths will be used throughout the project.
# Using Path objects makes path manipulation cleaner.
BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / 'input'

TASK_CSV_PATH = INPUT_DIR / 'deliverable_structure.csv'
CUSTOMIZATION_OVERVIEW_CSV_PATH = INPUT_DIR / 'customization_overview.csv'
PROJECT_REQUIREMENTS_PATH = INPUT_DIR / 'project_requirements.txt'
HOLIDAYS_PATH = INPUT_DIR / 'holidays.csv'
OUTPUT_DIR = BASE_DIR / 'output'

# Other configuration settings can be added here
PROJECT_START_DATE_STR = "2026-02-08"

# Debugging flag
DEBUG = True