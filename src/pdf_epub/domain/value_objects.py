from enum import Enum
from typing import NamedTuple


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BoundingBox(NamedTuple):
    """Page coordinates in points: (left, top, right, bottom)."""

    x0: float
    y0: float
    x1: float
    y1: float
