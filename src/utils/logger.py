"""Logging configuration for the project."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.utils.config import load_config

_config = load_config()


def setup_logging(name: str = "prompt_injection_filter") -> logging.Logger:
    """Build a logger with console + rotating file handlers."""
    logger = logging.getLogger(name)
    if logger.handlers:  # avoid duplicate handlers on hot reload
        return logger

    level = getattr(logging, str(_config["logging"].get("level", "INFO")).upper(), logging.INFO)
    fmt = _config["logging"].get("format", "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    formatter = logging.Formatter(fmt)

    logger.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    log_file = Path(_config["logging"].get("file", "logs/system.log"))
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=int(_config["logging"].get("max_bytes", 5 * 1024 * 1024)),
        backupCount=int(_config["logging"].get("backup_count", 5)),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


logger = setup_logging("pif")