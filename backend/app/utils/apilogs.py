import logging
import sys
import os
from logging.handlers import RotatingFileHandler

def setup_logger():
    logger = logging.getLogger("api_logger")
    logger.setLevel(logging.INFO)

    # Format the logs clearly: Timestamp - Level - Message
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s", 
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Stream out to the immediate console as well
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    # Stream heavily into a rotating text log file in our root dir
    # Named api_logs.log to keep it identifiable
    log_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "api_logs.log")
    
    file_handler = RotatingFileHandler(
        log_file_path, maxBytes=5000000, backupCount=3
    )
    file_handler.setFormatter(formatter)

    # Avoid duplicating handlers if this module is reloaded
    if not logger.handlers:
        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)

    return logger

logger = setup_logger()
