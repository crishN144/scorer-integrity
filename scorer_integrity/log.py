"""Set up a logger to be used in all modules in the library.

To use the logger, import it in any module and use it as follows:

    ```
    from scorer_integrity.log import logger

    logger.info("Info message")
    logger.warning("Warning message")
    ```
"""

import logging
from logging.config import dictConfig
from pathlib import Path

DEFAULT_LOGFILE = Path(__file__).resolve().parent.parent / "logs" / "logs.log"


def setup_logger(logfile: Path = DEFAULT_LOGFILE) -> logging.Logger:
    """Set up a logger to be used in all modules in the library.

    Console handler logs at INFO, file handler at WARNING.

    Args:
        logfile: Path to the file handler's log file. Parent dirs are created.

    Returns:
        A configured logger object.
    """
    if not logfile.parent.exists():
        logfile.parent.mkdir(parents=True, exist_ok=True)

    logging_config = {
        "version": 1,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": "INFO",
            },
            "file": {
                "class": "logging.FileHandler",
                "filename": str(logfile),
                "formatter": "default",
                "level": "WARNING",
            },
        },
        "root": {
            "handlers": ["console", "file"],
            "level": "INFO",
        },
    }

    dictConfig(logging_config)
    return logging.getLogger()


logger = setup_logger()
