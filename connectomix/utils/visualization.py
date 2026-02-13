"""Visualization functions for Connectomix.

This module provides plotting functions for visualizing analysis results
including design matrices, connectivity matrices, statistical maps, and
seed locations.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

logger = logging.getLogger(__name__)


def plot_design_matrix(
    design_matrix: pd.DataFrame,
    output_path: Optional[Path] = None,
    title: str = "Design Matrix",
    figsize: Tuple[float, float] = (8, 10),
    cmap: str = "RdBu_r",
) -> plt.Figure:
    """Plot design matrix as a heatmap.
    
    Visualizes the design matrix with subjects as rows and regressors as columns.
    
    Args:
        design_matrix: Design matrix DataFrame from build_design_matrix().
        output_path: Path to save figure. If None, figure is not saved.
        title: Plot title.
        figsize: Figure size (width, height) in inches.
        cmap: Colormap for heatmap.
    
    Returns:
        Matplotlib Figure object.
    
    Example:
        >>> fig = plot_design_matrix(design_matrix, output_path="design.png")
    """
    fig, ax = plt.subplots(figsize=figsize)
    
    # Normalize for better visualization
    data = design_matrix.values
    
    # Plot heatmap
    sns.heatmap(
        data,
        ax=ax,
        cmap=cmap,
        center=0,
        xticklabels=design_matrix.columns,
        yticklabels=design_matrix.index,
        cbar_kws={"label": "Value"},
    )
    
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Regressors", fontsize=12)
    ax.set_ylabel("Subjects", fontsize=12)
    
    # Rotate x labels for readability
    plt.xticks(rotation=45, ha="right")
    
    plt.tight_layout()
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Saved design matrix plot: {output_path}")
    
    return fig


def plot_connectivity_matrix(
    matrix: np.ndarray,
    labels: Optional[List[str]] = None,
    output_path: Optional[Path] = None,
    title: str = "Connectivity Matrix",
    figsize: Tuple[float, float] = (12, 10),
    cmap: str = "RdBu_r",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    annotate: bool = False,
    cluster: bool = False,
) -> plt.Figure:
    """Plot connectivity matrix as a heatmap.
    
    Visualizes ROI-to-ROI or seed-to-seed connectivity matrices.
    
    Args:
        matrix: Square connectivity matrix (N x N).
        labels: List of ROI/seed names. If None, uses indices.
        output_path: Path to save figure. If None, figure is not saved.
        title: Plot title.
        figsize: Figure size (width, height) in inches.
        cmap: Colormap for heatmap.
        vmin: Minimum value for colormap. If None, uses data min.
        vmax: Maximum value for colormap. If None, uses data max.
        annotate: If True, show values in cells (only for small matrices).
        cluster: If True, apply hierarchical clustering to reorder matrix.
    
    Returns:
        Matplotlib Figure object.
    
    Example:
        >>> fig = plot_connectivity_matrix(
        ...     corr_matrix, labels=roi_names, output_path="connectivity.png"
        ... )
    """
    n_regions = matrix.shape[0]
    
    # Generate labels if not provided
    if labels is None:
        labels = [f"ROI_{i+1}" for i in range(n_regions)]
    
    # Truncate labels if too many
    max_labels = 50
    show_labels = n_regions <= max_labels
    
    if cluster and n_regions > 2:
        # Apply hierarchical clustering
        from scipy.cluster.hierarchy import linkage, leaves_list
        from scipy.spatial.distance import squareform
        
        # Convert correlation to distance
        dist_matrix = 1 - np.abs(matrix)
        np.fill_diagonal(dist_matrix, 0)
        
        try:
            condensed = squareform(dist_matrix)
            linkage_matrix = linkage(condensed, method="average")
            order = leaves_list(linkage_matrix)
            
            # Reorder matrix and labels
            matrix = matrix[order][:, order]
            labels = [labels[i] for i in order]
        except Exception as e:
            logger.warning(f"Clustering failed: {e}. Using original order.")
    
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)
    
    # Set colormap limits
    if vmin is None:
        vmin = -1 if np.min(matrix) < 0 else 0
    if vmax is None:
        vmax = 1
    
    # Plot heatmap
    im = ax.imshow(
        matrix,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        aspect="equal",
    )
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label("Correlation", fontsize=12)
    
    # Add labels
    if show_labels:
        ax.set_xticks(range(n_regions))
        ax.set_yticks(range(n_regions))
        ax.set_xticklabels(labels, rotation=90, fontsize=8)
        ax.set_yticklabels(labels, fontsize=8)
    else:
        ax.set_xlabel(f"Regions (n={n_regions})", fontsize=12)
        ax.set_ylabel(f"Regions (n={n_regions})", fontsize=12)
    
    # Add annotations for small matrices
    if annotate and n_regions <= 20:
        for i in range(n_regions):
            for j in range(n_regions):
                text = f"{matrix[i, j]:.2f}"
                ax.text(j, i, text, ha="center", va="center", fontsize=6)
    
    ax.set_title(title, fontsize=14, fontweight="bold")
    
    plt.tight_layout()
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Saved connectivity matrix plot: {output_path}")
    
    return fig


def plot_stat_map(
    stat_map,
    output_path: Optional[Path] = None,
    title: str = "Statistical Map",
    threshold: Optional[float] = None,
    display_mode: str = "ortho",
    cut_coords: Optional[Union[int, List[float]]] = None,
    colorbar: bool = True,
    cmap: str = "cold_hot",
    figsize: Tuple[float, float] = (12, 4),
) -> plt.Figure:
    """Plot statistical map on brain template.
    
    Uses nilearn's plotting functions to display statistical maps.
    
    Args:
        stat_map: Statistical map (path, NIfTI image, or array).
        output_path: Path to save figure. If None, figure is not saved.
        title: Plot title.
        threshold: Threshold for display. Values below are transparent.
        display_mode: Display mode ('ortho', 'x', 'y', 'z', 'xz', 'yz', etc.).
        cut_coords: Coordinates for slices. If int, number of slices.
        colorbar: Whether to show colorbar.
        cmap: Colormap name.
        figsize: Figure size (width, height) in inches.
    
    Returns:
        Matplotlib Figure object.
    
    Example:
        >>> fig = plot_stat_map(t_map, threshold=3.0, output_path="tmap.png")
    """
    from nilearn import plotting
    
    fig = plt.figure(figsize=figsize)
    
    # Use nilearn's plot_stat_map
    display = plotting.plot_stat_map(
        stat_map,
        threshold=threshold,
        display_mode=display_mode,
        cut_coords=cut_coords,
        colorbar=colorbar,
        cmap=cmap,
        title=title,
        figure=fig,
    )
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Saved stat map plot: {output_path}")
    
    return fig


def plot_glass_brain(
    stat_map,
    output_path: Optional[Path] = None,
    title: str = "Glass Brain",
    threshold: Optional[float] = None,
    display_mode: str = "lyrz",
    colorbar: bool = True,
    cmap: str = "cold_hot",
    figsize: Tuple[float, float] = (12, 4),
) -> plt.Figure:
    """Plot statistical map as glass brain projection.
    
    Shows 3D projection of significant regions on transparent brain.
    
    Args:
        stat_map: Statistical map (path, NIfTI image, or array).
        output_path: Path to save figure. If None, figure is not saved.
        title: Plot title.
        threshold: Threshold for display.
        display_mode: Display mode ('lyrz', 'lzr', 'lyr', etc.).
        colorbar: Whether to show colorbar.
        cmap: Colormap name.
        figsize: Figure size (width, height) in inches.
    
    Returns:
        Matplotlib Figure object.
    """
    from nilearn import plotting
    
    fig = plt.figure(figsize=figsize)
    
    display = plotting.plot_glass_brain(
        stat_map,
        threshold=threshold,
        display_mode=display_mode,
        colorbar=colorbar,
        cmap=cmap,
        title=title,
        figure=fig,
    )
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Saved glass brain plot: {output_path}")
    
    return fig


def plot_seeds(
    seed_coords: np.ndarray,
    seed_names: List[str],
    output_path: Optional[Path] = None,
    title: str = "Seed Locations",
    marker_size: int = 100,
    figsize: Tuple[float, float] = (12, 4),
) -> plt.Figure:
    """Plot seed locations on brain template.
    
    Visualizes spherical seed locations on anatomical template.
    
    Args:
        seed_coords: Array of seed coordinates, shape (N, 3).
        seed_names: List of seed names.
        output_path: Path to save figure. If None, figure is not saved.
        title: Plot title.
        marker_size: Size of seed markers.
        figsize: Figure size (width, height) in inches.
    
    Returns:
        Matplotlib Figure object.
    """
    from nilearn import plotting
    
    fig = plt.figure(figsize=figsize)
    
    # Create color palette
    n_seeds = len(seed_names)
    colors = plt.cm.Set1(np.linspace(0, 1, max(n_seeds, 9)))[:n_seeds]
    
    # Plot on glass brain
    display = plotting.plot_glass_brain(
        None,
        display_mode="lyrz",
        figure=fig,
    )
    
    # Add seed markers
    display.add_markers(
        seed_coords,
        marker_color=colors,
        marker_size=marker_size,
    )
    
    # Add legend
    for i, (name, color) in enumerate(zip(seed_names, colors)):
        plt.scatter([], [], c=[color], s=50, label=name)
    
    plt.legend(
        loc="upper right",
        bbox_to_anchor=(1.15, 1),
        fontsize=10,
    )
    
    plt.suptitle(title, fontsize=14, fontweight="bold")
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Saved seeds plot: {output_path}")
    
    return fig


def plot_cluster_locations(
    cluster_table: pd.DataFrame,
    stat_map,
    output_path: Optional[Path] = None,
    title: str = "Significant Clusters",
    figsize: Tuple[float, float] = (12, 8),
) -> plt.Figure:
    """Plot cluster peak locations on brain.
    
    Visualizes cluster peaks from cluster table.
    
    Args:
        cluster_table: DataFrame from get_cluster_table().
        stat_map: Statistical map for background.
        output_path: Path to save figure. If None, figure is not saved.
        title: Plot title.
        figsize: Figure size (width, height) in inches.
    
    Returns:
        Matplotlib Figure object.
    """
    from nilearn import plotting
    
    if cluster_table.empty:
        logger.warning("Empty cluster table, nothing to plot")
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No significant clusters", ha="center", va="center", fontsize=14)
        ax.axis("off")
        return fig
    
    fig = plt.figure(figsize=figsize)
    
    # Extract coordinates
    coords = cluster_table[["X", "Y", "Z"]].values
    
    # Get cluster sizes for marker scaling
    if "Cluster Size (voxels)" in cluster_table.columns:
        sizes = cluster_table["Cluster Size (voxels)"].values
        sizes = 50 + 200 * (sizes / sizes.max())
    else:
        sizes = np.full(len(coords), 100)
    
    # Plot stat map
    display = plotting.plot_stat_map(
        stat_map,
        display_mode="ortho",
        figure=fig,
        title=title,
    )
    
    # Add cluster markers
    display.add_markers(
        coords,
        marker_color="yellow",
        marker_size=sizes,
    )
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Saved cluster locations plot: {output_path}")
    
    return fig


def plot_qc_metrics(
    metrics: Dict[str, float],
    output_path: Optional[Path] = None,
    title: str = "Quality Control Metrics",
    figsize: Tuple[float, float] = (10, 6),
) -> plt.Figure:
    """Plot quality control metrics as bar chart.
    
    Visualizes QC metrics like tSNR, noise reduction, etc.
    
    Args:
        metrics: Dictionary of metric names to values.
        output_path: Path to save figure. If None, figure is not saved.
        title: Plot title.
        figsize: Figure size (width, height) in inches.
    
    Returns:
        Matplotlib Figure object.
    """
    fig, ax = plt.subplots(figsize=figsize)
    
    names = list(metrics.keys())
    values = list(metrics.values())
    
    # Create bar plot
    bars = ax.bar(range(len(names)), values, color=sns.color_palette("viridis", len(names)))
    
    # Add value labels on bars
    for bar, value in zip(bars, values):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height,
            f"{value:.2f}",
            ha="center",
            va="bottom",
            fontsize=10,
        )
    
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha="right")
    ax.set_ylabel("Value", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    
    plt.tight_layout()
    
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        logger.info(f"Saved QC metrics plot: {output_path}")
    
    return fig


def _compute_color_scale(
    img_data: np.ndarray,
    threshold: float = 0.0,
    scale_factor: float = 1.2,
) -> Tuple[float, float]:
    """Compute symmetric color scale (vmin/vmax) for statistical maps.
    
    Implements robust, threshold-aware color scaling:
    1. Extract valid (non-NaN) data
    2. Apply threshold filtering (|value| ≥ threshold)
    3. Compute 99th/1st percentile bounds
    4. Apply 1.2× scaling factor for visual enhancement
    5. Establish symmetry around zero
    6. Ensure minimum range of ±1.0
    
    Args:
        img_data: 3D array of statistical values
        threshold: Display threshold (default: 0.0)
        scale_factor: Multiplier for visual enhancement (default: 1.2)
    
    Returns:
        Tuple of (vmin, vmax) for symmetric color scaling around zero
    """
    # Extract valid (non-NaN) values
    valid_data = img_data[~np.isnan(img_data)]
    
    if len(valid_data) == 0:
        return -1.0, 1.0
    
    # Apply threshold filtering
    if threshold > 0:
        above_threshold = valid_data[np.abs(valid_data) >= threshold]
        if len(above_threshold) > 0:
            valid_data = above_threshold
        # If no values above threshold, use all valid data
    
    # Separate positive and negative values
    positive_vals = valid_data[valid_data > 0]
    negative_vals = valid_data[valid_data < 0]
    
    # Compute percentile bounds
    pos_max = np.percentile(positive_vals, 99) if len(positive_vals) > 0 else 0
    neg_min = np.percentile(negative_vals, 1) if len(negative_vals) > 0 else 0
    
    # Apply scaling factor
    pos_max *= scale_factor
    neg_min *= scale_factor
    
    # Establish symmetry: use maximum absolute value for both
    abs_max = max(np.abs(pos_max), np.abs(neg_min))
    
    # Ensure minimum range
    if abs_max < 0.1:
        abs_max = 1.0
    
    return -abs_max, abs_max


def _fig_to_base64(fig: plt.Figure, dpi: int = 100) -> str:
    """Convert matplotlib figure to base64 PNG for HTML embedding.
    
    Args:
        fig: Matplotlib figure object
        dpi: Resolution in dots per inch (default: 100)
    
    Returns:
        Base64 encoded PNG data URI string
    """
    import io
    import base64
    
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', dpi=dpi, bbox_inches='tight', facecolor='white')
    buffer.seek(0)
    image_data = base64.b64encode(buffer.read()).decode()
    buffer.close()
    return image_data


def _create_seed_sphere(
    reference_img,
    seed_coords: np.ndarray,
    radius: float,
) -> "nib.Nifti1Image":
    """Create a NIfTI image representing a spherical seed region.
    
    Creates a binary 3D image with 1s inside the sphere and 0s outside,
    in the same space as the reference image.
    
    Args:
        reference_img: Reference NIfTI image defining the space
        seed_coords: Seed coordinates [x, y, z] in mm (MNI space)
        radius: Sphere radius in mm
    
    Returns:
        NIfTI image with sphere mask
    """
    import nibabel as nib
    
    # Get the shape and affine from reference image
    ref_data = reference_img.get_fdata()
    ref_affine = reference_img.affine
    
    # Create an empty sphere mask
    sphere_data = np.zeros_like(ref_data)
    
    # Get inverse affine to convert MNI coords to voxel indices
    inv_affine = np.linalg.inv(ref_affine)
    
    # Convert seed coordinates from MNI to voxel indices
    seed_voxel = inv_affine @ np.array([*seed_coords, 1])
    seed_voxel = seed_voxel[:3]  # Drop homogeneous coordinate
    
    # Create distance matrix for all voxels
    indices = np.indices(ref_data.shape)
    distances = np.sqrt(
        (indices[0] - seed_voxel[0])**2 +
        (indices[1] - seed_voxel[1])**2 +
        (indices[2] - seed_voxel[2])**2
    )
    
    # Estimate voxel size in mm (using average of diagonal elements)
    voxel_size = np.mean(np.abs(np.diag(ref_affine[:3, :3])))
    
    # Convert radius from mm to voxels
    radius_voxels = radius / voxel_size
    
    # Create binary sphere mask
    sphere_data[distances <= radius_voxels] = 1.0
    
    # Create NIfTI image with same affine as reference
    sphere_img = nib.Nifti1Image(sphere_data, affine=ref_affine)
    
    return sphere_img


def plot_lightbox_axial_slices(
    stat_map,
    seed_coords: Optional[np.ndarray] = None,
    seed_radius: Optional[float] = None,
    output_path: Optional[Path] = None,
    title: str = "Statistical Map - Axial Slices",
    n_slices: int = 12,
    n_cols: int = 3,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
) -> plt.Figure:
    """Plot statistical map in orthogonal view centered at seed location.
    
    Creates an orthogonal (3-plane) visualization of a statistical map
    centered at the specified seed coordinates using nilearn's plot_stat_map.
    Optionally overlays a green sphere representing the seed region.
    
    Args:
        stat_map: Statistical map (path string, Path, or NIfTI image object)
        seed_coords: Seed coordinates [x, y, z] in mm to center the view. If None, uses image center.
        seed_radius: Seed sphere radius in mm. If provided, overlays green sphere on the plot.
        output_path: Path to save figure as PNG (optional)
        title: Figure title (default: "Statistical Map - Axial Slices")
        n_slices: Number of slices to display (default: 12) - unused with ortho mode
        n_cols: Number of columns in grid layout (default: 3) - unused with ortho mode
        vmin: Manual minimum for color scale. If None, computed from data.
        vmax: Manual maximum for color scale. If None, computed from data.
    
    Returns:
        Matplotlib Figure object
    
    Example:
        >>> fig = plot_lightbox_axial_slices(
        ...     "path/to/tmap.nii.gz",
        ...     seed_coords=np.array([0, 0, 0]),
        ...     seed_radius=5.0,
        ...     title="First-Level T-Map centered at seed"
        ... )
    """
    from nilearn import plotting
    import nibabel as nib
    
    try:
        # Load image if path
        if isinstance(stat_map, (str, Path)):
            stat_map_img = nib.load(stat_map)
        else:
            stat_map_img = stat_map
        
        stat_data = stat_map_img.get_fdata()
        
        if stat_data.ndim != 3:
            raise ValueError(f"Expected 3D image, got shape {stat_data.shape}")
        
        # Compute symmetric color scale if not provided
        if vmin is None or vmax is None:
            # Threshold is always 0 (no masking)
            vmin_computed, vmax_computed = _compute_color_scale(stat_data, threshold=0.0)
            if vmin is None:
                vmin = vmin_computed
            if vmax is None:
                vmax = vmax_computed
        
        # Convert seed_coords to list format expected by nilearn
        if seed_coords is not None:
            cut_coords = tuple(seed_coords)
        else:
            cut_coords = None
        
        # Use nilearn's plot_stat_map with orthogonal display mode
        # Larger figure size: width for images + colorbar, height for 3 orthogonal slices
        fig = plt.figure(figsize=(16, 5))
        
        display = plotting.plot_stat_map(
            stat_map_img,
            threshold=0,  # Always use threshold=0 (no masking)
            display_mode='ortho',  # 3-plane orthogonal view
            cut_coords=cut_coords,  # Centered at seed location
            colorbar=True,
            cmap='cold_hot',
            title=title,
            figure=fig,
            vmin=vmin,
            vmax=vmax,
        )
        
        # Overlay seed sphere if both coordinates and radius are provided
        if seed_coords is not None and seed_radius is not None:
            try:
                # Create a sphere mask at the seed location
                seed_sphere_img = _create_seed_sphere(stat_map_img, seed_coords, seed_radius)
                
                # Add the sphere overlay with bright green colormap
                display.add_overlay(
                    seed_sphere_img,
                    cmap='Greens',
                    alpha=0.6,
                    vmin=0.5,
                    vmax=1.0,
                )
                logger.debug(f"Added seed sphere overlay: coords={seed_coords}, radius={seed_radius}mm")
            except Exception as sphere_error:
                logger.warning(f"Could not overlay seed sphere: {sphere_error}")
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_path, dpi=100, bbox_inches='tight', facecolor='white')
            logger.info(f"Saved stat map orthogonal view plot: {output_path}")
        
        return fig
        
    except Exception as e:
        logger.warning(f"Could not create stat map plot: {e}")
        
        # Fallback: generate error message figure
        fig = plt.figure(figsize=(12, 6), dpi=100)
        ax = fig.add_subplot(111)
        ax.text(
            0.5, 0.5,
            f"Error generating stat map visualization\n\n{str(e)}",
            ha='center', va='center', fontsize=12, color='red',
            transform=ax.transAxes,
        )
        ax.axis('off')
        
        return fig


def close_all_figures():
    """Close all matplotlib figures to free memory."""
    plt.close("all")
    logger.debug("Closed all matplotlib figures")
