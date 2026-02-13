"""Preprocessing functions for connectivity analysis.

Denoising, resampling, and FD-based censoring are handled upstream by
fmridenoiser. This package provides:
- CanICA atlas generation
- Condition masking for task fMRI
"""

from connectomix.preprocessing.canica import run_canica_atlas
from connectomix.preprocessing.condition_masking import (
    ConditionMasker,
    load_events_file,
    find_events_file,
)

__all__ = [
    "run_canica_atlas",
    "ConditionMasker",
    "load_events_file",
    "find_events_file",
]
