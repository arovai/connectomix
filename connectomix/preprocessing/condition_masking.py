"""Condition masking for task fMRI time series.

For task fMRI, condition masking selects specific timepoints (volumes)
belonging to experimental conditions before computing connectivity.

This allows computing connectivity separately for different task conditions
(e.g., 'face' vs 'house' blocks) or restricting analysis to specific
trial types.

Note: FD-based temporal censoring and initial volume dropping are handled
upstream by fmridenoiser. This module only handles condition-based selection.

Example:
    >>> from connectomix.preprocessing.condition_masking import ConditionMasker
    >>> masker = ConditionMasker(config, n_volumes=200, tr=2.0)
    >>> masker.apply_condition_selection(events_df)
    >>> masked_img = masker.apply_to_image(func_img, condition='face')
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

import nibabel as nib
import numpy as np
import pandas as pd

from connectomix.utils.exceptions import PreprocessingError


logger = logging.getLogger(__name__)


class ConditionMasker:
    """Generate and apply condition-based temporal masks.
    
    This class creates boolean masks that select volumes belonging to
    specified experimental conditions. The masks are applied to the
    image data to compute condition-specific connectivity.
    
    Attributes:
        config: Condition masking configuration.
        n_volumes: Number of volumes in the original data.
        tr: Repetition time in seconds.
        condition_masks: Dict mapping condition names to boolean masks.
    """
    
    def __init__(
        self,
        config,
        n_volumes: int,
        tr: float,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize condition masker.
        
        Args:
            config: ConditionMaskingConfig instance.
            n_volumes: Number of volumes in the data.
            tr: Repetition time in seconds.
            logger: Optional logger instance.
        """
        self.config = config
        self.n_volumes = n_volumes
        self.tr = tr
        self._logger = logger or logging.getLogger(__name__)
        
        # Store condition-specific masks
        self.condition_masks: Dict[str, np.ndarray] = {}
        
        # Store raw timing masks (before any global filtering)
        self.raw_condition_masks: Dict[str, np.ndarray] = {}
        
        self._logger.debug(f"Initialized condition masker for {n_volumes} volumes (TR={tr}s)")
    
    def apply_condition_selection(
        self,
        events_df: pd.DataFrame,
        conditions: Optional[List[str]] = None,
    ) -> Dict[str, np.ndarray]:
        """Create masks for condition-based selection.
        
        For each condition in the events file, creates a boolean mask
        indicating which volumes belong to that condition.
        
        Volumes are assigned to conditions based on:
        - Volume center time (volume_index * TR + TR/2) falls within [onset, onset + duration)
        
        Args:
            events_df: Events DataFrame with 'onset', 'duration', 'trial_type'.
                      All times are in SECONDS.
            conditions: List of specific conditions to process (or None to use config.conditions).
                       Special keyword 'baseline' creates complementary mask.
            
        Returns:
            Dictionary mapping condition names to boolean masks.
        """
        # Validate events DataFrame
        required_cols = ['onset', 'duration']
        for col in required_cols:
            if col not in events_df.columns:
                raise PreprocessingError(
                    f"Events file missing required column: '{col}'. "
                    f"Available columns: {list(events_df.columns)}"
                )
        
        # Determine condition column (must have trial_type or equivalent)
        condition_col = None
        for possible in ['trial_type', 'condition', 'event_type']:
            if possible in events_df.columns:
                condition_col = possible
                break
        
        if condition_col is None:
            raise PreprocessingError(
                "Events file missing condition column. Expected one of: "
                "'trial_type', 'condition', 'event_type'. "
                f"Available columns: {list(events_df.columns)}"
            )
        
        # Get all unique conditions from events file
        all_conditions = events_df[condition_col].unique().tolist()
        self._logger.info(f"Found trial types in events file: {all_conditions}")
        
        # Determine which conditions to process
        # Priority: explicit conditions parameter > config.conditions
        conditions_to_use = conditions if conditions is not None else getattr(self.config, 'conditions', None)
        
        # Check if user requested "baseline" (special keyword for inter-trial intervals)
        baseline_requested = False
        if conditions_to_use:
            # Check for special "baseline" keyword (case-insensitive)
            baseline_keywords = {'baseline', 'rest', 'iti', 'inter-trial'}
            requested_lower = {c.lower() for c in conditions_to_use}
            baseline_requested = bool(requested_lower & baseline_keywords)
            
            # Filter out baseline keywords from conditions to process
            conditions_to_process = [c for c in conditions_to_use if c.lower() not in baseline_keywords]
            
            # Validate remaining conditions exist in events file
            for cond in conditions_to_process:
                if cond not in all_conditions:
                    raise PreprocessingError(
                        f"Trial type '{cond}' not found in events file. "
                        f"Available trial types: {all_conditions}\n"
                        f"Tip: Use 'baseline' to select inter-trial intervals."
                    )
        else:
            # No conditions specified - process all trial types
            conditions_to_process = all_conditions
        
        # Compute volume center times in seconds
        # Volume i covers time [i*TR, (i+1)*TR)
        # Center of volume i is at time i*TR + TR/2
        volume_centers = np.arange(self.n_volumes) * self.tr + self.tr / 2
        
        self._logger.debug(f"Data: {self.n_volumes} volumes, TR={self.tr}s, "
                          f"total duration={self.n_volumes * self.tr:.1f}s")
        
        # First, compute mask for ALL events (needed for baseline calculation)
        all_events_mask = np.zeros(self.n_volumes, dtype=bool)
        for _, event in events_df.iterrows():
            onset = float(event['onset'])  # Seconds
            duration = float(event['duration'])  # Seconds
            event_end = onset + duration
            
            # Volume i belongs to event if its center falls in [onset, event_end)
            in_event = (volume_centers >= onset) & (volume_centers < event_end)
            all_events_mask |= in_event
        
        # Create mask for each requested condition
        self.condition_masks = {}
        self.raw_condition_masks = {}
        
        for condition in conditions_to_process:
            # Start with all False
            cond_mask = np.zeros(self.n_volumes, dtype=bool)
            
            # Get events for this trial type
            cond_events = events_df[events_df[condition_col] == condition]
            n_events = len(cond_events)
            
            self._logger.debug(f"Processing condition '{condition}': {n_events} events")
            
            for event_idx, (_, event) in enumerate(cond_events.iterrows()):
                onset = float(event['onset'])  # Seconds
                duration = float(event['duration'])  # Seconds
                event_end = onset + duration
                
                # Find volumes whose CENTER falls within [onset, event_end)
                in_event = (volume_centers >= onset) & (volume_centers < event_end)
                n_vols_this_event = np.sum(in_event)
                
                if n_vols_this_event > 0:
                    self._logger.debug(
                        f"  Event {event_idx + 1}: onset={onset:.2f}s, "
                        f"duration={duration:.2f}s → {n_vols_this_event} volume(s)"
                    )
                
                cond_mask |= in_event
            
            # Store masks
            self.raw_condition_masks[condition] = cond_mask.copy()
            self.condition_masks[condition] = cond_mask
            
            n_volumes_cond = np.sum(cond_mask)
            if n_volumes_cond > 0:
                self._logger.info(
                    f"Trial type '{condition}': {n_volumes_cond} volumes "
                    f"({100 * n_volumes_cond / self.n_volumes:.1f}%)"
                )
            else:
                self._logger.warning(
                    f"Trial type '{condition}': NO volumes selected (check onset/duration)"
                )
        
        # Add baseline if requested
        if baseline_requested:
            raw_baseline_mask = ~all_events_mask
            self.raw_condition_masks['baseline'] = raw_baseline_mask
            self.condition_masks['baseline'] = raw_baseline_mask
            
            n_baseline = np.sum(raw_baseline_mask)
            self._logger.info(
                f"Baseline (inter-trial intervals): {n_baseline} volumes "
                f"({100 * n_baseline / self.n_volumes:.1f}%)"
            )
        
        return self.condition_masks
    
    def apply_to_image(
        self,
        img: nib.Nifti1Image,
        condition: Optional[str] = None,
    ) -> nib.Nifti1Image:
        """Apply condition mask to 4D image.
        
        Args:
            img: 4D NIfTI image.
            condition: Condition name to select volumes for.
            
        Returns:
            New image with only selected volumes.
        """
        data = img.get_fdata()
        
        if data.ndim != 4:
            raise PreprocessingError(
                f"Expected 4D image, got {data.ndim}D"
            )
        
        # Select mask
        if condition is not None:
            if condition not in self.condition_masks:
                raise PreprocessingError(
                    f"Condition '{condition}' not found. "
                    f"Available: {list(self.condition_masks.keys())}"
                )
            mask = self.condition_masks[condition]
        else:
            # If no condition specified, return all volumes
            return img
        
        # Apply mask
        masked_data = data[..., mask]
        
        # Create new image
        new_img = nib.Nifti1Image(masked_data, img.affine, img.header)
        new_img.header.set_data_shape(masked_data.shape)
        
        n_original = data.shape[-1]
        n_retained = masked_data.shape[-1]
        self._logger.debug(
            f"Applied condition mask '{condition}': {n_original} -> {n_retained} volumes"
        )
        
        return new_img
    
    def validate(self) -> None:
        """Check if enough volumes remain for each condition.
        
        Raises:
            PreprocessingError: If too few volumes remain (as warning).
        """
        self._warnings: List[str] = []
        
        for cond_name, cond_mask in self.condition_masks.items():
            n_retained = np.sum(cond_mask)
            fraction_retained = n_retained / self.n_volumes
            
            if n_retained < self.config.min_volumes_retained:
                warning_msg = (
                    f"LOW VOLUME COUNT for condition '{cond_name}': only {n_retained} volumes "
                    f"(recommended minimum: {self.config.min_volumes_retained}). "
                    f"Results may be unreliable."
                )
                self._warnings.append(warning_msg)
                self._logger.warning(warning_msg)
            
            if fraction_retained < self.config.min_fraction_retained:
                warning_msg = (
                    f"LOW RETENTION RATE for condition '{cond_name}': {fraction_retained:.1%} "
                    f"(recommended minimum: {self.config.min_fraction_retained:.0%}). "
                    f"Results may be unreliable."
                )
                self._warnings.append(warning_msg)
                self._logger.warning(warning_msg)
            elif fraction_retained < self.config.warn_fraction_retained:
                self._logger.warning(
                    f"Only {fraction_retained:.1%} of volumes retained for condition "
                    f"'{cond_name}'. Interpret results with caution."
                )
    
    def get_summary(self) -> Dict[str, Any]:
        """Return condition masking statistics for reporting.
        
        Returns:
            Dictionary with masking summary statistics.
        """
        # Calculate total volumes used across all conditions
        combined_mask = np.zeros(self.n_volumes, dtype=bool)
        for mask in self.condition_masks.values():
            combined_mask |= mask
        n_retained = int(np.sum(combined_mask))
        n_masked = self.n_volumes - n_retained
        fraction_retained = n_retained / self.n_volumes
        
        summary = {
            'enabled': self.config.enabled,
            'n_original': self.n_volumes,
            'n_retained': n_retained,
            'n_masked': n_masked,
            'fraction_retained': fraction_retained,
        }
        
        # Add per-condition info
        if self.condition_masks:
            summary['conditions'] = {}
            for name, mask in self.condition_masks.items():
                raw_mask = self.raw_condition_masks.get(name, mask)
                summary['conditions'][name] = {
                    'n_volumes': int(np.sum(mask)),
                    'fraction': float(np.sum(mask) / self.n_volumes),
                    'mask': mask.tolist(),
                    'raw_mask': raw_mask.tolist(),
                }
        
        # Add any warnings that were generated during validation
        if hasattr(self, '_warnings') and self._warnings:
            summary['warnings'] = self._warnings
        
        return summary


def load_events_file(
    events_path: Path,
    logger: Optional[logging.Logger] = None,
) -> pd.DataFrame:
    """Load BIDS events TSV file.
    
    Args:
        events_path: Path to events.tsv file.
        logger: Optional logger.
        
    Returns:
        Events DataFrame.
    """
    _logger = logger or logging.getLogger(__name__)
    
    if not events_path.exists():
        raise PreprocessingError(f"Events file not found: {events_path}")
    
    events_df = pd.read_csv(events_path, sep='\t')
    _logger.debug(f"Loaded events file: {events_path.name} ({len(events_df)} events)")
    
    return events_df


def find_events_file(
    func_path: Path,
    layout: "BIDSLayout",
    logger: Optional[logging.Logger] = None,
) -> Optional[Path]:
    """Find BIDS events file matching a functional file using BIDSLayout.
    
    Uses BIDSLayout to properly query for events.tsv in the raw BIDS dataset.
    BIDS allows two types of events files:
    
    1. Subject-specific: sub-01_task-rest_events.tsv (in sub-01/func/)
    2. Dataset-wide: task-rest_events.tsv (in root, shared by all subjects)
    
    This function first queries without subject filter. If multiple matches
    are found, it narrows down by adding subject (and session/run if needed).
    
    Args:
        func_path: Path to functional file.
        layout: BIDSLayout object with access to raw BIDS data.
        logger: Optional logger.
        
    Returns:
        Path to events file, or None if not found.
    """
    _logger = logger or logging.getLogger(__name__)
    
    # Extract entities from functional filename
    func_name = func_path.name
    
    # Parse entities
    entities = {}
    for part in func_name.split('_'):
        if '-' in part:
            key, value = part.split('-', 1)
            entities[key] = value
    
    if 'sub' not in entities or 'task' not in entities:
        _logger.warning("Cannot find events file: missing sub or task entity")
        return None
    
    # Clean up task name (remove any suffix contamination)
    task_name = entities['task'].replace('_bold.nii.gz', '').replace('_bold.nii', '')
    
    # Build base query WITHOUT subject (to find dataset-wide events files)
    base_query = {
        'task': task_name,
        'suffix': 'events',
        'extension': '.tsv',
    }
    
    # Add session if present
    if 'ses' in entities:
        base_query['session'] = entities['ses']
    
    # Add run if present
    if 'run' in entities:
        base_query['run'] = entities['run']
    
    _logger.debug(f"Querying BIDSLayout for events file (without subject): {base_query}")
    
    try:
        # First query WITHOUT subject - catches dataset-wide events files
        events_files = layout.get(**base_query)
        
        if len(events_files) == 1:
            events_path = Path(events_files[0].path)
            _logger.debug(f"Found single events file: {events_path}")
            return events_path
        
        elif len(events_files) > 1:
            # Multiple matches - narrow down by subject
            query_with_subject = {**base_query, 'subject': entities['sub']}
            _logger.debug(f"Multiple events files found, narrowing by subject: {query_with_subject}")
            
            events_files = layout.get(**query_with_subject)
            
            if events_files:
                events_path = Path(events_files[0].path)
                _logger.debug(f"Found subject-specific events file: {events_path}")
                return events_path
        
        # No matches - try without run entity (events may be shared across runs)
        if 'run' in base_query:
            query_no_run = {k: v for k, v in base_query.items() if k != 'run'}
            _logger.debug(f"No events file found, trying without run: {query_no_run}")
            
            events_files = layout.get(**query_no_run)
            
            if len(events_files) == 1:
                events_path = Path(events_files[0].path)
                _logger.debug(f"Found events file (ignoring run): {events_path}")
                return events_path
            
            elif len(events_files) > 1:
                query_no_run['subject'] = entities['sub']
                events_files = layout.get(**query_no_run)
                
                if events_files:
                    events_path = Path(events_files[0].path)
                    _logger.debug(f"Found subject-specific events file (ignoring run): {events_path}")
                    return events_path
        
        _logger.debug(f"No events file found for task '{task_name}'")
        return None
            
    except Exception as e:
        _logger.warning(f"Error querying BIDSLayout for events: {e}")
        return None
