"""ROI-to-voxel connectivity analysis using GLM."""

from pathlib import Path
from typing import List, Optional, Dict, Union, Tuple
import logging
import numpy as np
import pandas as pd
import nibabel as nib
from nilearn.glm.first_level import FirstLevelModel
from nilearn import image

from connectomix.connectivity.extraction import extract_single_region_timeseries
from connectomix.connectivity.seed_to_voxel import load_brain_mask, compute_glm_contrast_map
from connectomix.data.atlases import load_atlas
from connectomix.io.writers import save_nifti_with_sidecar
from connectomix.utils.exceptions import ConnectivityError
from connectomix.utils.validation import sanitize_filename



def load_roi_mask(
    roi_definition: Union[str, Path],
    atlas_name: Optional[str] = None,
    roi_label: Optional[str] = None,
    target_img: Optional[nib.Nifti1Image] = None,
    logger: Optional[logging.Logger] = None
) -> Tuple[nib.Nifti1Image, str]:
    """Load or extract a ROI mask from flexible sources.
    
    Supports two approaches:
    1. Direct mask file path: Load a pre-existing binary mask file
    2. Atlas label: Extract ROI from atlas using the provided label
    
    Args:
        roi_definition: Either path to mask file OR atlas identifier (if using atlas)
        atlas_name: Name of atlas (required if using atlas-based approach)
                   Must be a valid atlas identifier from ATLAS_REGISTRY
        roi_label: Label/name of ROI within the atlas (required if atlas_name provided)
        target_img: Optional target image for resampling the mask to match dimensions
        logger: Optional logger instance
    
    Returns:
        Tuple of (roi_mask_img, roi_name):
        - roi_mask_img: Binary NIfTI image defining the ROI
        - roi_name: String name/identifier of the ROI
    
    Raises:
        ConnectivityError: If mask cannot be loaded, atlas not found, or label not in atlas
        ValueError: If conflicting arguments provided or missing required arguments
    
    Examples:
        # Load from file
        mask, name = load_roi_mask("/path/to/roi_mask.nii.gz")
        
        # Extract from atlas by label
        mask, name = load_roi_mask("schaefer_100", atlas_name="schaefer_100", 
                                     roi_label="17Networks_LH_Vis_1")
    """
    if logger:
        logger.debug(f"Loading ROI mask with definition: {roi_definition}, "
                    f"atlas: {atlas_name}, label: {roi_label}")
    
    # Case 1: Direct mask file
    if atlas_name is None:
        # Using mask file approach
        mask_path = Path(roi_definition)
        
        if not mask_path.exists():
            raise ConnectivityError(f"Mask file not found: {mask_path}")
        
        try:
            roi_mask_img = nib.load(mask_path)
            roi_name = mask_path.stem  # Use filename without extension as roi name
            
            if logger:
                logger.debug(f"  Loaded mask from file: {mask_path.name}")
            
            # Resample to target image if needed
            if target_img is not None and roi_mask_img.shape[:3] != target_img.shape[:3]:
                if logger:
                    logger.debug(f"  Resampling mask from {roi_mask_img.shape[:3]} "
                               f"to {target_img.shape[:3]}")
                # Use target_affine for more efficient resampling
                roi_mask_img = image.resample_to_img(roi_mask_img, target_img, 
                                                      interpolation='nearest')
                # Ensure mask stays binary after resampling
                mask_data = roi_mask_img.get_fdata()
                mask_data = (mask_data > 0.5).astype(np.int16)
                roi_mask_img = nib.Nifti1Image(mask_data, roi_mask_img.affine, roi_mask_img.header)
            
            return roi_mask_img, roi_name
            
        except Exception as e:
            raise ConnectivityError(f"Failed to load mask file {mask_path}: {e}")
    
    # Case 2: Extract from atlas using label
    else:
        if roi_label is None:
            raise ValueError(
                "roi_label must be provided when using atlas_name"
            )
        
        try:
            # Clean atlas name and label (defensive against parsing issues)
            atlas_name_clean = atlas_name.strip().rstrip(',') if isinstance(atlas_name, str) else atlas_name
            roi_label_clean = roi_label.strip().rstrip(',') if isinstance(roi_label, str) else roi_label
            
            # Load atlas and labels
            atlas_img, atlas_labels = load_atlas(atlas_name_clean)
            
            if logger:
                logger.debug(f"  Loaded atlas '{atlas_name_clean}' with {len(atlas_labels)} regions")
            
            # Find index of the requested label
            label_idx = None
            for idx, label in enumerate(atlas_labels):
                if label.lower() == roi_label_clean.lower():
                    label_idx = idx + 1  # Atlas indices are 1-based
                    break
            
            if label_idx is None:
                available_labels = "\n    ".join(atlas_labels[:10])  # Show first 10
                n_total = len(atlas_labels)
                more_text = f"\n    ... and {n_total - 10} more" if n_total > 10 else ""
                raise ConnectivityError(
                    f"Label '{roi_label_clean}' not found in atlas '{atlas_name_clean}'\n"
                    f"Available labels (first 10):\n    {available_labels}{more_text}"
                )
            
            # Extract ROI mask from atlas
            atlas_data = atlas_img.get_fdata()
            roi_data = (atlas_data == label_idx).astype(np.int16)
            
            # Create binary mask image
            roi_mask_img = nib.Nifti1Image(roi_data, atlas_img.affine, atlas_img.header)
            
            if logger:
                n_voxels = np.sum(roi_data > 0)
                logger.debug(f"  Extracted ROI '{roi_label_clean}' (index {label_idx}) "
                           f"with {n_voxels} voxels")
            
            # Resample to target image if needed
            if target_img is not None and roi_mask_img.shape[:3] != target_img.shape[:3]:
                if logger:
                    logger.debug(f"  Resampling mask from {roi_mask_img.shape[:3]} "
                               f"to {target_img.shape[:3]}")
                roi_mask_img = image.resample_to_img(roi_mask_img, target_img,
                                                      interpolation='nearest')
                # Ensure mask stays binary after resampling
                mask_data = roi_mask_img.get_fdata()
                mask_data = (mask_data > 0.5).astype(np.int16)
                roi_mask_img = nib.Nifti1Image(mask_data, roi_mask_img.affine, roi_mask_img.header)
            
            return roi_mask_img, roi_label_clean
            
        except ConnectivityError:
            raise
        except Exception as e:
            raise ConnectivityError(
                f"Failed to extract ROI '{roi_label_clean}' from atlas '{atlas_name_clean}': {e}"
            )


def compute_roi_to_voxel(
    func_img: nib.Nifti1Image,
    roi_mask: nib.Nifti1Image,
    roi_name: str,
    output_path: Path,
    brain_mask: Optional[nib.Nifti1Image] = None,
    logger: Optional[logging.Logger] = None,
    t_r: Optional[float] = None
) -> Path:
    """Compute ROI-to-voxel connectivity using GLM.
    
    Creates a 3D brain map showing correlation strength between the ROI
    and every voxel in the brain.
    
    Args:
        func_img: Functional image (4D)
        roi_mask: Binary mask defining the ROI
        roi_name: Name of ROI region (for metadata)
        output_path: Path for output effect size map
        brain_mask: Brain mask image restricting analysis to brain voxels
        logger: Optional logger instance
        t_r: Repetition time in seconds
    
    Returns:
        Path to saved effect size map
    
    Raises:
        ConnectivityError: If analysis fails
    """
    if logger:
        logger.info(f"Computing ROI-to-voxel connectivity: {roi_name}")
    
    try:
        # Extract ROI time series (average across voxels in mask)
        roi_timeseries = extract_single_region_timeseries(
            func_img,
            roi_mask,
            logger
        )
        
        if logger:
            logger.debug(f"  ROI time series shape: {roi_timeseries.shape}")
            logger.debug(f"  ROI time series stats: mean={roi_timeseries.mean():.6f}, "
                        f"std={roi_timeseries.std():.6f}, range=[{roi_timeseries.min():.6f}, {roi_timeseries.max():.6f}]")
        
        # Validate ROI time series quality
        if np.allclose(roi_timeseries, 0):
            raise ConnectivityError(
                f"ROI time series for {roi_name} is all zeros. "
                f"Check if the ROI mask is inside the functional image."
            )
        
        if np.std(roi_timeseries) < 1e-10:
            raise ConnectivityError(
                f"ROI time series for {roi_name} has no variance "
                f"(std={np.std(roi_timeseries):.2e}). "
                f"Check if the ROI mask contains valid voxels."
            )
        
        # Use shared GLM computation function
        metadata = {
            'ROIName': roi_name,
            'AnalysisMethod': 'roiToVoxel',
        }
        
        effect_size_map = compute_glm_contrast_map(
            func_img=func_img,
            timeseries=roi_timeseries,
            region_name=roi_name,
            output_path=output_path,
            brain_mask=brain_mask,
            regressor_name='roi',
            logger=logger,
            t_r=t_r,
            metadata=metadata,
        )
        
        # Compute ROI center-of-mass for visualization and metadata
        from scipy import ndimage
        roi_data = roi_mask.get_fdata()
        roi_affine = roi_mask.affine
        roi_voxel_com = np.array(ndimage.center_of_mass(roi_data > 0))
        roi_world_com = roi_affine @ np.append(roi_voxel_com, 1)
        cut_coords = tuple(roi_world_com[:3].astype(float))
        
        if logger:
            logger.debug(f"  ROI center-of-mass (mm): {cut_coords}")
        
        # Update metadata JSON with cut_coords
        import json
        json_path = output_path.with_suffix('.json')
        if json_path.exists():
            with open(json_path, 'r') as f:
                json_metadata = json.load(f)
            json_metadata['ROI_CenterOfMass_mm'] = [float(x) for x in cut_coords]
            with open(json_path, 'w') as f:
                json.dump(json_metadata, f, indent=2)
        
        # Create visualization with ROI mask overlay
        try:
            from nilearn import plotting as nplot
            import matplotlib.pyplot as plt
            
            # Create orthogonal plot
            fig = plt.figure(figsize=(16, 5))
            display = nplot.plot_stat_map(
                effect_size_map,
                threshold=0,
                display_mode='ortho',
                cut_coords=cut_coords,
                colorbar=True,
                cmap='cold_hot',
                title=f"Connectivity Map - {roi_name}",
                figure=fig,
            )
            
            # Overlay ROI mask
            try:
                # Ensure ROI mask has the same shape and affine as effect_size_map
                if roi_mask.shape[:3] != effect_size_map.shape[:3]:
                    if logger:
                        logger.debug(f"  Resampling ROI mask from {roi_mask.shape[:3]} "
                                   f"to {effect_size_map.shape[:3]} for overlay")
                    from nilearn import image as nimg
                    roi_mask = nimg.resample_to_img(roi_mask, effect_size_map, 
                                                     interpolation='nearest')
                
                # Ensure mask data is float and properly scaled for overlay
                mask_data = roi_mask.get_fdata().astype(np.float32)
                # Ensure values are 0-1 (binary)
                mask_data = (mask_data > 0.5).astype(np.float32)
                
                # Validate mask has non-zero values
                n_nonzero = np.sum(mask_data > 0)
                if logger:
                    logger.debug(f"  ROI mask: {n_nonzero} voxels, shape={mask_data.shape}")
                
                if n_nonzero > 0:
                    roi_mask_display = nib.Nifti1Image(mask_data, effect_size_map.affine, 
                                                        effect_size_map.header)
                    
                    display.add_contours(
                        roi_mask_display,
                        levels=[0.5],
                        colors='lime',
                        linewidths=2.0,
                    )
                    if logger:
                        logger.debug(f"  Added ROI mask contours in green")
                else:
                    if logger:
                        logger.warning(f"  ROI mask is empty (no voxels)")
            except Exception as roi_overlay_error:
                if logger:
                    logger.warning(f"  Could not overlay ROI mask: {roi_overlay_error}")
                    logger.debug(f"  ROI overlay error details:", exc_info=True)
            
            # Save plot to figures directory
            # Remove .nii/.nii.gz extension and add .png
            png_name = output_path.name.replace('.nii.gz', '').replace('.nii', '') + '.png'
            plot_output = output_path.parent.parent / 'figures' / png_name
            plot_output.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(plot_output, dpi=100, bbox_inches='tight')
            plt.close(fig)
            
            if logger:
                logger.info(f"  Saved plot: {plot_output.name}")
        
        except Exception as plot_error:
            if logger:
                logger.warning(f"Could not create visualization: {plot_error}")
        
        return output_path
    
    except ConnectivityError:
        raise
    except Exception as e:
        raise ConnectivityError(f"ROI-to-voxel analysis failed for {roi_name}: {e}")



def compute_multiple_rois_to_voxel(
    func_img: nib.Nifti1Image,
    roi_masks: List[nib.Nifti1Image],
    roi_names: List[str],
    output_dir: Path,
    output_pattern: str,
    logger: Optional[logging.Logger] = None,
    t_r: Optional[float] = None
) -> List[Path]:
    """Compute ROI-to-voxel connectivity for multiple ROIs.
    
    Args:
        func_img: Functional image (4D)
        roi_masks: List of binary mask images
        roi_names: List of ROI region names
        output_dir: Directory for output maps
        output_pattern: Filename pattern with {roi_name} placeholder
        logger: Optional logger instance
        t_r: Repetition time in seconds
    
    Returns:
        List of paths to saved effect size maps
    
    Raises:
        ConnectivityError: If analysis fails
    """
    if len(roi_names) != len(roi_masks):
        raise ConnectivityError(
            f"Number of ROI names ({len(roi_names)}) doesn't match "
            f"number of masks ({len(roi_masks)})"
        )
    
    output_paths = []
    
    for roi_name, roi_mask in zip(roi_names, roi_masks):
        # Build output path with sanitized roi_name to handle spaces and special characters
        safe_roi_name = sanitize_filename(roi_name)
        output_filename = output_pattern.format(roi_name=safe_roi_name)
        output_path = output_dir / output_filename
        
        # Compute connectivity
        result_path = compute_roi_to_voxel(
            func_img=func_img,
            roi_mask=roi_mask,
            roi_name=roi_name,
            output_path=output_path,
            logger=logger,
            t_r=t_r
        )
        
        output_paths.append(result_path)
    
    return output_paths


def compute_roi_to_voxel_flexible(
    func_img: nib.Nifti1Image,
    roi_definition: Union[str, Path],
    output_path: Path,
    atlas_name: Optional[str] = None,
    roi_label: Optional[str] = None,
    brain_mask: Optional[nib.Nifti1Image] = None,
    logger: Optional[logging.Logger] = None,
    t_r: Optional[float] = None
) -> Path:
    """Compute ROI-to-voxel connectivity with flexible ROI specification.
    
    This is a convenience wrapper around compute_roi_to_voxel that handles
    loading ROI masks from either files or atlas labels.
    
    Args:
        func_img: Functional image (4D)
        roi_definition: Either path to mask file OR atlas identifier
        output_path: Path for output effect size map
        atlas_name: Atlas identifier (required if roi_definition is atlas-based)
        roi_label: Label within atlas (required if atlas_name is provided)
        brain_mask: Optional brain mask image for restricting analysis
        logger: Optional logger instance
        t_r: Repetition time in seconds
    
    Returns:
        Path to saved effect size map
    
    Raises:
        ConnectivityError: If analysis fails
        ValueError: If conflicting arguments provided
    
    Example:
        # From file
        result = compute_roi_to_voxel_flexible(
            func_img, "/path/to/roi_mask.nii.gz", output_path,
            logger=logger
        )
        
        # From atlas label
        result = compute_roi_to_voxel_flexible(
            func_img, "schaefer_100", output_path,
            atlas_name="schaefer_100", 
            roi_label="17Networks_LH_Vis_1",
            logger=logger
        )
    """
    try:
        # Load ROI mask using flexible approach
        roi_mask, roi_name = load_roi_mask(
            roi_definition=roi_definition,
            atlas_name=atlas_name,
            roi_label=roi_label,
            target_img=func_img,
            logger=logger
        )
        
        # Compute connectivity
        return compute_roi_to_voxel(
            func_img=func_img,
            roi_mask=roi_mask,
            roi_name=roi_name,
            output_path=output_path,
            brain_mask=brain_mask,
            logger=logger,
            t_r=t_r
        )
    
    except Exception as e:
        raise ConnectivityError(f"ROI-to-voxel connectivity computation failed: {e}")


def compute_multiple_rois_to_voxel_flexible(
    func_img: nib.Nifti1Image,
    roi_definitions: List[Tuple[Union[str, Path], Optional[str], Optional[str]]],
    output_dir: Path,
    output_pattern: str,
    atlas_name: Optional[str] = None,
    brain_mask: Optional[nib.Nifti1Image] = None,
    logger: Optional[logging.Logger] = None,
    t_r: Optional[float] = None
) -> List[Path]:
    """Compute ROI-to-voxel connectivity for multiple ROIs with flexible specs.
    
    This function allows specifying ROIs as a mix of:
    - File paths to mask images
    - Atlas labels (when used with an atlas_name)
    
    Args:
        func_img: Functional image (4D)
        roi_definitions: List of tuples (roi_def, roi_label, roi_name_override)
                        where roi_def is path or atlas ID,
                        roi_label is label when using atlases (None for files),
                        roi_name_override is optional name override
        output_dir: Directory for output maps
        output_pattern: Filename pattern with {roi_name} placeholder
        atlas_name: Atlas identifier (used for atlas-based ROIs in roi_definitions)
        brain_mask: Optional brain mask image
        logger: Optional logger instance
        t_r: Repetition time in seconds
    
    Returns:
        List of paths to saved effect size maps
    
    Raises:
        ConnectivityError: If analysis fails
    """
    output_paths = []
    
    for roi_def_tuple in roi_definitions:
        # Handle both 2-tuple and 3-tuple formats
        if len(roi_def_tuple) == 2:
            roi_def, roi_label = roi_def_tuple
            roi_name_override = None
        elif len(roi_def_tuple) == 3:
            roi_def, roi_label, roi_name_override = roi_def_tuple
        else:
            raise ValueError(
                f"ROI definition tuples must be (roi_def, roi_label) "
                f"or (roi_def, roi_label, roi_name_override), got: {roi_def_tuple}"
            )
        
        # Load ROI mask
        roi_mask, roi_name = load_roi_mask(
            roi_definition=roi_def,
            atlas_name=atlas_name,
            roi_label=roi_label,
            target_img=func_img,
            logger=logger
        )
        
        # Use override name if provided
        if roi_name_override:
            roi_name = roi_name_override
        
        # Build output path with sanitized roi_name to handle spaces and special characters
        safe_roi_name = sanitize_filename(roi_name)
        output_filename = output_pattern.format(roi_name=safe_roi_name)
        output_path = output_dir / output_filename
        
        # Compute connectivity
        result_path = compute_roi_to_voxel(
            func_img=func_img,
            roi_mask=roi_mask,
            roi_name=roi_name,
            output_path=output_path,
            brain_mask=brain_mask,
            logger=logger,
            t_r=t_r
        )
        
        output_paths.append(result_path)
    
    return output_paths
