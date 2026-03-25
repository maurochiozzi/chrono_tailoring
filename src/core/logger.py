import logging
from pathlib import Path
from src import config

def setup_audit_logger(log_file_path: Path) -> logging.Logger:
    """Sets up the audit logger for graph transformations.

    Args:
        log_file_path (Path): The path to the log file.

    Returns:
        logging.Logger: The configured logger instance.
    """
    logger = logging.getLogger("chrono_audit")
    logger.setLevel(logging.INFO)
    
    # Avoid adding multiple handlers if already configured
    if not logger.handlers:
        file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        
    return logger

audit_log_path = config.OUTPUT_DIR / "audit.log"
if not config.OUTPUT_DIR.exists():
    config.OUTPUT_DIR.mkdir(parents=True)

audit_logger = setup_audit_logger(audit_log_path)
