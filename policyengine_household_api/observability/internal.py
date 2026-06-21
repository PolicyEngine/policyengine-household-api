from __future__ import annotations

import logging


class PlainMessageFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()
