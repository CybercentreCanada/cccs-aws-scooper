import logging
from datetime import datetime, timezone
from sys import modules

from installer.core.constants import CBS

LOG_FILE_NAME = f"{datetime.now(timezone.utc).timestamp()}.cbs.log"


class CustomFormatter(logging.Formatter):
    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    def __init__(self, fmt):
        super().__init__()
        self.fmt = fmt
        self.FORMATS = {
            logging.DEBUG: self.grey + self.fmt + self.reset,
            logging.INFO: self.blue + self.fmt + self.reset,
            logging.WARNING: self.yellow + self.fmt + self.reset,
            logging.ERROR: self.red + self.fmt + self.reset,
            logging.CRITICAL: self.bold_red + self.fmt + self.reset,
        }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


LOGGER = logging.getLogger(CBS.upper())
LOGGER.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

file_formatter = logging.Formatter(
    "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
stdout_formatter = CustomFormatter("%(message)s")
ch.setFormatter(stdout_formatter)

LOGGER.addHandler(ch)

if "pytest" not in modules:
    fh = logging.FileHandler(LOG_FILE_NAME)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(file_formatter)
    LOGGER.addHandler(fh)
