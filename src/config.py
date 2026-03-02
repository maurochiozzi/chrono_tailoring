from pathlib import Path

# Paths are now relative to the project root (one level up from src)
BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / 'input'

TASK_CSV_PATH = INPUT_DIR / 'deliverable_structure.csv'
CUSTOMIZATION_OVERVIEW_CSV_PATH = INPUT_DIR / 'customization_overview.csv'
PROJECT_REQUIREMENTS_PATH = INPUT_DIR / 'project_requirements.txt'
HOLIDAYS_PATH = INPUT_DIR / 'holidays.csv'
OUTPUT_DIR = BASE_DIR / 'output'

# Other configuration settings can be added here
# Note: project_start_date, working_start_hour, and working_end_hour
# are now configured in input/project_requirements.txt under "settings".

# Debugging flag
DEBUG = True
