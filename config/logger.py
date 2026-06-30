import logging
import sys
from pathlib import Path

# Setup logs directory
ROOT_DIR = Path(__file__).parent.parent
LOG_FILE = ROOT_DIR / "agentwire.log"

class ColoredFormatter(logging.Formatter):
    """Custom logging Formatter that prints standard console logs in green color."""
    GREEN = "\033[92m"
    RESET = "\033[0m"

    def format(self, record):
        formatted = super().format(record)
        return f"{self.GREEN}{formatted}{self.RESET}"

def setup_logging():
    """Sets up standard logging configuration for the AgentWire application."""
    # Define formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    colored_formatter = ColoredFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(colored_formatter)
    console_handler.setLevel(logging.INFO)

    # File Handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

# Initialize logging when module is imported
setup_logging()

def get_logger(name: str) -> logging.Logger:
    """Obtains a named logger instance."""
    return logging.getLogger(name)
