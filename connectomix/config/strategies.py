"""Denoising strategy specifications."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DenoisingStrategySpec:
    """Specification for a denoising strategy.
    
    Attributes:
        name: Strategy name
        confounds: List of confound column names to use
        is_rigid: Whether strategy includes rigid censoring parameters
        fd_threshold: FD threshold in cm (if rigid strategy)
        min_segment_length: Minimum segment length after motion censoring
        description: Human-readable description
    """
    name: str
    confounds: List[str]
    is_rigid: bool = False
    fd_threshold: Optional[float] = None
    min_segment_length: int = 0
    description: str = ""


# Predefined denoising strategies
DENOISING_STRATEGIES = {
    "minimal": DenoisingStrategySpec(
        name="minimal",
        confounds=["trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"],
        description="6 motion parameters only"
    ),
    "csfwm_6p": DenoisingStrategySpec(
        name="csfwm_6p",
        confounds=["csf", "white_matter", "trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"],
        description="CSF + WM + 6 motion parameters"
    ),
    "csfwm_12p": DenoisingStrategySpec(
        name="csfwm_12p",
        confounds=[
            "csf", "white_matter",
            "trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z",
            "trans_x_derivative_1", "trans_y_derivative_1", "trans_z_derivative_1",
            "rot_x_derivative_1", "rot_y_derivative_1", "rot_z_derivative_1"
        ],
        description="CSF + WM + 12 motion parameters (6 + derivatives)"
    ),
    "gs_csfwm_6p": DenoisingStrategySpec(
        name="gs_csfwm_6p",
        confounds=[
            "global_signal", "csf", "white_matter",
            "trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"
        ],
        description="Global + CSF + WM + 6 motion parameters"
    ),
    "gs_csfwm_12p": DenoisingStrategySpec(
        name="gs_csfwm_12p",
        confounds=[
            "global_signal", "csf", "white_matter",
            "trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z",
            "trans_x_derivative_1", "trans_y_derivative_1", "trans_z_derivative_1",
            "rot_x_derivative_1", "rot_y_derivative_1", "rot_z_derivative_1"
        ],
        description="Global + CSF + WM + 12 motion parameters"
    ),
    "csfwm_24p": DenoisingStrategySpec(
        name="csfwm_24p",
        confounds=[
            "csf", "white_matter",
            "trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z",
            "trans_x_derivative_1", "trans_y_derivative_1", "trans_z_derivative_1",
            "rot_x_derivative_1", "rot_y_derivative_1", "rot_z_derivative_1",
            "trans_x**2", "trans_y**2", "trans_z**2",
            "rot_x**2", "rot_y**2", "rot_z**2",
            "trans_x_derivative_1**2", "trans_y_derivative_1**2", "trans_z_derivative_1**2",
            "rot_x_derivative_1**2", "rot_y_derivative_1**2", "rot_z_derivative_1**2"
        ],
        description="CSF + WM + 24 motion parameters (6 + derivatives + squares)"
    ),
    "compcor_6p": DenoisingStrategySpec(
        name="compcor_6p",
        confounds=[
            "a_comp_cor_00", "a_comp_cor_01", "a_comp_cor_02",
            "a_comp_cor_03", "a_comp_cor_04", "a_comp_cor_05",
            "trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"
        ],
        description="6 aCompCor components + 6 motion parameters"
    ),
    "simpleGSR": DenoisingStrategySpec(
        name="simpleGSR",
        confounds=[
            "global_signal", "csf", "white_matter",
            "trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z",
            "trans_x_derivative_1", "trans_y_derivative_1", "trans_z_derivative_1",
            "rot_x_derivative_1", "rot_y_derivative_1", "rot_z_derivative_1",
            "trans_x**2", "trans_y**2", "trans_z**2",
            "rot_x**2", "rot_y**2", "rot_z**2",
            "trans_x_derivative_1**2", "trans_y_derivative_1**2", "trans_z_derivative_1**2",
            "rot_x_derivative_1**2", "rot_y_derivative_1**2", "rot_z_derivative_1**2"
        ],
        description="Global + CSF + WM + 24 motion (preserves time series)"
    ),
    "scrubbing5": DenoisingStrategySpec(
        name="scrubbing5",
        confounds=[
            "csf", "white_matter",
            "trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z",
            "trans_x_derivative_1", "trans_y_derivative_1", "trans_z_derivative_1",
            "rot_x_derivative_1", "rot_y_derivative_1", "rot_z_derivative_1",
            "trans_x**2", "trans_y**2", "trans_z**2",
            "rot_x**2", "rot_y**2", "rot_z**2",
            "trans_x_derivative_1**2", "trans_y_derivative_1**2", "trans_z_derivative_1**2",
            "rot_x_derivative_1**2", "rot_y_derivative_1**2", "rot_z_derivative_1**2"
        ],
        is_rigid=True,
        fd_threshold=0.5,
        min_segment_length=5,
        description="CSF/WM + 24 motion + FD=0.5cm censoring + 5-volume scrubbing"
    ),
}


def get_denoising_strategy(strategy_name: str) -> DenoisingStrategySpec:
    """Get denoising strategy specification.
    
    Args:
        strategy_name: Name of denoising strategy
    
    Returns:
        DenoisingStrategySpec object
    
    Raises:
        ValueError: If strategy not found
    """
    if strategy_name not in DENOISING_STRATEGIES:
        available = ", ".join(DENOISING_STRATEGIES.keys())
        raise ValueError(
            f"Unknown denoising strategy: {strategy_name}. "
            f"Available: {available}"
        )
    
    return DENOISING_STRATEGIES[strategy_name]


def list_denoising_strategies() -> List[DenoisingStrategySpec]:
    """Get list of all available denoising strategies.
    
    Returns:
        List of DenoisingStrategySpec objects
    """
    return list(DENOISING_STRATEGIES.values())
