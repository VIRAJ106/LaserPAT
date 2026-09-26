"""
csv_logger.py — Structured CSV logging for LaserPAT simulation runs.

Each call to log_frame() appends one row to the output CSV. Headers are
written on the first call so the file can be opened mid-run in Excel/pandas.
"""
import csv
import os
from dataclasses import dataclass, fields, astuple
from typing import Optional


@dataclass
class FrameRecord:
    frame_id: int
    timestamp: float
    state: str
    tracking_error_px: float
    gimbal_x: float
    gimbal_y: float
    target_x: float
    target_y: float
    ai_score: float = 0.0
    weather_preset: str = "clear"
    innovation_gate_passed: bool = True


class CSVLogger:
    """Appends one FrameRecord per simulation step to a CSV file."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._file = None
        self._writer = None
        self._header_written = False

    def open(self):
        os.makedirs(os.path.dirname(self.filepath) or ".", exist_ok=True)
        self._file = open(self.filepath, "w", newline="")
        self._writer = csv.writer(self._file)

    def log_frame(self, record: FrameRecord):
        if self._writer is None:
            raise RuntimeError("CSVLogger.open() must be called before log_frame()")
        if not self._header_written:
            self._writer.writerow([f.name for f in fields(record)])
            self._header_written = True
        self._writer.writerow(astuple(record))

    def flush(self):
        if self._file:
            self._file.flush()

    def close(self):
        if self._file:
            self._file.close()
            self._file = None
            self._writer = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()
