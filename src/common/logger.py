from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.common.config import Config


def setup_logger(
    name: str = "cfa_agent",
    level: str = "DEBUG",
    log_file: Optional[str] = None,
    format_string: str = "%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s",
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    if not logger.handlers:
        handler_console = logging.StreamHandler(sys.stdout)
        handler_console.setFormatter(logging.Formatter(format_string))
        logger.addHandler(handler_console)

        if log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            handler_file = logging.FileHandler(log_file, encoding="utf-8")
            handler_file.setFormatter(logging.Formatter(format_string))
            logger.addHandler(handler_file)

    return logger


def init_logger_from_config(config: Config) -> logging.Logger:
    logger = logging.getLogger("cfa_agent")
    logger.setLevel(getattr(logging, config.log.log_level.upper()))
    logger.handlers.clear()

    format_string = "%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s"

    handler_console = logging.StreamHandler(sys.stdout)
    handler_console.setFormatter(logging.Formatter(format_string))
    logger.addHandler(handler_console)

    if config.log.log_file:
        Path(config.log.log_file).parent.mkdir(parents=True, exist_ok=True)
        handler_file = logging.FileHandler(config.log.log_file, encoding="utf-8")
        handler_file.setFormatter(logging.Formatter(format_string))
        logger.addHandler(handler_file)

    return logger


logger = setup_logger()