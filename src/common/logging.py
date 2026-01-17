"""Centralized logging setup."""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Setup centralized logging configuration."""
    logger = logging.getLogger("discord_object_store")
    logger.setLevel(level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    # Add handler if not already added
    if not logger.handlers:
        logger.addHandler(console_handler)
    
    return logger


# Global logger instance
logger = setup_logging()
