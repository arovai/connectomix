"""Temporal censoring for motion artifacts and condition selection."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import nibabel as nib
import numpy as np
import pandas as pd

from connectomix.utils.exceptions import PreprocessingError
from connectomix.preprocessing.condition_masking import ConditionMasker, load_events_file


def find_events_file(
    func_path: Path,
    layout,
    logger: Optional[logging.Logger] = None,
) -> Optional[Path]:
    """Find BIDS events file matching a functional file.
    
    Args:
        func_path: Path to functional file
        layout: BIDSLayout object
        logger: Optional logger instance
    
    Returns:
        Path to events file or None if not found
    """
    _logger = logger or logging.getLogger(__name__)
    
    func_path = Path(func_path)
    
    try:
        # Parse entities from functional filename
        from connectomix.core.participant import _extract_entities_from_path
        entities = _extract_entities_from_path(func_path)
        
        # Query for events file matching this task
        query = {
            'extension': 'tsv',
            'suffix': 'events',
            'scope': 'raw',
        }
        
        if 'task' in entities:
            query['task'] = entities['task']
        
        # Try with subject first
        if 'sub' in entities:
            query['subject'] = entities['sub']
            events_list = layout.get(**query)
            if events_list:
                return Path(events_list[0].path)
        
        # Try without subject (dataset-wide events file)
        query.pop('subject', None)
        events_list = layout.get(**query)
        if events_list:
            return Path(events_list[0].path)
        
        if _logger:
            _logger.debug(f"No events file found for {func_path.name}")
        return None
    
    except Exception as e:
        if _logger:
            _logger.warning(f"Error finding events file: {e}")
        return None


class TemporalCensor:
    """Manage temporal censoring for motion artifacts and condition selection.
    
    Creates boolean masks that select volumes to include/exclude in connectivity
    computation based on motion thresholds, condition selection, or custom masks.
    
    Attributes:
        mask: Boolean array indicating which volumes to keep
        condition_masks: Dict of condition-specific masks
        censoring_log: Log of censoring decisions per volume
    """
    
    def __init__(
        self,
        config,
        n_volumes: int,
        tr: float,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize temporal censor.
        
        Args:
            config: Temporal censoring configuration
            n_volumes: Number of volumes in the data
            tr: Repetition time in seconds
            logger: Optional logger instance
        """
        self.config = config
        self.n_volumes = n_volumes
        self.tr = tr
        self._logger = logger or logging.getLogger(__name__)
        
        self.mask = np.ones(n_volumes, dtype=bool)
        self.condition_masks: Dict[str, np.ndarray] = {}
        self.censoring_log: Dict[int, List[str]] = {}
        
        # Initialize censoring log
        for i in range(n_volumes):
            self.censoring_log[i] = []
    
    def apply_initial_drop(self, n_volumes: Optional[int] = None) -> None:
        """Drop initial volumes (dummy scans).
        
        Args:
            n_volumes: Number of volumes to drop (from config if None)
        """
        if n_volumes is None:
            n_volumes = self.config.drop_initial_volumes
        
        if n_volumes <= 0:
            return
        
        if n_volumes >= self.n_volumes:
            self._logger.warning(
                f"Requested to drop {n_volumes} volumes but only have {self.n_volumes}"
            )
            n_volumes = self.n_volumes - 1
        
        # Mark first n_volumes as censored
        self.mask[:n_volumes] = False
        for i in range(min(n_volumes, self.n_volumes)):
            self.censoring_log[i].append("initial_drop")
        
        self._logger.info(f"Dropped {n_volumes} initial volumes")
    
    def apply_motion_censoring(self, confounds_df: pd.DataFrame) -> None:
        """Apply motion-based censoring using framewise displacement.
        
        Args:
            confounds_df: DataFrame with confounds (must include 'framewise_displacement')
        """
        if not self.config.motion_censoring.enabled:
            return
        
        fd_threshold = self.config.motion_censoring.fd_threshold
        if fd_threshold is None or fd_threshold <= 0:
            return
        
        # Get framewise displacement column
        if 'framewise_displacement' not in confounds_df.columns:
            self._logger.warning("'framewise_displacement' not found in confounds")
            return
        
        fd = confounds_df['framewise_displacement'].values
        
        # Handle NaN values
        fd = np.nan_to_num(fd, nan=0.0)
        
        # Identify high-motion volumes
        high_motion = fd > fd_threshold
        n_censored = np.sum(high_motion)
        
        # Apply extension (censor surrounding volumes)
        extend = self.config.motion_censoring.fd_extend
        if extend > 0:
            extended_mask = np.zeros(len(high_motion), dtype=bool)
            for i in range(len(high_motion)):
                if high_motion[i]:
                    start = max(0, i - extend)
                    end = min(len(high_motion), i + extend + 1)
                    extended_mask[start:end] = True
            high_motion = extended_mask
            n_censored = np.sum(high_motion)
        
        # Update mask
        self.mask &= ~high_motion
        
        for i, censored in enumerate(high_motion):
            if censored:
                self.censoring_log[i].append("motion")
        
        self._logger.info(
            f"Motion censoring: removed {n_censored} volume(s) "
            f"above FD threshold {fd_threshold} cm"
        )
    
    def apply_segment_filtering(self, min_segment_length: int) -> None:
        """Remove short contiguous segments of valid volumes.
        
        After motion censoring, removes segments shorter than min_segment_length
        to ensure sufficient data for connectivity estimation.
        
        Args:
            min_segment_length: Minimum segment length to keep
        """
        if min_segment_length <= 0:
            return
        
        # Find contiguous segments of True values in mask
        segments = np.split(np.where(self.mask)[0], 
                           np.where(np.diff(np.where(self.mask)[0]) != 1)[0] + 1)
        
        # Remove short segments
        for segment in segments:
            if len(segment) < min_segment_length:
                self.mask[segment] = False
                for idx in segment:
                    self.censoring_log[idx].append("short_segment")
        
        n_remaining = np.sum(self.mask)
        self._logger.info(
            f"Segment filtering: kept {n_remaining} volume(s) "
            f"(min segment={min_segment_length})"
        )
    
    def apply_condition_selection(
        self,
        events_df: pd.DataFrame,
        conditions: Optional[List[str]] = None,
    ) -> None:
        """Select volumes belonging to specific experimental conditions.
        
        Args:
            events_df: BIDS events DataFrame
            conditions: List of condition names to select (all if None)
        """
        if conditions is None or len(conditions) == 0:
            return
        
        # Use ConditionMasker to create condition-specific masks
        masker = ConditionMasker(self.config, self.n_volumes, self.tr, self._logger)
        masker.apply_condition_selection(events_df, conditions)
        
        self.condition_masks = masker.condition_masks
        self._logger.info(f"Created condition masks for: {list(self.condition_masks.keys())}")
    
    def get_censoring_entity(self) -> Optional[str]:
        """Get BIDS entity string representing censoring applied.
        
        Returns:
            String like 'FD0.5mm' or None if no censoring applied
        """
        fd_threshold = self.config.motion_censoring.fd_threshold
        if fd_threshold and fd_threshold > 0:
            # Convert cm to mm
            return f"FD{fd_threshold * 10:.1f}mm"
        return None
    
    def apply_to_image(
        self,
        img: nib.Nifti1Image,
        condition: Optional[str] = None,
    ) -> nib.Nifti1Image:
        """Apply censoring mask to functional image data.
        
        Args:
            img: Functional image
            condition: Specific condition to apply (uses condition_masks if provided)
        
        Returns:
            Masked image with censored volumes removed
        """
        data = img.get_fdata()
        
        # Get appropriate mask
        if condition and condition in self.condition_masks:
            mask = self.condition_masks[condition]
        else:
            mask = self.mask
        
        # Apply mask to 4D data
        if len(data.shape) == 4:
            masked_data = data[..., mask]
        else:
            masked_data = data
        
        # Create new image with masked data
        masked_img = nib.Nifti1Image(masked_data, img.affine, img.header)
        return masked_img
    
    def get_summary(self) -> Dict[str, any]:
        """Get summary of censoring applied.
        
        Returns:
            Dictionary with censoring statistics
        """
        n_kept = np.sum(self.mask)
        n_censored = self.n_volumes - n_kept
        pct_kept = 100.0 * n_kept / self.n_volumes if self.n_volumes > 0 else 0.0
        
        return {
            'n_volumes_original': self.n_volumes,
            'n_volumes_kept': int(n_kept),
            'n_volumes_censored': int(n_censored),
            'percent_kept': float(pct_kept),
            'percent_censored': 100.0 - float(pct_kept),
            'duration_kept_sec': float(n_kept * self.tr),
            'duration_censored_sec': float(n_censored * self.tr),
        }
