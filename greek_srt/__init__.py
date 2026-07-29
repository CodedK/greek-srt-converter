"""Greek SRT converter core. Two entry points: scan() reads, convert() writes."""

from .models import (
    Action,
    Confidence,
    ConvertResult,
    FileReport,
    FileStamp,
    LossyChange,
    Target,
)
from .clean import StructureChanged
from .fileio import BACKUP_PREFIX, FileOpError
from .convert import (
    LOSS_GUARD,
    MAX_FILE_BYTES,
    PREVIEW_LINES,
    Progress,
    ProgressCallback,
    convert,
    scan,
    scan_one,
)

from .timing import format_timecode, parse_timecode, shift_document_timing

__all__ = [
    "Action", "Confidence", "ConvertResult", "FileReport", "FileStamp",
    "LossyChange", "Target", "StructureChanged", "FileOpError",
    "Progress", "ProgressCallback", "convert", "scan", "scan_one",
    "parse_timecode", "format_timecode", "shift_document_timing",
    "BACKUP_PREFIX", "PREVIEW_LINES", "MAX_FILE_BYTES", "LOSS_GUARD",
]
__version__ = "1.0.0"
