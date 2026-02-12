"""BIDS I/O operations for Connectomix."""

from connectomix.io.bids import create_bids_layout, build_bids_path, query_participant_files
from connectomix.io.readers import load_seeds_file
from connectomix.io.writers import save_nifti_with_sidecar, save_matrix_with_sidecar
from connectomix.io.paths import validate_bids_dir, create_dataset_description

__all__ = [
    "create_bids_layout",
    "build_bids_path",
    "query_participant_files",
    "load_seeds_file",
    "save_nifti_with_sidecar",
    "save_matrix_with_sidecar",
    "validate_bids_dir",
    "create_dataset_description",
]
