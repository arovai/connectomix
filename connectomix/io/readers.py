"""File readers for various formats.

Confound loading (load_confounds, expand_confound_wildcards) has moved
to fmridenoiser. This module retains readers needed by connectomix:
seeds, participants, JSON sidecars, and repetition time.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Tuple, Dict, Any
import json


def load_seeds_file(seeds_path: Path) -> Tuple[List[str], np.ndarray]:
    """Load seeds from TSV file.
    
    Expected format:
        name    x    y    z
        PCC     0   -52   18
        mPFC    0    52    0
    
    Args:
        seeds_path: Path to seeds TSV file
    
    Returns:
        Tuple of (seed_names, coordinates_array)
        - seed_names: List of seed region names
        - coordinates_array: NumPy array of shape (n_seeds, 3) with MNI coordinates
    
    Raises:
        ValueError: If required columns are missing
        FileNotFoundError: If seeds file doesn't exist
    """
    if not seeds_path.exists():
        raise FileNotFoundError(f"Seeds file not found: {seeds_path}")
    
    # Load TSV file
    df = pd.read_csv(seeds_path, sep='\t')
    
    # Check for required columns
    required_cols = ['name', 'x', 'y', 'z']
    missing = set(required_cols) - set(df.columns)
    if missing:
        raise ValueError(
            f"Seeds file missing required columns: {sorted(missing)}\n"
            f"Required columns: {required_cols}\n"
            f"Found columns: {df.columns.tolist()}"
        )
    
    # Extract data
    names = df['name'].tolist()
    coords = df[['x', 'y', 'z']].values.astype(float)
    
    return names, coords


def load_participants_tsv(bids_dir: Path) -> pd.DataFrame:
    """Load participants.tsv file from BIDS dataset.
    
    Args:
        bids_dir: Path to BIDS dataset root
    
    Returns:
        DataFrame with participant information
    
    Raises:
        FileNotFoundError: If participants.tsv doesn't exist
    """
    participants_path = bids_dir / "participants.tsv"
    
    if not participants_path.exists():
        raise FileNotFoundError(
            f"participants.tsv not found in {bids_dir}\n"
            f"This file is required for group-level analysis."
        )
    
    df = pd.read_csv(participants_path, sep='\t')
    
    # Ensure participant_id column exists
    if 'participant_id' not in df.columns:
        raise ValueError(
            f"participants.tsv missing 'participant_id' column"
        )
    
    return df


def load_json_sidecar(json_path: Path) -> Dict[str, Any]:
    """Load JSON sidecar file.
    
    Args:
        json_path: Path to JSON file
    
    Returns:
        Dictionary with JSON contents
    
    Raises:
        FileNotFoundError: If JSON file doesn't exist
        json.JSONDecodeError: If JSON is invalid
    """
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    
    with json_path.open() as f:
        data = json.load(f)
    
    return data


def get_repetition_time(json_path: Path) -> float:
    """Get repetition time (TR) from JSON sidecar.
    
    Args:
        json_path: Path to functional image JSON sidecar
    
    Returns:
        TR in seconds
    
    Raises:
        ValueError: If TR not found in JSON
    """
    data = load_json_sidecar(json_path)
    
    if 'RepetitionTime' not in data:
        raise ValueError(
            f"RepetitionTime not found in {json_path.name}"
        )
    
    return float(data['RepetitionTime'])
