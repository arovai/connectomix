"""Default configuration dataclasses for Connectomix.

Connectomix is a connectivity-only analysis tool that consumes denoised
fMRI outputs from fmridenoiser (or any BIDS-compliant denoised derivatives).
Denoising, resampling, and FD-based temporal censoring are handled upstream
by fmridenoiser. Connectomix focuses on:

- Atlas / seed loading
- Condition masking (task fMRI: selecting timepoints by condition)
- Connectivity computation (seed-to-voxel, roi-to-roi, etc.)
- Group-level analysis
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path


@dataclass
class ConditionMaskingConfig:
    """Configuration for condition-based masking (task fMRI).
    
    When enabled, separate connectivity matrices are computed for each
    condition, using only timepoints belonging to that condition.
    
    This replaces the old "temporal censoring" concept. FD-based motion
    censoring has moved to fmridenoiser. Only condition-based timepoint
    selection ("condition masking") stays in connectomix.
    
    Attributes:
        enabled: Whether condition masking is enabled.
        events_file: Path to events TSV file, or "auto" to find from BIDS.
        conditions: List of condition names to include (empty = all).
        transition_buffer: Seconds to exclude around condition boundaries.
        min_volumes_retained: Minimum number of volumes required per condition.
        min_fraction_retained: Minimum fraction of volumes required.
        warn_fraction_retained: Warn if retention falls below this.
    """
    enabled: bool = False
    events_file: Optional[str] = "auto"
    conditions: List[str] = field(default_factory=list)
    transition_buffer: float = 0.0
    min_volumes_retained: int = 50
    min_fraction_retained: float = 0.3
    warn_fraction_retained: float = 0.5


@dataclass
class TemporalCensoringConfig:
    """Configuration for temporal censoring.
    
    Motion censoring (FD-based scrubbing) is handled upstream by fmridenoiser.
    This configuration enables condition-based timepoint selection for task fMRI
    and drop of initial dummy volumes.
    
    Attributes:
        enabled: Whether temporal censoring is enabled (default: False).
        drop_initial_volumes: Number of dummy scans to drop (default: 0).
        condition_selection: Dict with condition selection config (default: disabled).
        custom_mask_file: Optional path to custom censoring mask file.
        min_volumes_retained: Minimum volumes to retain (default: 50).
    """
    enabled: bool = False
    drop_initial_volumes: int = 0
    condition_selection: Dict = field(default_factory=lambda: {"enabled": False})
    custom_mask_file: Optional[Path] = None
    min_volumes_retained: int = 50


@dataclass
class ParticipantConfig:
    """Configuration for participant-level connectivity analysis.
    
    Connectomix consumes denoised fMRI data produced by fmridenoiser (or
    any BIDS-compliant denoised derivatives). It does NOT perform denoising,
    resampling, or FD-based temporal censoring—those are upstream steps.
    
    Attributes:
        subject: List of subject IDs to process
        tasks: List of task names to process
        sessions: List of session IDs to process
        runs: List of run IDs to process
        spaces: List of space names to process
        label: Custom label for output filenames
        denoised_derivatives: Path to denoised derivatives (fmridenoiser output)
        method: Analysis method (seedToVoxel, roiToVoxel, seedToSeed, roiToRoi)
        seeds_file: Path to TSV file with seed coordinates (for seed methods)
        seeds: List of seed definitions as dicts with 'name', 'x', 'y', 'z' keys
        radius: Sphere radius in mm (for seed methods)
        roi_masks: List of paths to ROI mask files (for roiToVoxel)
        roi_atlas: Atlas name for ROI extraction (for roiToVoxel with atlas labels)
        roi_label: ROI label(s) within atlas to extract (for roiToVoxel with atlas)
        atlas: Atlas name or "canica" (for roiToRoi)
        connectivity_kind: Type of connectivity measure
        n_components: Number of ICA components (for CanICA)
        canica_threshold: Threshold for extracting regions from ICA components
        canica_min_region_size: Minimum region size in voxels (for CanICA)
        condition_masking: Configuration for condition-based timepoint selection
    """
    
    # BIDS entity filters
    subject: Optional[List[str]] = None
    tasks: Optional[List[str]] = None
    sessions: Optional[List[str]] = None
    runs: Optional[List[str]] = None
    spaces: Optional[List[str]] = None
    
    # Custom label for output filenames
    label: Optional[str] = None
    
    # Input: path to denoised derivatives (fmridenoiser or compatible output)
    denoised_derivatives: Optional[Path] = None
    
    # Analysis method
    method: str = "roiToRoi"
    
    # Method-specific parameters - Seed-based
    seeds_file: Optional[Path] = None
    seeds: Optional[List[Dict[str, Any]]] = None
    radius: float = 5.0
    
    # Method-specific parameters - ROI-based
    roi_masks: Optional[List[Path]] = None
    roi_atlas: Optional[str] = None
    roi_label: Optional[List[str]] = None
    atlas: str = "schaefer2018n100"
    
    # Connectivity computation
    connectivity_kind: str = "correlation"
    
    # CanICA parameters
    n_components: int = 20
    canica_threshold: float = 1.0
    canica_min_region_size: int = 50
    
    # Condition masking configuration (task fMRI condition-based timepoint selection)
    condition_masking: ConditionMaskingConfig = field(default_factory=ConditionMaskingConfig)
    
    # Temporal censoring configuration (deprecated - kept for backward compatibility)
    temporal_censoring: TemporalCensoringConfig = field(default_factory=TemporalCensoringConfig)
    
    def __post_init__(self) -> None:
        """Post-initialization normalization of configuration values.
        
        Cleans up string fields by stripping whitespace, removing trailing 
        commas, and normalizing other common parsing issues that can occur 
        when loading configuration from CLI arguments or YAML files.
        """
        # Helper function to clean string values
        def clean_string(value: Optional[str]) -> Optional[str]:
            """Strip whitespace and trailing commas from a string."""
            if value is None:
                return None
            # Strip whitespace and remove trailing commas
            return value.strip().rstrip(',')
        
        # Clean string fields
        self.method = clean_string(self.method)
        self.atlas = clean_string(self.atlas)
        self.roi_atlas = clean_string(self.roi_atlas)
        self.label = clean_string(self.label)
        self.connectivity_kind = clean_string(self.connectivity_kind)
        
        # Clean roi_label list items
        if self.roi_label:
            self.roi_label = [clean_string(label) for label in self.roi_label]
            # Remove any None values that might have resulted
            self.roi_label = [label for label in self.roi_label if label is not None]
    
    def validate(self) -> None:
        """Validate configuration parameters.
        
        Raises:
            ValueError: If configuration is invalid
        """
        from connectomix.config.validator import ConfigValidator
        
        validator = ConfigValidator()
        
        # Validate method
        validator.validate_choice(
            self.method,
            ["seedToVoxel", "roiToVoxel", "seedToSeed", "roiToRoi"],
            "method"
        )
        
        # Validate positive values
        validator.validate_positive(self.radius, "radius")
        validator.validate_positive(self.n_components, "n_components")
        validator.validate_positive(self.canica_threshold, "canica_threshold")
        validator.validate_positive(self.canica_min_region_size, "canica_min_region_size")
        
        # Validate method-specific requirements
        if self.method in ["seedToVoxel", "seedToSeed"]:
            if self.seeds_file is None and self.seeds is None:
                validator.errors.append(
                    f"Either 'seeds_file' or 'seeds' is required for method '{self.method}'"
                )
            if self.seeds_file is not None and not Path(self.seeds_file).exists():
                validator.errors.append(
                    f"seeds_file does not exist: {self.seeds_file}"
                )
            if self.seeds is not None:
                # Validate seed structure
                if not isinstance(self.seeds, list) or len(self.seeds) == 0:
                    validator.errors.append(
                        f"seeds must be a non-empty list of dicts with 'name', 'x', 'y', 'z' keys"
                    )
                else:
                    for i, seed in enumerate(self.seeds):
                        if not isinstance(seed, dict):
                            validator.errors.append(
                                f"seeds[{i}] must be a dict, got {type(seed).__name__}"
                            )
                        else:
                            required_keys = {'name', 'x', 'y', 'z'}
                            missing_keys = required_keys - set(seed.keys())
                            if missing_keys:
                                validator.errors.append(
                                    f"seeds[{i}] missing required keys: {sorted(missing_keys)}"
                                )
        
        if self.method == "roiToVoxel":
            # Flexible ROI specification: either file paths OR atlas+label
            # BUT roi_label is ALWAYS required (for file naming in reports)
            has_mask_files = self.roi_masks is not None and len(self.roi_masks) > 0
            has_atlas_label = (self.roi_atlas is not None and 
                             self.roi_label is not None and len(self.roi_label) > 0)
            
            if not has_mask_files and not has_atlas_label:
                validator.errors.append(
                    f"Method '{self.method}' requires either: "
                    f"1) 'roi_masks' with 'roi_label' (one label per mask file), or "
                    f"2) 'roi_atlas' with 'roi_label' for atlas-based extraction"
                )
            
            # Ensure roi_label is provided in both cases
            if not self.roi_label or len(self.roi_label) == 0:
                validator.errors.append(
                    f"Method '{self.method}' requires 'roi_label' for naming outputs. "
                    f"Provide --roi-label on command line or roi_label in config."
                )
            
            # If using roi_masks, warn if number of labels doesn't match number of masks
            if has_mask_files and self.roi_label:
                if len(self.roi_label) != len(self.roi_masks):
                    validator.errors.append(
                        f"Number of roi_labels ({len(self.roi_label)}) must match "
                        f"number of roi_masks ({len(self.roi_masks)}). "
                        f"Provide one label per mask file."
                    )
        
        if self.method == "roiToRoi":
            if self.atlas is None:
                validator.errors.append(
                    f"atlas is required for method '{self.method}'"
                )
        
        # Validate denoised derivatives path if provided
        if self.denoised_derivatives is not None:
            if not Path(self.denoised_derivatives).exists():
                validator.errors.append(
                    f"denoised_derivatives path does not exist: {self.denoised_derivatives}"
                )
        
        # Raise if any errors
        validator.raise_if_errors()


@dataclass
class GroupConfig:
    """Configuration for group-level tangent space connectivity analysis.
    
    The tangent space approach computes a group-level geometric mean of
    covariance matrices and projects individual connectivity into a tangent
    space centered on this mean. This provides:
    - A group mean connectivity matrix
    - Individual deviation matrices in tangent space
    - Better statistical properties for group comparisons
    
    Attributes:
        participant_derivatives: Path to participant-level connectomix outputs
        subjects: List of subject IDs to include (None = all available)
        tasks: List of tasks to include (None = all available)
        sessions: List of sessions to include (None = all available)
        atlas: Atlas used in participant-level analysis
        method: Analysis method from participant level (must be roiToRoi)
        vectorize: Whether to vectorize connectivity matrices for output
        label: Custom label for output filenames
    """
    
    # Input specification
    participant_derivatives: Optional[Path] = None
    
    # BIDS entity filters
    subjects: Optional[List[str]] = None
    tasks: Optional[List[str]] = None
    sessions: Optional[List[str]] = None
    
    # Analysis parameters (must match participant-level)
    atlas: str = "schaefer2018n100"
    method: str = "roiToRoi"
    
    # Output options
    vectorize: bool = False
    label: Optional[str] = None
    
    def validate(self) -> None:
        """Validate configuration parameters."""
        from connectomix.config.validator import ConfigValidator
        
        validator = ConfigValidator()
        
        # Method must be roiToRoi for tangent space analysis
        if self.method != "roiToRoi":
            validator.errors.append(
                f"Group-level tangent space analysis requires method='roiToRoi', "
                f"got '{self.method}'"
            )
        
        # Atlas must be specified
        if not self.atlas:
            validator.errors.append("Atlas must be specified for group analysis")
        
        validator.raise_if_errors()

