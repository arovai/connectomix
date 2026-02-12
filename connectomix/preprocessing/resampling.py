"""Image resampling and geometric consistency checking."""

import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import nibabel as nib
import numpy as np
from nilearn.image import resample_to_img
from nilearn.image import resampling as resampling_module

from connectomix.utils.exceptions import PreprocessingError


def check_geometric_consistency(
    func_files: List[str],
    logger: Optional[logging.Logger] = None,
    reference_file: Optional[Path] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Check if all functional images have consistent geometry.
    
    Compares shape, voxel size, and affine transformation across all images.
    
    Args:
        func_files: List of paths to functional images
        logger: Optional logger instance
        reference_file: Optional reference file to compare against
    
    Returns:
        Tuple of (is_consistent, geometries_dict) where:
        - is_consistent: True if all images have same geometry
        - geometries_dict: Dictionary with geometry information
    
    Raises:
        PreprocessingError: If geometry checking fails
    """
    _logger = logger or logging.getLogger(__name__)
    
    if not func_files:
        return True, {}
    
    try:
        # Load first image as reference if not provided
        if reference_file is None:
            reference_file = Path(func_files[0])
        else:
            reference_file = Path(reference_file)
        
        reference_img = nib.load(str(reference_file))
        ref_shape = reference_img.shape[:3]
        ref_voxel_size = reference_img.header.get_zooms()[:3]
        ref_affine = reference_img.affine
        
        _logger.debug(f"Reference geometry: shape={ref_shape}, voxel_size={ref_voxel_size}")
        
        # Check all images against reference
        geometries = {
            'reference_file': str(reference_file),
            'reference_shape': list(ref_shape),
            'reference_voxel_size': list(ref_voxel_size),
            'images': []
        }
        
        is_consistent = True
        inconsistent_files = []
        
        for func_file in func_files:
            func_file = Path(func_file)
            try:
                img = nib.load(str(func_file))
                shape = img.shape[:3]
                voxel_size = img.header.get_zooms()[:3]
                affine = img.affine
                
                # Check consistency
                shape_match = shape == ref_shape
                voxel_match = np.allclose(voxel_size, ref_voxel_size, rtol=1e-5)
                affine_match = np.allclose(affine, ref_affine, rtol=1e-5)
                
                file_consistent = shape_match and voxel_match and affine_match
                
                geometries['images'].append({
                    'file': str(func_file.name),
                    'shape': list(shape),
                    'voxel_size': list(voxel_size),
                    'consistent': file_consistent
                })
                
                if not file_consistent:
                    is_consistent = False
                    inconsistent_files.append(func_file.name)
                    if not shape_match:
                        _logger.debug(f"  {func_file.name}: shape mismatch {shape} != {ref_shape}")
                    if not voxel_match:
                        _logger.debug(f"  {func_file.name}: voxel size mismatch {voxel_size} != {ref_voxel_size}")
                    if not affine_match:
                        _logger.debug(f"  {func_file.name}: affine mismatch")
            
            except Exception as e:
                _logger.warning(f"Could not load {func_file.name}: {e}")
                is_consistent = False
                inconsistent_files.append(func_file.name)
        
        if not is_consistent:
            _logger.warning(
                f"⚠ Geometry inconsistency detected in {len(inconsistent_files)} file(s) - "
                f"will resample to reference. Files: {', '.join(inconsistent_files[:5])}"
                + (f"... and {len(inconsistent_files) - 5} more" if len(inconsistent_files) > 5 else "")
            )
        
        return is_consistent, geometries
    
    except Exception as e:
        raise PreprocessingError(f"Geometry consistency check failed: {e}")


def resample_to_reference(
    func_path: Path,
    reference_img: nib.Nifti1Image,
    output_path: Path,
    logger: Optional[logging.Logger] = None,
) -> nib.Nifti1Image:
    """Resample a functional image to match a reference image.
    
    Uses nilearn's resample_to_img for interpolation-based resampling.
    
    Args:
        func_path: Path to functional image to resample
        reference_img: Reference image to resample to
        output_path: Path for output resampled image
        logger: Optional logger instance
    
    Returns:
        Resampled nibabel image
    
    Raises:
        PreprocessingError: If resampling fails
    """
    _logger = logger or logging.getLogger(__name__)
    
    func_path = Path(func_path)
    output_path = Path(output_path)
    
    try:
        # Load input image
        func_img = nib.load(str(func_path))
        
        # Check if resampling is already done
        if output_path.exists():
            _logger.info(f"Resampled image exists, skipping: {output_path.name}")
            return nib.load(str(output_path))
        
        _logger.info(f"Resampling {func_path.name} to reference geometry...")
        
        # Resample to reference space
        resampled_img = resample_to_img(
            func_img,
            reference_img,
            interpolation='continuous',  # Use continuous interpolation for fMRI
            copy=True,
            order='F',  # Fortran order for memory efficiency
        )
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save resampled image
        nib.save(resampled_img, str(output_path))
        _logger.info(f"Saved resampled image to: {output_path.name}")
        
        return resampled_img
    
    except Exception as e:
        raise PreprocessingError(f"Resampling {func_path.name} failed: {e}")


def save_geometry_info(
    img: nib.Nifti1Image,
    output_path: Path,
    reference_path: Path,
    reference_img: nib.Nifti1Image,
    original_path: Path,
    original_img: nib.Nifti1Image,
    source_json: Optional[Path] = None,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Save geometry information and resampling metadata to JSON.
    
    Preserves information about the resampling process for provenance
    and quality assurance.
    
    Args:
        img: Final resampled image
        output_path: Path for output JSON file
        reference_path: Path to reference image used for resampling
        reference_img: Reference image object
        original_path: Path to original (pre-resampling) image
        original_img: Original image object
        source_json: Optional path to source JSON metadata to include
        logger: Optional logger instance
    
    Raises:
        PreprocessingError: If saving fails
    """
    _logger = logger or logging.getLogger(__name__)
    output_path = Path(output_path)
    
    try:
        # Extract geometry information
        geometry_info = {
            'resampling': {
                'reference_file': str(reference_path),
                'original_file': str(original_path),
                'original_geometry': {
                    'shape': list(original_img.shape[:3]),
                    'voxel_size_mm': [float(x) for x in original_img.header.get_zooms()[:3]],
                    'affine': original_img.affine.tolist(),
                },
                'reference_geometry': {
                    'shape': list(reference_img.shape[:3]),
                    'voxel_size_mm': [float(x) for x in reference_img.header.get_zooms()[:3]],
                    'affine': reference_img.affine.tolist(),
                },
                'final_geometry': {
                    'shape': list(img.shape[:3]),
                    'voxel_size_mm': [float(x) for x in img.header.get_zooms()[:3]],
                    'affine': img.affine.tolist(),
                },
                'interpolation': 'continuous',
            }
        }
        
        # Load and merge source JSON if it exists
        if source_json and Path(source_json).exists():
            try:
                with open(source_json, 'r') as f:
                    source_data = json.load(f)
                # Merge source data under 'source_metadata' key
                geometry_info['source_metadata'] = source_data
            except Exception as e:
                _logger.warning(f"Could not load source JSON {source_json}: {e}")
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save to JSON
        with open(output_path, 'w') as f:
            json.dump(geometry_info, f, indent=2)
        
        _logger.debug(f"Saved geometry info to: {output_path.name}")
    
    except Exception as e:
        raise PreprocessingError(f"Failed to save geometry info: {e}")
