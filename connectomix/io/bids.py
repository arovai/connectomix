"""BIDS layout creation and path building."""

from bids import BIDSLayout
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging
import glob

from connectomix.io.paths import validate_bids_dir, validate_derivatives_dir


def create_bids_layout(
    bids_dir: Path,
    derivatives: Optional[Dict[str, Path]] = None,
    logger: Optional[logging.Logger] = None
) -> BIDSLayout:
    """Create BIDS layout with denoised derivatives.
    
    Args:
        bids_dir: Path to BIDS dataset root or denoised derivatives directory
        derivatives: Dictionary mapping derivative names to paths
        logger: Optional logger instance
    
    Returns:
        BIDSLayout instance
    
    Raises:
        BIDSError: If BIDS directory or derivatives are invalid
    """
    # Validate BIDS directory
    validate_bids_dir(bids_dir)
    
    if logger:
        logger.info(f"Creating BIDS layout for {bids_dir}")
    
    # Set up derivatives paths as a list (pybids expects list, not dict)
    derivatives_list = []
    
    if derivatives:
        for name, path in derivatives.items():
            validate_derivatives_dir(path, name)
            derivatives_list.append(str(path))
            if logger:
                logger.debug(f"  Adding {name} derivatives: {path}")
    else:
        # Try to find fmridenoiser in standard location
        default_fmridenoiser = bids_dir / "derivatives" / "fmridenoiser"
        if default_fmridenoiser.exists():
            derivatives_list.append(str(default_fmridenoiser))
            if logger:
                logger.debug(f"  Found fmridenoiser at default location: {default_fmridenoiser}")
        else:
            # Check if BIDS_DIR itself contains denoised files
            denoised_files = glob.glob(str(bids_dir / "**" / "*desc-denoised_bold.nii.gz"), recursive=True)
            if len(denoised_files) > 0:
                derivatives_list.append(str(bids_dir))
                if logger:
                    logger.debug(f"  Found denoised files in BIDS_DIR, not adding as separate derivative")
    
    # Create layout - derivatives should be a list of paths or False
    layout = BIDSLayout(
        str(bids_dir),
        derivatives=derivatives_list if derivatives_list else False,
        validate=False  # Skip validation for speed
    )
    
    if logger:
        n_subjects = len(layout.get_subjects())
        logger.info(f"Found {n_subjects} subject(s) in dataset")
    
    return layout


def build_bids_path(
    output_dir: Path,
    entities: Dict[str, Any],
    suffix: str,
    extension: str,
    level: str = "participant"
) -> Path:
    """Build BIDS-compliant output path.
    
    Args:
        output_dir: Output directory root
        entities: Dictionary of BIDS entities
        suffix: File suffix (e.g., "bold", "effectSize")
        extension: File extension (e.g., ".nii.gz", ".json")
        level: Analysis level ("participant" or "group")
    
    Returns:
        Complete BIDS-compliant path
    
    Example:
        >>> entities = {
        ...     'subject': '01',
        ...     'session': '1',
        ...     'task': 'rest',
        ...     'space': 'MNI152NLin2009cAsym',
        ...     'method': 'seedToVoxel',
        ...     'seed': 'PCC'
        ... }
        >>> path = build_bids_path(
        ...     Path('/output'),
        ...     entities,
        ...     'effectSize',
        ...     '.nii.gz'
        ... )
        >>> # Returns: /output/sub-01/ses-1/sub-01_ses-1_task-rest_space-MNI_method-seedToVoxel_seed-PCC_effectSize.nii.gz
    """
    # Start with output directory
    if level == "participant":
        path = output_dir / f"sub-{entities['subject']}"
        if 'session' in entities and entities['session']:
            path = path / f"ses-{entities['session']}"
    else:  # group
        path = output_dir / "group"
        
        if 'method' in entities and entities['method']:
            path = path / entities['method']
        
        if 'analysis' in entities and entities['analysis']:
            path = path / entities['analysis']
        
        if 'session' in entities and entities['session']:
            path = path / f"ses-{entities['session']}"
    
    # Build filename from entities
    parts = []
    
    # Define entity order (following BIDS specification)
    entity_order = [
        'subject', 'session', 'task', 'acquisition', 'ceagent',
        'reconstruction', 'direction', 'run', 'echo', 'space',
        'denoise', 'condition', 'method', 'seed', 'roi', 'data', 'atlas', 'analysis',
        'desc', 'threshold', 'stat'
    ]
    
    for entity_name in entity_order:
        if entity_name in entities and entities[entity_name] is not None:
            value = entities[entity_name]
            # Handle lists (convert to hyphen-separated string)
            if isinstance(value, list):
                value = '-'.join(str(v) for v in value)
            parts.append(f"{entity_name}-{value}")
    
    # Add suffix
    parts.append(suffix)
    
    # Create filename
    filename = "_".join(parts) + extension
    
    # Ensure directory exists
    path.mkdir(parents=True, exist_ok=True)
    
    return path / filename


def query_participant_files(
    layout: BIDSLayout,
    entities: Dict[str, Any],
    logger: Optional[logging.Logger] = None
) -> Dict[str, list]:
    """Query denoised fMRI files for participant-level analysis.
    
    Args:
        layout: BIDSLayout instance
        entities: Dictionary of BIDS entities for filtering
        logger: Optional logger instance
    
    Returns:
        Dictionary with keys 'func', 'json' containing file lists
    
    Raises:
        BIDSError: If no denoised functional files found
    """
    from connectomix.utils.exceptions import BIDSError
    
    # Build query parameters for denoised files
    query_params = {
        'extension': 'nii.gz',
        'suffix': 'bold',
        'desc': 'denoised',
        'scope': 'derivatives',
        'invalid_filters': 'allow',  # Allow derivative-specific entities like 'desc'
    }
    
    # Add optional filters
    if entities.get('subject'):
        query_params['subject'] = entities['subject']
    if entities.get('session'):
        query_params['session'] = entities['session']
    if entities.get('task'):
        query_params['task'] = entities['task']
    if entities.get('run'):
        query_params['run'] = entities['run']
    if entities.get('space'):
        query_params['space'] = entities['space']
    
    # Query for functional files
    func_files = layout.get(**query_params)
    
    if len(func_files) == 0:
        raise BIDSError(
            f"No denoised functional files found matching criteria: {query_params}\n"
            f"Connectomix requires denoised fMRI data (desc-denoised_bold).\n"
            f"Denoised outputs can be obtained from fmridenoiser or similar denoising pipelines.\n"
            f"If denoised data is in non-standard location, specify with --derivatives"
        )
    
    # Deduplicate files by path (in case BIDS layout returns duplicates)
    seen_paths = set()
    func_files_unique = []
    for func_file in func_files:
        if func_file.path not in seen_paths:
            func_files_unique.append(func_file)
            seen_paths.add(func_file.path)
    
    # Get corresponding JSON sidecars
    json_files = []
    for func_file in func_files_unique:
        json_path = func_file.path.replace('.nii.gz', '.json')
        if Path(json_path).exists():
            json_files.append(json_path)
    
    if logger:
        logger.info(f"Found {len(func_files_unique)} denoised functional file(s)")
    
    return {
        'func': [f.path for f in func_files_unique],
        'json': json_files
    }
