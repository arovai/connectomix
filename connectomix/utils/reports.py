"""HTML report generation for Connectomix participant-level analyses.

This module provides comprehensive HTML report generation with:
- Analysis parameters and methods documentation
- Connectivity matrix visualizations
- Denoising timecourse plots
- Quality assurance metrics
- Scientific references
- Downloadable figures

Example:
    >>> from connectomix.utils.reports import ParticipantReportGenerator
    >>> report = ParticipantReportGenerator(
    ...     subject_id="01",
    ...     session="1",
    ...     config=config,
    ...     output_dir=Path("/data/output")
    ... )
    >>> report.add_connectivity_matrix(matrix, labels, "schaefer2018n100")
    >>> report.add_denoising_plot(confounds_df, ["trans_x", "rot_y"])
    >>> report.generate()
"""

import base64
import json
import logging
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for report generation
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from connectomix.core.version import __version__
from connectomix.utils.visualization import plot_lightbox_axial_slices
from connectomix.utils.validation import sanitize_filename

logger = logging.getLogger(__name__)


# ============================================================================
# CSS Styles - Professional, modern, shareable design
# ============================================================================

REPORT_CSS = """
<style>
:root {
    --primary-color: #2563eb;
    --primary-dark: #1d4ed8;
    --secondary-color: #7c3aed;
    --success-color: #10b981;
    --warning-color: #f59e0b;
    --danger-color: #ef4444;
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-300: #d1d5db;
    --gray-600: #4b5563;
    --gray-700: #374151;
    --gray-800: #1f2937;
    --gray-900: #111827;
}

* {
    box-sizing: border-box;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    color: var(--gray-800);
    background-color: var(--gray-50);
    margin: 0;
    padding: 0;
}

.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 20px;
}

/* Navigation */
.nav-bar {
    position: sticky;
    top: 0;
    background: white;
    border-bottom: 1px solid var(--gray-200);
    padding: 15px 20px;
    z-index: 100;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.nav-content {
    max-width: 1400px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
}

.nav-brand {
    font-weight: 700;
    font-size: 1.25em;
    color: var(--primary-color);
}

.nav-links {
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
}

.nav-links a {
    color: var(--gray-600);
    text-decoration: none;
    font-size: 0.9em;
    transition: color 0.2s;
}

.nav-links a:hover {
    color: var(--primary-color);
}

/* Header */
.header {
    background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
    color: white;
    padding: 40px;
    margin-bottom: 30px;
    border-radius: 12px;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
}

.header h1 {
    margin: 0 0 10px 0;
    font-size: 2.5em;
    font-weight: 700;
}

.header .subtitle {
    font-size: 1.2em;
    opacity: 0.9;
}

.header .meta-info {
    margin-top: 20px;
    display: flex;
    gap: 30px;
    flex-wrap: wrap;
    font-size: 0.95em;
}

.header .meta-item {
    display: flex;
    align-items: center;
    gap: 8px;
}

/* Table of Contents */
.toc {
    background: white;
    padding: 25px;
    border-radius: 12px;
    margin-bottom: 30px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.toc h2 {
    margin-top: 0;
    color: var(--gray-800);
    border-bottom: 2px solid var(--primary-color);
    padding-bottom: 10px;
}

.toc-list {
    list-style: none;
    padding: 0;
    margin: 0;
    columns: 2;
    column-gap: 40px;
}

.toc-list li {
    margin-bottom: 8px;
    break-inside: avoid;
}

.toc-list a {
    color: var(--gray-700);
    text-decoration: none;
    display: flex;
    align-items: center;
    gap: 8px;
}

.toc-list a:hover {
    color: var(--primary-color);
}

.toc-number {
    background: var(--gray-100);
    color: var(--gray-600);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.85em;
    font-weight: 600;
}

/* Sections */
.section {
    background: white;
    padding: 30px;
    border-radius: 12px;
    margin-bottom: 25px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.section h2 {
    color: var(--gray-800);
    border-bottom: 2px solid var(--primary-color);
    padding-bottom: 12px;
    margin-top: 0;
    margin-bottom: 25px;
    font-size: 1.5em;
}

.section h3 {
    color: var(--gray-700);
    margin-top: 25px;
    margin-bottom: 15px;
    font-size: 1.2em;
}

/* Metrics Grid */
.metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 20px;
    margin: 20px 0;
}

.metric-card {
    background: var(--gray-50);
    padding: 20px;
    border-radius: 10px;
    text-align: center;
    border-left: 4px solid var(--primary-color);
    transition: transform 0.2s, box-shadow 0.2s;
}

.metric-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.metric-value {
    font-size: 2em;
    font-weight: 700;
    color: var(--primary-color);
}

.metric-label {
    color: var(--gray-600);
    font-size: 0.9em;
    margin-top: 5px;
}

/* Info Box */
.info-box {
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
    border: 1px solid #bae6fd;
    border-left: 4px solid var(--primary-color);
    border-radius: 8px;
    padding: 20px;
    margin: 20px 0;
}

.info-box h4 {
    margin-top: 0;
    color: var(--primary-dark);
}

.info-box p {
    margin-bottom: 0.5em;
}

.info-box code {
    background: white;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.9em;
}

/* Parameter Tables */
.param-table {
    width: 100%;
    border-collapse: collapse;
    margin: 15px 0;
    font-size: 0.95em;
}

.param-table th,
.param-table td {
    padding: 12px 15px;
    text-align: left;
    border-bottom: 1px solid var(--gray-200);
}

.param-table th {
    background: var(--gray-100);
    font-weight: 600;
    color: var(--gray-700);
}

.param-table tr:hover {
    background: var(--gray-50);
}

.param-table code {
    background: var(--gray-100);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'Monaco', 'Menlo', monospace;
    font-size: 0.9em;
}

/* Figures */
.figure-container {
    margin: 25px 0;
    text-align: center;
}

.figure-wrapper {
    display: inline-block;
    background: white;
    padding: 15px;
    border-radius: 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    position: relative;
}

.figure-wrapper img {
    max-width: 100%;
    height: auto;
    border-radius: 6px;
}

.figure-caption {
    color: var(--gray-600);
    font-style: italic;
    margin-top: 12px;
    font-size: 0.95em;
}

.download-btn {
    position: absolute;
    top: 10px;
    right: 10px;
    background: var(--primary-color);
    color: white;
    border: none;
    padding: 8px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.85em;
    opacity: 0.9;
    transition: opacity 0.2s;
}

.download-btn:hover {
    opacity: 1;
}

/* Code Blocks */
.code-block {
    background: var(--gray-900);
    color: #e5e7eb;
    padding: 20px;
    border-radius: 8px;
    overflow-x: auto;
    font-family: 'Monaco', 'Menlo', monospace;
    font-size: 0.9em;
    line-height: 1.5;
    margin: 15px 0;
}

.code-block .comment {
    color: #6b7280;
}

.code-block .string {
    color: #10b981;
}

.code-block .keyword {
    color: #8b5cf6;
}

/* Alert Boxes */
.alert {
    padding: 15px 20px;
    border-radius: 8px;
    margin: 15px 0;
    display: flex;
    align-items: flex-start;
    gap: 12px;
}

.alert-icon {
    font-size: 1.2em;
    flex-shrink: 0;
}

.alert-success {
    background: #d1fae5;
    border: 1px solid var(--success-color);
    color: #065f46;
}

.alert-warning {
    background: #fef3c7;
    border: 1px solid var(--warning-color);
    color: #92400e;
}

.alert-info {
    background: #dbeafe;
    border: 1px solid var(--primary-color);
    color: #1e40af;
}

/* References */
.references {
    font-size: 0.95em;
}

.reference-item {
    margin-bottom: 15px;
    padding-left: 25px;
    position: relative;
}

.reference-item::before {
    content: "•";
    position: absolute;
    left: 8px;
    color: var(--primary-color);
}

.reference-item a {
    color: var(--primary-color);
    text-decoration: none;
}

.reference-item a:hover {
    text-decoration: underline;
}

/* Footer */
.footer {
    text-align: center;
    padding: 30px 20px;
    color: var(--gray-600);
    font-size: 0.9em;
    border-top: 1px solid var(--gray-200);
    margin-top: 40px;
}

.footer a {
    color: var(--primary-color);
    text-decoration: none;
}

/* Tabs for multiple views */
.tabs {
    display: flex;
    border-bottom: 2px solid var(--gray-200);
    margin-bottom: 20px;
}

.tab {
    padding: 12px 20px;
    cursor: pointer;
    border: none;
    background: none;
    font-size: 1em;
    color: var(--gray-600);
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: all 0.2s;
}

.tab:hover {
    color: var(--primary-color);
}

.tab.active {
    color: var(--primary-color);
    border-bottom-color: var(--primary-color);
    font-weight: 600;
}

.tab-content {
    display: none;
}

.tab-content.active {
    display: block;
}

/* Collapsible sections */
.collapsible {
    cursor: pointer;
    padding: 15px;
    width: 100%;
    border: none;
    text-align: left;
    outline: none;
    font-size: 1.1em;
    background: var(--gray-100);
    border-radius: 8px;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.collapsible:hover {
    background: var(--gray-200);
}

.collapsible::after {
    content: '▼';
    font-size: 0.8em;
    transition: transform 0.2s;
}

.collapsible.active::after {
    transform: rotate(180deg);
}

.collapsible-content {
    padding: 0 15px;
    max-height: 0;
    overflow: hidden;
    transition: max-height 0.3s ease-out;
}

/* Responsive Design */
@media (max-width: 768px) {
    .container {
        padding: 10px;
    }
    
    .header {
        padding: 25px;
    }
    
    .header h1 {
        font-size: 1.8em;
    }
    
    .nav-links {
        display: none;
    }
    
    .toc-list {
        columns: 1;
    }
    
    .metrics-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}

/* Print styles */
@media print {
    .nav-bar, .download-btn {
        display: none;
    }
    
    .section {
        break-inside: avoid;
    }
    
    body {
        background: white;
    }
}
</style>
"""


# ============================================================================
# JavaScript for interactivity
# ============================================================================

REPORT_JS = """
<script>
// Download figure functionality
function downloadFigure(imgId, filename) {
    const img = document.getElementById(imgId);
    const link = document.createElement('a');
    link.href = img.src;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Collapsible sections
document.addEventListener('DOMContentLoaded', function() {
    const collapsibles = document.querySelectorAll('.collapsible');
    collapsibles.forEach(function(coll) {
        coll.addEventListener('click', function() {
            this.classList.toggle('active');
            const content = this.nextElementSibling;
            if (content.style.maxHeight) {
                content.style.maxHeight = null;
            } else {
                content.style.maxHeight = content.scrollHeight + 'px';
            }
        });
    });
    
    // Tab functionality
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(function(tab) {
        tab.addEventListener('click', function() {
            const tabGroup = this.parentElement;
            const contentGroup = tabGroup.nextElementSibling;
            
            // Remove active class from all tabs and contents
            tabGroup.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            contentGroup.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            // Add active class to clicked tab and corresponding content
            this.classList.add('active');
            const targetId = this.getAttribute('data-tab');
            document.getElementById(targetId).classList.add('active');
        });
    });
    
    // Smooth scroll for navigation
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });
});
</script>
"""


# ============================================================================
# Scientific References
# ============================================================================

REFERENCES = {
    "fmriprep": {
        "title": "fMRIPrep: a robust preprocessing pipeline for functional MRI",
        "authors": "Esteban O, et al.",
        "journal": "Nature Methods",
        "year": "2019",
        "doi": "10.1038/s41592-018-0235-4",
        "url": "https://doi.org/10.1038/s41592-018-0235-4"
    },
    "nilearn": {
        "title": "Machine learning for neuroimaging with scikit-learn",
        "authors": "Abraham A, et al.",
        "journal": "Frontiers in Neuroinformatics",
        "year": "2014",
        "doi": "10.3389/fninf.2014.00014",
        "url": "https://doi.org/10.3389/fninf.2014.00014"
    },
    "schaefer": {
        "title": "Local-Global Parcellation of the Human Cerebral Cortex from Intrinsic Functional Connectivity MRI",
        "authors": "Schaefer A, et al.",
        "journal": "Cerebral Cortex",
        "year": "2018",
        "doi": "10.1093/cercor/bhx179",
        "url": "https://doi.org/10.1093/cercor/bhx179"
    },
    "aal": {
        "title": "Automated Anatomical Labeling of Activations in SPM Using a Macroscopic Anatomical Parcellation of the MNI MRI Single-Subject Brain",
        "authors": "Tzourio-Mazoyer N, et al.",
        "journal": "NeuroImage",
        "year": "2002",
        "doi": "10.1006/nimg.2001.0978",
        "url": "https://doi.org/10.1006/nimg.2001.0978"
    },
    "connectivity": {
        "title": "Functional connectivity in the motor cortex of resting human brain using echo-planar MRI",
        "authors": "Biswal B, et al.",
        "journal": "Magnetic Resonance in Medicine",
        "year": "1995",
        "doi": "10.1002/mrm.1910340409",
        "url": "https://doi.org/10.1002/mrm.1910340409"
    },
    "denoising": {
        "title": "A Component Based Noise Correction Method (CompCor) for BOLD and Perfusion Based fMRI",
        "authors": "Behzadi Y, et al.",
        "journal": "NeuroImage",
        "year": "2007",
        "doi": "10.1016/j.neuroimage.2007.04.042",
        "url": "https://doi.org/10.1016/j.neuroimage.2007.04.042"
    }
}


# ============================================================================
# Report Generator Class
# ============================================================================

class ParticipantReportGenerator:
    """Generate comprehensive HTML reports for participant-level analyses.
    
    This class builds professional, navigable HTML reports with:
    - Analysis parameters and configuration
    - Connectivity matrix visualizations
    - Denoising quality assessment
    - Scientific references
    - Downloadable figures
    
    Attributes:
        subject_id: BIDS subject ID (can include full label like 'sub-01_ses-1_task-rest')
        config: ParticipantConfig instance
        output_dir: Directory for saving reports and figures
    """
    
    def __init__(
        self,
        subject_id: str,
        config: Any,  # ParticipantConfig
        output_dir: Path,
        confounds_df: Optional[pd.DataFrame] = None,
        selected_confounds: Optional[List[str]] = None,
        connectivity_matrix: Optional[np.ndarray] = None,
        roi_names: Optional[List[str]] = None,
        connectivity_paths: Optional[List[Path]] = None,
        logger: Optional[logging.Logger] = None,
        session: Optional[str] = None,
        task: Optional[str] = None,
        run: Optional[str] = None,
        space: Optional[str] = None,
        desc: Optional[str] = None,
        label: Optional[str] = None,
        censoring_summary: Optional[Dict[str, Any]] = None,
        condition: Optional[str] = None,
        censoring: Optional[str] = None,
        resampling_info: Optional[Dict[str, Any]] = None,
        denoising_strategy: Optional[str] = None,
    ):
        """Initialize report generator.
        
        Args:
            subject_id: Subject ID or full BIDS label
            config: ParticipantConfig with analysis parameters
            output_dir: Output directory for reports
            confounds_df: Confounds DataFrame from preprocessing (fmridenoiser or fMRIPrep)
            selected_confounds: List of confound columns used
            connectivity_matrix: Connectivity matrix (for ROI methods)
            roi_names: ROI labels for matrix methods
            connectivity_paths: List of output paths from connectivity
            logger: Logger instance
            session: Session ID (without 'ses-' prefix)
            task: Task name
            run: Run number
            space: Space name
            desc: Description entity for filename (e.g., atlas name, method)
            label: Custom label entity for filename
            censoring_summary: Summary of temporal censoring applied
            condition: Condition name for filename (when --conditions is used)
            censoring: Censoring method entity for filename (e.g., 'fd05')
            resampling_info: Information about resampling performed (reference, original geometry, etc.)
            denoising_strategy: Denoising strategy used (e.g., 'scrubbing5', 'simpleGSR')
        """
        self.subject_id = subject_id
        self.session = session
        self.config = config
        self.output_dir = Path(output_dir)
        self.task = task
        self.run = run
        self.space = space
        self.desc = desc
        self.label = label
        self.condition = condition
        self.censoring = censoring
        self.connectivity_paths = connectivity_paths or []
        self._logger = logger or logging.getLogger(__name__)
        
        # Figures directory for saving plots
        self.figures_dir: Optional[Path] = None
        # Connectivity data directory for saving matrices
        self.connectivity_data_dir: Optional[Path] = None
        
        # Storage for report content
        self.sections: List[str] = []
        self.figures: Dict[str, Tuple[plt.Figure, str]] = {}  # id -> (figure, caption)
        self.toc_items: List[Tuple[str, str]] = []  # (id, title)
        self._figure_counter = 0
        
        # QA metrics
        self.qa_metrics: Dict[str, Any] = {}
        
        # Denoising info
        self.confounds_used: List[str] = selected_confounds or []
        self.confounds_df: Optional[pd.DataFrame] = confounds_df
        self.denoising_histogram_data: Optional[Dict[str, Any]] = None
        
        # Denoising strategy - use parameter if provided, otherwise try config
        self.denoising_strategy = denoising_strategy or getattr(config, 'denoising_strategy', None)
        
        # Connectivity results
        self.connectivity_matrices: List[Tuple[np.ndarray, List[str], str]] = []
        
        # Brain maps (for seedToVoxel and roiToVoxel analyses)
        self.brain_maps: List[Tuple[Path, str, Optional[np.ndarray]]] = []  # (path, label, seed_coords)
        
        # Add connectivity matrix if provided
        if connectivity_matrix is not None and roi_names is not None:
            # Only use atlas name if method uses an atlas; otherwise use method name
            method = getattr(config, 'method', None)
            if method in ('seedToVoxel', 'seedToSeed'):
                atlas_name = method
            else:
                atlas_name = config.atlas if hasattr(config, 'atlas') and config.atlas else "connectivity"
            self.add_connectivity_matrix(connectivity_matrix, roi_names, atlas_name)
        
        # Command/config info
        self.command_line: Optional[str] = None
        self.config_dict: Optional[Dict] = None
        
        # Temporal censoring summary
        self.censoring_summary: Optional[Dict[str, Any]] = censoring_summary
        
        # Resampling info
        self.resampling_info: Optional[Dict[str, Any]] = resampling_info
        
        self._logger.debug(f"Initialized report generator for {subject_id}")
    
    def _get_unique_figure_id(self) -> str:
        """Get unique figure ID."""
        self._figure_counter += 1
        return f"fig_{self._figure_counter}"
    
    def _method_uses_atlas(self) -> bool:
        """Check if the current analysis method uses an atlas.
        
        Returns:
            True if the method uses an atlas, False otherwise
        """
        method = getattr(self.config, 'method', None)
        # Methods that do NOT use an atlas
        non_atlas_methods = ['seedToVoxel', 'seedToSeed']
        return method not in non_atlas_methods
    
    def _figure_to_base64(self, fig: plt.Figure, dpi: int = 150) -> str:
        """Convert matplotlib figure to base64 PNG."""
        buffer = BytesIO()
        fig.savefig(buffer, format='png', dpi=dpi, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        buffer.seek(0)
        img_data = base64.b64encode(buffer.read()).decode('utf-8')
        buffer.close()
        return img_data
    
    def _build_bids_figure_filename(self, figure_type: str, desc: str) -> str:
        """Build BIDS-compliant figure filename with all entities.
        
        Pattern: sub-<label>[_ses-<session>][_task-<task>][_space-<space>][_denoise-<method>]
                 [_condition-<condition>][_method-<method>][_atlas-<atlas>][_desc-<desc>][_<figure_type>].<ext>
        
        Args:
            figure_type: Type of figure (e.g., 'connectivity', 'histogram')
            desc: Description (e.g., 'correlation', 'covariance')
            
        Returns:
            BIDS-compliant filename like: sub-01_task-rest_condition-face_atlas-schaefer2018n100_desc-correlation_connectivity.png
        """
        # Extract subject ID from subject_id (which may be 'sub-01' or 'sub-01_ses-1_task-rest', etc.)
        if self.subject_id.startswith('sub-'):
            # Parse BIDS entities from subject_id
            parts = self.subject_id.split('_')
            sub_part = parts[0]  # sub-XX
        else:
            sub_part = f"sub-{self.subject_id}"
        
        # Build entity components in BIDS order
        filename_parts = [sub_part]
        
        if self.session:
            filename_parts.append(f"ses-{self.session}")
        
        if self.task:
            filename_parts.append(f"task-{self.task}")
        
        if self.space:
            filename_parts.append(f"space-{self.space}")
        
        # Add denoising strategy
        if self.denoising_strategy and self.denoising_strategy != "none":
            filename_parts.append(f"denoise-{self.denoising_strategy}")
        
        # Add condition (if present)
        if self.condition:
            filename_parts.append(f"condition-{self.condition}")
        
        # Add method (analysis type)
        if hasattr(self.config, 'method') and self.config.method:
            filename_parts.append(f"method-{self.config.method}")
        
        # Add atlas (only if method uses an atlas)
        if self._method_uses_atlas() and hasattr(self.config, 'atlas') and self.config.atlas:
            filename_parts.append(f"atlas-{self.config.atlas}")
        
        # Add description
        if desc:
            filename_parts.append(f"desc-{desc}")
        
        # Add figure type as suffix
        base_filename = "_".join(filename_parts)
        return f"{base_filename}_{figure_type}.png"
    
    def _save_figure_to_disk(self, fig: plt.Figure, figure_type: str, desc: str, dpi: int = 150) -> Optional[Path]:
        """Save figure to the figures directory with BIDS-compliant filename.
        
        Args:
            fig: Matplotlib figure to save
            figure_type: Type of figure (e.g., 'connectivity', 'histogram')
            desc: Description entity (e.g., 'correlation', 'covariance')
            dpi: Resolution for saving
            
        Returns:
            Path to saved figure, or None if figures_dir not set
        """
        if self.figures_dir is None:
            return None
        
        try:
            self.figures_dir.mkdir(parents=True, exist_ok=True)
            # Build BIDS-compliant filename
            filename = self._build_bids_figure_filename(figure_type, desc)
            fig_path = self.figures_dir / filename
            fig.savefig(fig_path, format='png', dpi=dpi, bbox_inches='tight',
                        facecolor='white', edgecolor='none')
            self._logger.debug(f"  Saved figure: {fig_path}")
            return fig_path
        except Exception as e:
            self._logger.warning(f"Could not save figure to disk: {e}")
            return None
    
    def _save_matrix_to_disk(
        self, 
        matrix: np.ndarray, 
        filename: str,
        labels: Optional[List[str]] = None,
        description: str = "Correlation matrix"
    ) -> Optional[Path]:
        """Save numpy matrix to the connectivity_data directory with JSON sidecar.
        
        Args:
            matrix: Numpy array to save
            filename: Filename for the saved data (without path, should end in .npy)
            labels: Optional list of labels for rows/columns
            description: Description for the JSON sidecar
            
        Returns:
            Path to saved file, or None if connectivity_data_dir not set
        """
        if self.connectivity_data_dir is None:
            return None
        
        try:
            self.connectivity_data_dir.mkdir(parents=True, exist_ok=True)
            
            # Save numpy array
            data_path = self.connectivity_data_dir / filename
            np.save(data_path, matrix)
            self._logger.debug(f"  Saved matrix: {data_path}")
            
            # Save JSON sidecar with metadata
            json_path = data_path.with_suffix('.json')
            sidecar = {
                "Description": description,
                "Shape": list(matrix.shape),
            }
            if labels:
                sidecar["Labels"] = labels
            
            with open(json_path, 'w') as f:
                json.dump(sidecar, f, indent=2)
            
            return data_path
        except Exception as e:
            self._logger.warning(f"Could not save matrix to disk: {e}")
            return None
    
    def _build_bids_base_filename(self) -> str:
        """Build BIDS-compliant base filename from available entities.
        
        Returns:
            Base filename with BIDS entities (e.g., 'sub-01_ses-1_task-rest')
        """
        if self.subject_id.startswith('sub-'):
            # subject_id already contains BIDS formatting
            parts = [self.subject_id]
        else:
            # Build from individual components
            parts = [f"sub-{self.subject_id}"]
            if self.session:
                parts.append(f"ses-{self.session}")
            if self.task:
                parts.append(f"task-{self.task}")
            if self.run:
                parts.append(f"run-{self.run}")
        
        # Add optional entities
        if self.space:
            parts.append(f"space-{self.space}")
        if self.censoring:
            parts.append(f"censoring-{self.censoring}")
        if self.condition:
            parts.append(f"condition-{self.condition}")
        
        return "_".join(parts)
    
    def set_command_line(self, command: str) -> None:
        """Store command line used to run analysis."""
        self.command_line = command
    
    def set_config_dict(self, config_dict: Dict) -> None:
        """Store configuration dictionary."""
        self.config_dict = config_dict
    
    def add_qa_metrics(self, metrics: Dict[str, Any]) -> None:
        """Add quality assurance metrics."""
        self.qa_metrics.update(metrics)
    
    def add_connectivity_matrix(
        self,
        matrix: np.ndarray,
        labels: List[str],
        name: str,
    ) -> None:
        """Add connectivity matrix for visualization.
        
        Args:
            matrix: Connectivity matrix (N x N)
            labels: ROI labels
            name: Atlas/analysis name
        """
        self.connectivity_matrices.append((matrix, labels, name))
    
    def add_denoising_info(
        self,
        confounds_df: pd.DataFrame,
        confounds_used: List[str],
    ) -> None:
        """Add denoising information.
        
        Args:
            confounds_df: Full confounds DataFrame from preprocessing (fmridenoiser or fMRIPrep)
            confounds_used: List of confound columns used in denoising
        """
        self.confounds_df = confounds_df
        self.confounds_used = confounds_used
    
    def add_denoising_histogram_data(
        self,
        histogram_data: Dict[str, Any]
    ) -> None:
        """Add denoising histogram data for before/after comparison.
        
        Args:
            histogram_data: Dictionary from compute_denoising_histogram_data containing:
                - 'original_data': Flattened original voxel values
                - 'denoised_data': Flattened denoised voxel values
                - 'original_stats': Dict with mean, std, min, max
                - 'denoised_stats': Dict with mean, std, min, max
        """
        self.denoising_histogram_data = histogram_data
    
    def add_brain_map(
        self,
        brain_map_path: Union[str, Path],
        label: str,
        seed_coords: Optional[np.ndarray] = None,
        seed_radius: Optional[float] = None
    ) -> None:
        """Add a brain map for visualization (seedToVoxel or roiToVoxel output).
        
        Args:
            brain_map_path: Path to NIfTI brain map file (.nii or .nii.gz)
            label: Label for the brain map (e.g., seed name, ROI name)
            seed_coords: Optional seed coordinates [x, y, z] in mm for centered views
            seed_radius: Optional seed sphere radius in mm for visualization overlay
        """
        self.brain_maps.append((Path(brain_map_path), label, seed_coords, seed_radius))
    
    def _build_header(self) -> str:
        """Build report header section."""
        # subject_id may already include full BIDS label like 'sub-01_ses-1_task-rest'
        # or just the ID like '01'
        if self.subject_id.startswith('sub-'):
            # Already formatted, use as-is
            display_label = self.subject_id.replace('_', ' | ')
        else:
            # Build from parts
            session_str = f"ses-{self.session}" if self.session else ""
            task_str = f"task-{self.task}" if self.task else ""
            
            title_parts = [f"sub-{self.subject_id}"]
            if session_str:
                title_parts.append(session_str)
            if task_str:
                title_parts.append(task_str)
            display_label = ' | '.join(title_parts)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        html = f'''
        <div class="header">
            <h1>🧠 Connectomix Participant Report</h1>
            <div class="subtitle">{display_label}</div>
            <div class="meta-info">
                <div class="meta-item">📅 {timestamp}</div>
                <div class="meta-item">🔬 Method: {self.config.method}</div>
                <div class="meta-item">📊 Connectomix v{__version__}</div>
            </div>
        </div>
        '''
        return html
    
    def _build_toc(self) -> str:
        """Build table of contents."""
        if not self.toc_items:
            return ""
        
        items_html = ""
        for i, (section_id, title) in enumerate(self.toc_items, 1):
            items_html += f'''
                <li>
                    <a href="#{section_id}">
                        <span class="toc-number">{i}</span>
                        {title}
                    </a>
                </li>
            '''
        
        return f'''
        <div class="toc">
            <h2>📋 Table of Contents</h2>
            <ul class="toc-list">
                {items_html}
            </ul>
        </div>
        '''
    
    def _build_overview_section(self) -> str:
        """Build analysis overview section."""
        self.toc_items.append(("overview", "Analysis Overview"))
        
        method_descriptions = {
            "roiToRoi": "ROI-to-ROI correlation analysis using atlas parcellation",
            "seedToVoxel": "Seed-based correlation mapping",
            "roiToVoxel": "ROI-based whole-brain correlation",
            "seedToSeed": "Seed-to-seed correlation matrix"
        }
        
        method_desc = method_descriptions.get(self.config.method, self.config.method)
        
        # Determine atlas display value for overview
        # Only display atlas if the method uses an atlas
        if self._method_uses_atlas():
            atlas_overview = getattr(self.config, 'atlas', 'N/A')
            if atlas_overview and atlas_overview != 'N/A':
                standard_atlases = ['schaefer2018n100', 'schaefer2018n200', 'aal', 'harvardoxford', 'canica']
                if atlas_overview.lower() not in [a.lower() for a in standard_atlases]:
                    atlas_overview = f"{atlas_overview} (custom)"
        else:
            atlas_overview = 'N/A'
        
        html = f'''
        <div class="section" id="overview">
            <h2>📊 Analysis Overview</h2>
            
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-value">{self.config.method}</div>
                    <div class="metric-label">Analysis Method</div>
                </div>
                {f'<div class="metric-card"><div class="metric-value">{atlas_overview}</div><div class="metric-label">Atlas</div></div>' if self._method_uses_atlas() else ''}
            </div>
            
            <h3>Method Description</h3>
            <p>{method_desc}</p>
            
            <div class="alert alert-info">
                <span class="alert-icon">ℹ️</span>
                <div>This analysis computes functional connectivity from denoised 
                fMRI data produced by fmridenoiser.</div>
            </div>
        </div>
        '''
        return html
    
    def _build_parameters_section(self) -> str:
        """Build analysis parameters section."""
        self.toc_items.append(("parameters", "Analysis Parameters"))
        
        # Preprocessing parameters (from upstream denoising by fmridenoiser)
        preproc_params = [
            ("Preprocessed by", "fmridenoiser"),
            ("Analysis type", "consumes denoised data"),
        ]
        
        preproc_rows = ""
        for name, value in preproc_params:
            preproc_rows += f"<tr><td>{name}</td><td><code>{value}</code></td></tr>"
        
        # Method-specific parameters
        method_params = []
        if self.config.method in ["roiToRoi", "roiToVoxel"]:
            atlas_value = getattr(self.config, 'atlas', 'N/A')
            # Determine if this is a standard atlas or custom
            standard_atlases = ['schaefer2018n100', 'schaefer2018n200', 'aal', 'harvardoxford', 'canica']
            if atlas_value and atlas_value.lower() not in [a.lower() for a in standard_atlases]:
                # Custom atlas - check if it looks like a path
                from pathlib import Path
                if Path(atlas_value).exists():
                    atlas_display = f"{atlas_value} (custom path)"
                else:
                    atlas_display = f"{atlas_value} (custom, from Nilearn data dir)"
            else:
                atlas_display = atlas_value
            method_params.append(("Atlas", atlas_display))
        if self.config.method in ["seedToVoxel", "seedToSeed"]:
            method_params.append(("Seeds file", str(getattr(self.config, 'seeds_file', 'N/A'))))
            method_params.append(("Sphere radius", f"{getattr(self.config, 'radius', 5.0)} mm"))
        
        method_rows = ""
        for name, value in method_params:
            method_rows += f"<tr><td>{name}</td><td><code>{value}</code></td></tr>"
        
        html = f'''
        <div class="section" id="parameters">
            <h2>⚙️ Analysis Parameters</h2>
            
            <h3>Preprocessing Parameters</h3>
            <table class="param-table">
                <tr><th>Parameter</th><th>Value</th></tr>
                {preproc_rows}
            </table>
            
            <h3>Method-Specific Parameters</h3>
            <table class="param-table">
                <tr><th>Parameter</th><th>Value</th></tr>
                {method_rows}
            </table>
        </div>
        '''
        return html
    
    def _build_resampling_section(self) -> str:
        """Build resampling information section."""
        # Only show if resampling was performed
        if not self.resampling_info or not self.resampling_info.get('resampled', False):
            return ""
        
        self.toc_items.append(("resampling", "Resampling"))
        
        info = self.resampling_info
        
        # Format geometry information
        def format_shape(shape):
            if shape:
                return f"{shape[0]} × {shape[1]} × {shape[2]}"
            return "N/A"
        
        def format_voxel_size(voxels):
            if voxels:
                return f"{voxels[0]:.2f} × {voxels[1]:.2f} × {voxels[2]:.2f} mm"
            return "N/A"
        
        original_shape = format_shape(info.get('original_shape'))
        original_voxel = format_voxel_size(info.get('original_voxel_size'))
        reference_shape = format_shape(info.get('reference_shape'))
        reference_voxel = format_voxel_size(info.get('reference_voxel_size'))
        final_shape = format_shape(info.get('final_shape'))
        final_voxel = format_voxel_size(info.get('final_voxel_size'))
        
        reference_file = info.get('reference_file', 'N/A')
        if reference_file != 'N/A':
            # Show just the filename for readability
            from pathlib import Path
            reference_file = Path(reference_file).name
        
        html = f'''
        <div class="section" id="resampling">
            <h2>🔄 Resampling</h2>
            
            <div class="info-box warning">
                <strong>⚠️ Resampling Applied:</strong> This image was resampled to match a common 
                reference geometry for group-level compatibility.
            </div>
            
            <h3>Geometry Comparison</h3>
            <table class="param-table">
                <tr>
                    <th>Property</th>
                    <th>Original</th>
                    <th>Reference</th>
                    <th>After Resampling</th>
                </tr>
                <tr>
                    <td><strong>Shape (voxels)</strong></td>
                    <td>{original_shape}</td>
                    <td>{reference_shape}</td>
                    <td>{final_shape}</td>
                </tr>
                <tr>
                    <td><strong>Voxel Size</strong></td>
                    <td>{original_voxel}</td>
                    <td>{reference_voxel}</td>
                    <td>{final_voxel}</td>
                </tr>
            </table>
            
            <h3>Reference Image</h3>
            <p><code>{reference_file}</code></p>
            
            <p class="note">
                <em>Note:</em> Resampling uses linear interpolation via nilearn's 
                <code>resample_to_img</code>. The full reference affine matrix is saved 
                in the JSON sidecar of the resampled file.
            </p>
        </div>
        '''
        return html
    
    def _build_confounds_section(self) -> str:
        """Build preprocessing note section (denoising done upstream)."""
        self.toc_items.append(("preprocessing", "Preprocessing"))
        
        html = f'''
        <div class="section" id="preprocessing">
            <h2>🔧 Preprocessing</h2>
            
            <div class="alert alert-info">
                <span class="alert-icon">ℹ️</span>
                <div>
                    <strong>Note:</strong> This analysis uses denoised fMRI data preprocessed
                    by <strong>fmridenoiser</strong>. Confound regression, temporal filtering,
                    and motion censoring were applied during the upstream denoising step.
                </div>
            </div>
            
            <h3>Preprocessing Pipeline</h3>
            <ol>
                <li>fMRI preprocessing by fMRIPrep</li>
                <li>Confound regression and denoising by fmridenoiser</li>
                <li>Connectivity analysis by Connectomix</li>
            </ol>
            
            <p>For detailed information about confounds and preprocessing parameters used,
            please refer to the fmridenoiser output in the derivatives directory.</p>
        </div>
        '''
        
        return html
    
    def _create_confounds_plot(self) -> Optional[plt.Figure]:
        """Create confounds time series plot."""
        try:
            # Select confounds that exist in the dataframe
            available = [c for c in self.confounds_used if c in self.confounds_df.columns]
            if not available:
                return None
            
            # Limit to first 12 confounds for readability
            available = available[:12]
            
            fig, axes = plt.subplots(len(available), 1, figsize=(12, 2 * len(available)), 
                                      sharex=True)
            if len(available) == 1:
                axes = [axes]
            
            for i, confound in enumerate(available):
                data = self.confounds_df[confound].values
                # Z-score for visualization
                data = (data - np.nanmean(data)) / (np.nanstd(data) + 1e-10)
                
                axes[i].plot(data, color='#2563eb', linewidth=0.8)
                axes[i].axhline(0, color='gray', linestyle='--', alpha=0.5)
                axes[i].set_ylabel(confound, fontsize=9)
                axes[i].set_xlim(0, len(data))
                axes[i].tick_params(labelsize=8)
                
                # Remove top/right spines
                axes[i].spines['top'].set_visible(False)
                axes[i].spines['right'].set_visible(False)
            
            axes[-1].set_xlabel('Volume', fontsize=10)
            fig.suptitle('Confound Regressors (z-scored)', fontsize=12, fontweight='bold')
            plt.tight_layout()
            
            return fig
        except Exception as e:
            logger.warning(f"Could not create confounds plot: {e}")
            return None
    
    def _create_confounds_correlation_plot(self) -> Tuple[Optional[plt.Figure], Optional[pd.DataFrame]]:
        """Create correlation matrix plot between confounds.
        
        Returns:
            Tuple of (figure, correlation_dataframe)
        """
        try:
            # Select confounds that exist in the dataframe
            available = [c for c in self.confounds_used if c in self.confounds_df.columns]
            if len(available) < 2:
                return None, None
            
            # Limit to first 20 confounds for readability
            available = available[:20]
            
            # Extract data and compute correlation matrix
            confounds_data = self.confounds_df[available].dropna()
            if len(confounds_data) < 10:  # Need enough data points
                return None, None
            
            corr_df = confounds_data.corr()
            corr_matrix = corr_df.values
            
            # Determine figure size based on number of confounds
            n_conf = len(available)
            base_size = max(6, min(12, n_conf * 0.5))
            fig, ax = plt.subplots(figsize=(base_size, base_size))
            
            # Plot heatmap
            vmax = 1.0
            vmin = -1.0
            im = ax.imshow(corr_matrix, cmap='RdBu_r', vmin=vmin, vmax=vmax, aspect='equal')
            
            # Add colorbar
            cbar = plt.colorbar(im, ax=ax, shrink=0.8, label='Correlation')
            cbar.ax.tick_params(labelsize=9)
            
            # Add labels
            ax.set_xticks(range(n_conf))
            ax.set_yticks(range(n_conf))
            
            # Shorten labels if too long
            short_labels = [l[:15] + '...' if len(l) > 15 else l for l in available]
            ax.set_xticklabels(short_labels, rotation=90, fontsize=8)
            ax.set_yticklabels(short_labels, fontsize=8)
            
            ax.set_title('Confound Inter-Correlation Matrix', fontsize=12, fontweight='bold', pad=10)
            
            plt.tight_layout()
            return fig, corr_df
            
        except Exception as e:
            logger.warning(f"Could not create confounds correlation plot: {e}")
            return None, None
    
    def _create_denoising_histogram_plot(self) -> Optional[plt.Figure]:
        """Create histogram comparing voxel values before and after denoising.
        
        Returns:
            Matplotlib figure with overlaid histograms, or None if data not available.
        """
        if self.denoising_histogram_data is None:
            return None
        
        try:
            original_data = self.denoising_histogram_data['original_data']
            denoised_data = self.denoising_histogram_data['denoised_data']
            original_stats = self.denoising_histogram_data['original_stats']
            denoised_stats = self.denoising_histogram_data['denoised_stats']
            
            # Create figure
            fig, ax = plt.subplots(figsize=(10, 5))
            
            # For visualization, clip to ±3 std to focus on the main distribution
            # Both distributions are z-scored so they have similar scales
            clip_min = -3.5
            clip_max = 3.5
            
            n_bins = 100
            bins = np.linspace(clip_min, clip_max, n_bins + 1)
            
            # Plot histograms with transparency, normalized to percentages
            # Use weights to convert counts to percentages
            weights_orig = np.ones(len(original_data)) / len(original_data) * 100
            weights_den = np.ones(len(denoised_data)) / len(denoised_data) * 100
            
            ax.hist(original_data, bins=bins, alpha=0.5, color='steelblue', 
                   weights=weights_orig, label='Before denoising (z-scored)', edgecolor='none')
            ax.hist(denoised_data, bins=bins, alpha=0.5, color='coral', 
                   weights=weights_den, label='After denoising', edgecolor='none')
            
            # Add zero reference line
            ax.axvline(0, color='gray', linestyle='-', linewidth=1, alpha=0.5)
            
            # Set x-axis limits explicitly
            ax.set_xlim(clip_min, clip_max)
            
            ax.set_xlabel('Z-scored Intensity', fontsize=11)
            ax.set_ylabel('Percentage of voxels (%)', fontsize=11)
            ax.set_title('Distribution of Voxel Values Before and After Denoising (z-scored)', 
                        fontsize=12, fontweight='bold')
            ax.legend(loc='upper right', fontsize=9)
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            logger.warning(f"Could not create denoising histogram plot: {e}")
            return None
    
    def _build_censoring_section(self) -> str:
        """Build temporal masking section."""
        if self.censoring_summary is None or not self.censoring_summary.get('enabled', False):
            return ""
        
        self.toc_items.append(("censoring", "Temporal Masking"))
        
        summary = self.censoring_summary
        n_original = summary.get('n_original', 0)
        n_retained = summary.get('n_retained', 0)
        n_censored = summary.get('n_censored', 0)
        fraction = summary.get('fraction_retained', 1.0)
        
        # Determine retention status color
        if fraction < 0.5:
            status_class = "badge-error"
            status_text = "Low Retention"
        elif fraction < 0.7:
            status_class = "badge-warning"
            status_text = "Moderate Retention"
        else:
            status_class = "badge-success"
            status_text = "Good Retention"
        
        # Check if this is condition-based masking
        conditions = summary.get('conditions', {})
        has_conditions = len(conditions) > 0
        
        # Description for condition-based masking
        description = '''Temporal masking selects specific task conditions for analysis. 
        Connectivity was computed separately for each condition using only the timepoints 
        belonging to that condition. Motion artifacts were removed during the denoising phase.'''
        
        html = f'''
        <div class="section" id="censoring">
            <h2>⏱️ Temporal Masking</h2>
            
            <p>{description}</p>
            
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-value">{n_original}</div>
                    <div class="metric-label">Original Volumes</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{n_retained}</div>
                    <div class="metric-label">Volumes in Conditions</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{n_censored}</div>
                    <div class="metric-label">Not in Conditions</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{fraction:.1%}</div>
                    <div class="metric-label"><span class="{status_class}">{status_text}</span></div>
                </div>
            </div>
        '''
        
        # Condition-specific breakdown
        if conditions:
            html += '''
            <h3>Condition-Specific Volumes</h3>
            <p>Connectivity was computed separately for each condition:</p>
            <table>
                <thead>
                    <tr>
                        <th>Condition</th>
                        <th>Volumes</th>
                        <th>Fraction of Total</th>
                    </tr>
                </thead>
                <tbody>
            '''
            
            for cond_name, cond_info in sorted(conditions.items()):
                cond_vols = cond_info.get('n_volumes', 0)
                cond_frac = cond_info.get('fraction', 0)
                
                html += f'''
                    <tr>
                        <td><strong>{cond_name}</strong></td>
                        <td>{cond_vols}</td>
                        <td>{cond_frac:.1%}</td>
                    </tr>
                '''
            
            html += '''
                </tbody>
            </table>
            '''
        
        # Create temporal masking figure
        masking_fig = self._create_temporal_masking_figure()
        if masking_fig is not None:
            fig_id = self._get_unique_figure_id()
            img_data = self._figure_to_base64(masking_fig)
            saved_masking_path = self._save_figure_to_disk(masking_fig, 'masking', 'temporal')
            actual_masking_filename = saved_masking_path.name if saved_masking_path else 'temporal_masking.png'
            plt.close(masking_fig)
            
            html += f'''
            <h3>Temporal Masking Visualization</h3>
            <div class="figure-container">
                <div class="figure-wrapper">
                    <img id="{fig_id}" src="data:image/png;base64,{img_data}">
                    <button class="download-btn" onclick="downloadFigure('{fig_id}', '{actual_masking_filename}')">
                        ⬇️ Download
                    </button>
                </div>
                <div class="figure-caption">
                    Figure: Temporal masking visualization showing retained (green) and masked (red) volumes.
                    Green bars (#10b981) represent the {n_retained} included volumes.
                    Red bars (#ef4444) represent the {n_censored} excluded volumes.
                </div>
            </div>
            '''
        
        html += "</div>"
        return html
    
    def _create_censoring_plot(self) -> Optional[plt.Figure]:
        """Create temporal censoring visualization for condition-based masking.
        
        Shows condition-specific masks only. Motion artifacts are handled during denoising.
        """
        if self.censoring_summary is None:
            return None
        
        try:
            conditions = self.censoring_summary.get('conditions', {})
            mask = np.array(self.censoring_summary.get('mask', []), dtype=bool)
            
            if len(mask) == 0:
                return None
            
            n_volumes = len(mask)
            
            # Show condition-specific masks
            if conditions:
                # Create multi-row figure: one row per condition
                n_rows = len(conditions)
                figsize = (14, 1.5 * n_rows) if n_rows > 1 else (14, 2)
                fig, axes = plt.subplots(n_rows, 1, figsize=figsize, sharex=True, squeeze=False)
                axes = axes.flatten()
                
                # Plot each condition
                for idx, (cond_name, cond_info) in enumerate(sorted(conditions.items())):
                    ax = axes[idx]
                    
                    # Get condition mask if available
                    cond_mask = cond_info.get('mask', np.zeros(n_volumes, dtype=bool))
                    if isinstance(cond_mask, list):
                        cond_mask = np.array(cond_mask, dtype=bool)
                    
                    # Create colors: green for in condition, gray for not
                    colors = np.zeros((1, n_volumes, 3))
                    colors[0, cond_mask, :] = [0.1, 0.7, 0.5]   # Green for in condition
                    colors[0, ~cond_mask, :] = [0.85, 0.85, 0.85]  # Gray for not in condition
                    
                    ax.imshow(colors, aspect='auto', extent=[0, n_volumes, 0, 1])
                    ax.set_yticks([])
                    ax.set_ylabel(f'{cond_name}', fontsize=10, rotation=0, ha='right', va='center', fontweight='bold')
                    
                    # Add stats
                    n_cond = int(np.sum(cond_mask))
                    frac_cond = n_cond / n_volumes if n_volumes > 0 else 0
                    ax.text(n_volumes * 0.98, 0.5, f'{n_cond}/{n_volumes} ({frac_cond:.1%})',
                           ha='right', va='center', fontsize=9,
                           bbox=dict(boxstyle='round', facecolor='white', alpha=0.85))
                
                # Set labels
                axes[-1].set_xlabel('Volume', fontsize=11, fontweight='bold')
                axes[0].set_title('Temporal Masking by Condition', fontsize=13, fontweight='bold')
                
                # Add legend
                from matplotlib.patches import Patch
                legend_elements = [
                    Patch(facecolor=[0.1, 0.7, 0.5], label='In Condition'),
                    Patch(facecolor=[0.85, 0.85, 0.85], label='Not in Condition'),
                ]
                fig.legend(handles=legend_elements, loc='upper right', fontsize=10,
                          bbox_to_anchor=(0.99, 0.99))
                
            else:
                # Fallback: show simple binary mask
                fig, ax = plt.subplots(figsize=(14, 2))
                colors = np.zeros((1, n_volumes, 3))
                colors[0, mask, :] = [0.1, 0.7, 0.5]   # Green for retained
                colors[0, ~mask, :] = [0.9, 0.2, 0.2]  # Red for masked
                
                ax.imshow(colors, aspect='auto', extent=[0, n_volumes, 0, 1])
                ax.set_xlabel('Volume', fontsize=11, fontweight='bold')
                ax.set_yticks([])
                ax.set_xlim(0, n_volumes)
                ax.set_title('Temporal Masking', fontsize=13, fontweight='bold')
                
                n_retained = int(np.sum(mask))
                ax.text(n_volumes * 0.98, 0.5, f'{n_retained}/{n_volumes} retained',
                       ha='right', va='center', fontsize=10,
                       bbox=dict(boxstyle='round', facecolor='white', alpha=0.85))
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            logger.warning(f"Could not create censoring plot: {e}")
            return None
    
    def _create_temporal_masking_figure(self) -> Optional[plt.Figure]:
        """Create temporal masking visualization with specified design.
        
        Generates a figure showing retained vs. masked volumes using:
        - Green (#10b981) for retained volumes
        - Red (#ef4444) for masked volumes
        - 14" × variable height figure (1 row if no conditions, multiple if conditions)
        - axvspan() rendering with semi-transparent fill (alpha=0.7)
        - No y-axis ticks (categorical visualization)
        """
        if self.censoring_summary is None:
            return None
        
        try:
            mask = np.array(self.censoring_summary.get('mask', []), dtype=bool)
            conditions = self.censoring_summary.get('conditions', {})
            
            if len(mask) == 0:
                return None
            
            n_volumes = len(mask)
            
            # Define colors
            color_retained = '#10b981'    # Green for retained
            color_masked = '#ef4444'      # Red for masked
            alpha = 0.7                   # Semi-transparent fill
            
            # If conditions exist, show multiple rows (one per condition)
            if conditions:
                n_rows = len(conditions)
                figsize = (14, 1.5 * n_rows) if n_rows > 1 else (14, 2.5)
                fig, axes = plt.subplots(n_rows, 1, figsize=figsize, sharex=True, squeeze=False)
                axes = axes.flatten()
                
                # Plot each condition
                for idx, (cond_name, cond_info) in enumerate(sorted(conditions.items())):
                    ax = axes[idx]
                    cond_mask = np.array(cond_info.get('mask', []), dtype=bool)
                    
                    # Use axvspan() for each contiguous region
                    i = 0
                    while i < n_volumes:
                        current_status = cond_mask[i]
                        start = i
                        
                        # Find consecutive volumes with same status
                        while i < n_volumes and cond_mask[i] == current_status:
                            i += 1
                        
                        # Draw span for this group
                        color = color_retained if current_status else color_masked
                        ax.axvspan(start - 0.5, i - 0.5, alpha=alpha, color=color, linewidth=0)
                    
                    # Styling
                    ax.set_xlim(-0.5, n_volumes - 0.5)
                    ax.set_ylim(0, 1)
                    ax.set_yticks([])
                    ax.set_ylabel(cond_name, fontsize=11, fontweight='bold', rotation=0, ha='right', va='center')
                    
                    # Stats
                    n_cond = int(np.sum(cond_mask))
                    ax.text(n_volumes * 0.98, 0.5, f'{n_cond}/{n_volumes}',
                           ha='right', va='center', fontsize=9,
                           bbox=dict(boxstyle='round', facecolor='white', alpha=0.85))
                
                # Labels
                axes[-1].set_xlabel('Volume', fontsize=12, fontweight='bold')
                axes[0].set_title('Temporal Masking by Condition', fontsize=13, fontweight='bold')
                
                # Legend
                from matplotlib.patches import Patch
                legend_elements = [
                    Patch(facecolor=color_retained, alpha=alpha, label='In Condition'),
                    Patch(facecolor=color_masked, alpha=alpha, label='Not in Condition'),
                ]
                fig.legend(handles=legend_elements, loc='upper right', fontsize=10,
                          bbox_to_anchor=(0.99, 0.99))
                
            else:
                # Single plot: combined mask or global
                fig, ax = plt.subplots(figsize=(14, 2.5))
                
                # Use axvspan() for each volume interval
                i = 0
                while i < n_volumes:
                    current_status = mask[i]
                    start = i
                    
                    # Find consecutive volumes with same status
                    while i < n_volumes and mask[i] == current_status:
                        i += 1
                    
                    # Draw span for this group
                    color = color_retained if current_status else color_masked
                    ax.axvspan(start - 0.5, i - 0.5, alpha=alpha, color=color, linewidth=0)
                
                # Set axis properties
                ax.set_xlim(-0.5, n_volumes - 0.5)
                ax.set_ylim(0, 1)
                ax.set_xlabel('Volume', fontsize=12, fontweight='bold')
                ax.set_yticks([])  # No y-axis ticks (categorical, not quantitative)
                ax.set_xticks([0, n_volumes // 4, n_volumes // 2, 3 * n_volumes // 4, n_volumes - 1])
                ax.grid(axis='x', alpha=0.2, linestyle='--', linewidth=0.5)
                
                # Add statistics text
                n_retained = np.sum(mask)
                n_masked = n_volumes - n_retained
                pct_retained = 100.0 * n_retained / n_volumes
                
                # Title with statistics
                title_text = f'Temporal Masking: {n_retained}/{n_volumes} volumes retained ({pct_retained:.1f}%)'
                ax.set_title(title_text, fontsize=13, fontweight='bold', pad=10)
                
                # Add a subtle frame
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.spines['left'].set_visible(False)
                
                # Add legend
                from matplotlib.patches import Patch
                legend_elements = [
                    Patch(facecolor=color_retained, alpha=alpha, label=f'Retained ({n_retained})'),
                    Patch(facecolor=color_masked, alpha=alpha, label=f'Masked ({n_masked})')
                ]
                ax.legend(handles=legend_elements, loc='upper right', fontsize=10, framealpha=0.95)
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            logger.warning(f"Could not create temporal masking figure: {e}")
            return None
    
    
    def _build_connectivity_section(self) -> str:
        """Build connectivity results section."""
        if not self.connectivity_matrices:
            return ""
        
        self.toc_items.append(("connectivity", "Connectivity Results"))
        
        # Find data file path for this connectivity result
        data_file_path = ""
        if self.connectivity_paths:
            # Find .npy files (matrix files)
            matrix_files = [p for p in self.connectivity_paths if p.suffix == '.npy']
            if matrix_files:
                data_file_path = str(matrix_files[0])
        
        # Explanations for each connectivity measure type
        connectivity_explanations = {
            'correlation': """
                <div class="info-box">
                    <h4>📐 Pearson Correlation</h4>
                    <p>The <strong>Pearson correlation coefficient</strong> measures the linear relationship 
                    between the time series of each pair of regions. For regions i and j:</p>
                    <p style="text-align: center; font-family: monospace; margin: 10px 0;">
                        r<sub>ij</sub> = Σ[(x<sub>i</sub> - μ<sub>i</sub>)(x<sub>j</sub> - μ<sub>j</sub>)] / (σ<sub>i</sub> × σ<sub>j</sub> × n)
                    </p>
                    <p>where x<sub>i</sub> and x<sub>j</sub> are the time series, μ and σ are their means 
                    and standard deviations, and n is the number of time points. Values range from -1 
                    (perfect anti-correlation) to +1 (perfect correlation). The diagonal is set to zero.</p>
                    <p><strong>Use case:</strong> Standard measure for functional connectivity, captures total (direct + indirect) relationships.</p>
                </div>
            """,
            'covariance': """
                <div class="info-box">
                    <h4>📐 Covariance</h4>
                    <p>The <strong>covariance</strong> measures how two time series vary together, 
                    without normalizing by variance. For regions i and j:</p>
                    <p style="text-align: center; font-family: monospace; margin: 10px 0;">
                        cov<sub>ij</sub> = Σ[(x<sub>i</sub> - μ<sub>i</sub>)(x<sub>j</sub> - μ<sub>j</sub>)] / (n - 1)
                    </p>
                    <p>Unlike correlation, covariance preserves information about signal amplitude. 
                    Regions with higher BOLD signal variance will have larger covariance values.</p>
                    <p><strong>Use case:</strong> When signal amplitude differences between regions are meaningful, 
                    or as input for other analyses (e.g., structural equation modeling).</p>
                </div>
            """,
            'partial correlation': """
                <div class="info-box">
                    <h4>📐 Partial Correlation</h4>
                    <p>The <strong>partial correlation</strong> measures the relationship between two regions 
                    after removing the linear effects of all other regions. For regions i and j:</p>
                    <p style="text-align: center; font-family: monospace; margin: 10px 0;">
                        r<sub>ij|rest</sub> = -P<sub>ij</sub> / √(P<sub>ii</sub> × P<sub>jj</sub>)
                    </p>
                    <p>where P is the precision matrix (inverse covariance). This reveals <em>direct</em> 
                    connections by controlling for indirect paths through other regions. Values range from -1 to +1.</p>
                    <p><strong>Use case:</strong> Identifying direct functional connections, reducing spurious 
                    correlations caused by common inputs or indirect pathways.</p>
                </div>
            """,
            'precision': """
                <div class="info-box">
                    <h4>📐 Precision (Inverse Covariance)</h4>
                    <p>The <strong>precision matrix</strong> is the inverse of the covariance matrix:</p>
                    <p style="text-align: center; font-family: monospace; margin: 10px 0;">
                        P = Σ<sup>-1</sup>
                    </p>
                    <p>Non-zero off-diagonal elements P<sub>ij</sub> indicate <em>conditional dependence</em> 
                    between regions i and j given all other regions. Zero elements indicate conditional 
                    independence. The precision matrix is related to partial correlations but not normalized.</p>
                    <p><strong>Use case:</strong> Sparse network estimation, Gaussian graphical models, 
                    identifying direct statistical dependencies. Often regularized (e.g., graphical LASSO) for stability.</p>
                </div>
            """
        }
        
        html = '''
        <div class="section" id="connectivity">
            <h2>🔗 Connectivity Results</h2>
        '''
        
        for i, (matrix, labels, name) in enumerate(self.connectivity_matrices):
            # Determine the connectivity type from the name first
            connectivity_type = None
            name_lower = name.lower()
            if 'partial' in name_lower or 'partial-correlation' in name_lower:
                connectivity_type = 'partial correlation'
            elif 'precision' in name_lower:
                connectivity_type = 'precision'
            elif 'covariance' in name_lower:
                connectivity_type = 'covariance'
            elif 'correlation' in name_lower or i == 0:
                # Default to correlation for first matrix or if 'correlation' in name
                connectivity_type = 'correlation'
            
            fig = self._create_connectivity_plot(matrix, labels, name, connectivity_type)
            if fig is not None:
                fig_id = self._get_unique_figure_id()
                img_data = self._figure_to_base64(fig, dpi=150)
                
                # Save figure to disk with BIDS-compliant name
                # Map connectivity type names to BIDS-friendly descriptions
                desc_map = {
                    'correlation': 'correlation',
                    'covariance': 'covariance',
                    'partial correlation': 'partial-correlation',
                    'precision': 'precision'
                }
                desc = desc_map.get(connectivity_type, connectivity_type.replace(' ', '-'))
                saved_fig_path = self._save_figure_to_disk(fig, 'connectivity', desc, dpi=150)
                actual_fig_filename = saved_fig_path.name if saved_fig_path else 'connectivity.png'
                
                plt.close(fig)
                
                # Compute summary statistics
                upper_tri = matrix[np.triu_indices_from(matrix, k=1)]
                mean_conn = np.mean(upper_tri)
                std_conn = np.std(upper_tri)
                max_conn = np.max(upper_tri)
                min_conn = np.min(upper_tri)
                
                # Get specific data file for this matrix if multiple
                current_data_file = ""
                if i < len(self.connectivity_paths):
                    matrix_files = [p for p in self.connectivity_paths if p.suffix == '.npy']
                    if i < len(matrix_files):
                        current_data_file = str(matrix_files[i])
                elif data_file_path:
                    current_data_file = data_file_path
                
                # Get explanation for this connectivity type
                explanation_html = connectivity_explanations.get(connectivity_type, '')
                
                # Create cleaner display name for the measure
                type_display_names = {
                    'correlation': 'Pearson Correlation',
                    'covariance': 'Covariance',
                    'partial correlation': 'Partial Correlation',
                    'precision': 'Precision (Inverse Covariance)'
                }
                display_name = type_display_names.get(connectivity_type, name)
                
                # Create metric label based on type
                metric_label = 'Value' if connectivity_type in ['covariance', 'precision'] else 'Correlation'
                
                html += f'''
                <h3>{display_name}</h3>
                
                {explanation_html}
                
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-value">{matrix.shape[0]}</div>
                        <div class="metric-label">ROIs</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{mean_conn:.3f}</div>
                        <div class="metric-label">Mean {metric_label}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{std_conn:.3f}</div>
                        <div class="metric-label">Std {metric_label}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">[{min_conn:.2f}, {max_conn:.2f}]</div>
                        <div class="metric-label">Range</div>
                    </div>
                </div>
                
                <div class="figure-container">
                    <div class="figure-wrapper">
                        <img id="{fig_id}" src="data:image/png;base64,{img_data}">
                        <button class="download-btn" onclick="downloadFigure('{fig_id}', '{actual_fig_filename}')">
                            ⬇️ Download
                        </button>
                    </div>
                    <div class="figure-caption">
                        Figure: {display_name} matrix showing pairwise connectivity between 
                        {matrix.shape[0]} regions.
                        <br><strong>Data file:</strong> <code>{current_data_file}</code>
                    </div>
                </div>
                '''
                
                # Create and add histogram
                hist_fig = self._create_connectivity_histogram(matrix, name, connectivity_type)
                if hist_fig is not None:
                    hist_fig_id = self._get_unique_figure_id()
                    hist_img_data = self._figure_to_base64(hist_fig, dpi=150)
                    # Save with BIDS-compliant name (append "histogram" to description)
                    hist_desc = f"{desc}-histogram"
                    saved_hist_path = self._save_figure_to_disk(hist_fig, 'histogram', hist_desc, dpi=150)
                    actual_hist_filename = saved_hist_path.name if saved_hist_path else 'histogram.png'
                    plt.close(hist_fig)
                    
                    html += f'''
                <div class="figure-container">
                    <div class="figure-wrapper">
                        <img id="{hist_fig_id}" src="data:image/png;base64,{hist_img_data}">
                        <button class="download-btn" onclick="downloadFigure('{hist_fig_id}', '{actual_hist_filename}')">
                            ⬇️ Download
                        </button>
                    </div>
                    <div class="figure-caption">
                        Figure: Distribution of {display_name.lower()} values across all region pairs.
                        Red dashed line indicates the mean, orange dotted line indicates the median.
                    </div>
                </div>
                '''
        
        html += "</div>"
        return html
    
    def _create_connectivity_plot(
        self,
        matrix: np.ndarray,
        labels: List[str],
        name: str,
        connectivity_type: Optional[str] = None
    ) -> Optional[plt.Figure]:
        """Create connectivity matrix plot using nilearn-style visualization.
        
        Args:
            matrix: Connectivity matrix
            labels: ROI labels
            name: Atlas/analysis name
            connectivity_type: Type of connectivity measure (correlation, covariance, etc.)
        """
        try:
            n_regions = matrix.shape[0]
            
            # Build a clearer title based on connectivity type
            type_labels = {
                'correlation': 'Pearson Correlation',
                'covariance': 'Covariance',
                'partial correlation': 'Partial Correlation',
                'precision': 'Precision (Inverse Covariance)'
            }
            measure_label = type_labels.get(connectivity_type, 'Connectivity')
            
            # Determine figure size based on matrix size
            base_size = min(12, max(8, n_regions / 10))
            fig, ax = plt.subplots(figsize=(base_size, base_size))
            
            # Use nilearn-style diverging colormap
            vmax = np.max(np.abs(matrix[~np.eye(n_regions, dtype=bool)]))
            vmin = -vmax
            
            # Plot heatmap
            im = ax.imshow(matrix, cmap='RdBu_r', vmin=vmin, vmax=vmax, aspect='equal')
            
            # Add colorbar with appropriate label
            cbar_label = measure_label if connectivity_type != 'precision' else 'Precision'
            cbar = plt.colorbar(im, ax=ax, shrink=0.8, label=cbar_label)
            cbar.ax.tick_params(labelsize=9)
            
            # Add labels for smaller matrices
            if n_regions <= 50 and labels:
                ax.set_xticks(range(n_regions))
                ax.set_yticks(range(n_regions))
                ax.set_xticklabels(labels, rotation=90, fontsize=7)
                ax.set_yticklabels(labels, fontsize=7)
            else:
                ax.set_xlabel(f'Regions (n={n_regions})', fontsize=11)
                ax.set_ylabel(f'Regions (n={n_regions})', fontsize=11)
            
            # Extract atlas name from the full name (remove connectivity type suffix)
            atlas_display = name.split('_')[0] if '_' in name else name
            ax.set_title(f'{measure_label} Matrix\n({atlas_display}, {n_regions} regions)', 
                        fontsize=13, fontweight='bold', pad=10)
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            logger.warning(f"Could not create connectivity plot: {e}")
            return None
    
    def _create_connectivity_histogram(
        self,
        matrix: np.ndarray,
        name: str,
        connectivity_type: Optional[str] = None
    ) -> Optional[plt.Figure]:
        """Create histogram of connectivity values.
        
        Args:
            matrix: Connectivity matrix
            name: Atlas/analysis name
            connectivity_type: Type of connectivity measure
        """
        try:
            n_regions = matrix.shape[0]
            
            # Extract upper triangle (excluding diagonal)
            upper_tri = matrix[np.triu_indices_from(matrix, k=1)]
            
            # Build labels
            type_labels = {
                'correlation': 'Pearson Correlation',
                'covariance': 'Covariance',
                'partial correlation': 'Partial Correlation',
                'precision': 'Precision'
            }
            measure_label = type_labels.get(connectivity_type, 'Connectivity')
            
            # Create figure
            fig, ax = plt.subplots(figsize=(8, 4))
            
            # Plot histogram
            n_bins = min(50, len(upper_tri) // 20)
            n_bins = max(20, n_bins)
            
            ax.hist(upper_tri, bins=n_bins, color='steelblue', edgecolor='white', 
                   alpha=0.8, density=True)
            
            # Add vertical lines for mean and median
            mean_val = np.mean(upper_tri)
            median_val = np.median(upper_tri)
            ax.axvline(mean_val, color='red', linestyle='--', linewidth=2, 
                      label=f'Mean: {mean_val:.3f}')
            ax.axvline(median_val, color='orange', linestyle=':', linewidth=2, 
                      label=f'Median: {median_val:.3f}')
            
            # Add zero line for reference
            ax.axvline(0, color='gray', linestyle='-', linewidth=1, alpha=0.5)
            
            ax.set_xlabel(f'{measure_label} Value', fontsize=11)
            ax.set_ylabel('Density', fontsize=11)
            ax.set_title(f'Distribution of {measure_label} Values\n({len(upper_tri):,} unique pairs)', 
                        fontsize=12, fontweight='bold')
            ax.legend(loc='upper right', fontsize=9)
            
            # Add summary stats as text
            stats_text = f'Std: {np.std(upper_tri):.3f}\nMin: {np.min(upper_tri):.3f}\nMax: {np.max(upper_tri):.3f}'
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=9,
                   verticalalignment='top', fontfamily='monospace',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            logger.warning(f"Could not create connectivity histogram: {e}")
            return None
    

    def _build_brain_maps_section(self) -> str:
        """Build brain maps visualization section for seedToVoxel and roiToVoxel."""
        if not self.brain_maps:
            return ""
        
        self.toc_items.append(("brain_maps", "Brain Maps"))
        
        html = '''
        <div class="section" id="brain_maps">
            <h2>🧠 Brain Maps</h2>
            <p>Axial slices showing voxel-wise connectivity strength for each seed/ROI. 
            Lighter colors indicate stronger connectivity (in either positive or negative direction).
            Green overlay indicates the seed region (sphere) or ROI region (mask boundary).</p>
        '''
        
        for item in self.brain_maps:
            # Handle different tuple formats for backward compatibility
            if len(item) == 4:
                brain_map_path, label, seed_coords, seed_radius = item
            elif len(item) == 3:
                brain_map_path, label, seed_coords = item
                seed_radius = None
            else:
                brain_map_path, label = item
                seed_coords = None
                seed_radius = None
            
            try:
                # Try to read cut_coords from metadata sidecar
                cut_coords_from_metadata = None
                json_path = brain_map_path.with_suffix('.json')
                if json_path.exists():
                    try:
                        import json
                        with open(json_path, 'r') as f:
                            metadata = json.load(f)
                        # Try ROI center-of-mass first, then seed coordinates
                        if 'ROI_CenterOfMass_mm' in metadata:
                            cut_coords_from_metadata = tuple(metadata['ROI_CenterOfMass_mm'])
                        elif 'SeedCenterCoords_mm' in metadata:
                            cut_coords_from_metadata = tuple(metadata['SeedCenterCoords_mm'])
                    except Exception as json_error:
                        self._logger.debug(f"Could not read metadata from {json_path}: {json_error}")
                
                # Check if a pre-computed PNG exists from compute_glm_contrast_map()
                # Remove .nii/.nii.gz extension properly before adding .png
                png_name = brain_map_path.name.replace('.nii.gz', '').replace('.nii', '') + '.png'
                precomputed_png = brain_map_path.parent.parent / 'figures' / png_name
                img_data = None
                actual_fig_filename = None
                
                if precomputed_png.exists():
                    # Use the pre-computed PNG with correct coordinates
                    import base64
                    try:
                        with open(precomputed_png, 'rb') as f:
                            img_data = base64.b64encode(f.read()).decode('utf-8')
                        actual_fig_filename = precomputed_png.name
                        self._logger.debug(f"Using pre-computed PNG: {precomputed_png.name}")
                    except Exception as png_error:
                        self._logger.warning(f"Could not read pre-computed PNG: {png_error}")
                
                # If pre-computed PNG not available, generate lightbox visualization as fallback
                if img_data is None:
                    plot_seed_coords = cut_coords_from_metadata if cut_coords_from_metadata else seed_coords
                    fig = plot_lightbox_axial_slices(
                        str(brain_map_path),
                        seed_coords=plot_seed_coords,
                        seed_radius=seed_radius,
                        title=f"Connectivity Map: {label}",
                        n_slices=12,
                        n_cols=3
                    )
                    
                    if fig is not None:
                        img_data = self._figure_to_base64(fig, dpi=150)
                        actual_fig_filename = f'brainmap-{label.replace(" ", "-")}.png'
                        plt.close(fig)
                
                if img_data is not None:
                    fig_id = self._get_unique_figure_id()
                    
                    # Load NIfTI to get statistics
                    import nibabel as nib
                    img = nib.load(brain_map_path)
                    img_data_array = img.get_fdata()
                    nonzero = img_data_array[img_data_array != 0]
                    
                    # Compute statistics
                    if len(nonzero) > 0:
                        mean_val = np.mean(nonzero)
                        std_val = np.std(nonzero)
                        max_val = np.max(img_data_array)
                        min_val = np.min(img_data_array)
                        n_voxels = np.sum(img_data_array != 0)
                    else:
                        mean_val = std_val = max_val = min_val = 0
                        n_voxels = 0
                    
                    # Format seed information if available
                    seed_info_html = ""
                    if seed_coords is not None:
                        logger.debug(f"Formatting seed info for {label}: coords={seed_coords}")
                        seed_coords_str = ", ".join([f"{c:.2f}" for c in seed_coords])
                        seed_info_html = f'''<div class="metric-card">
                            <div class="metric-value">{label}</div>
                            <div class="metric-label">Seed Name</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">[{seed_coords_str}]</div>
                            <div class="metric-label">Seed Coordinates (mm)</div>
                        </div>'''
                        logger.debug(f"Generated seed_info_html: {bool(seed_info_html)}")
                    
                    # Build HTML for this brain map
                    html += f'''
                    <h3>{label}</h3>
                    
                    <div class="metrics-grid">
                        {seed_info_html}
                        <div class="metric-card">
                            <div class="metric-value">{n_voxels:,}</div>
                            <div class="metric-label">Non-zero Voxels</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">{mean_val:.3f}</div>
                            <div class="metric-label">Mean Connectivity</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">{std_val:.3f}</div>
                            <div class="metric-label">Std Connectivity</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">[{min_val:.2f}, {max_val:.2f}]</div>
                            <div class="metric-label">Range</div>
                        </div>
                    </div>
                    
                    <div class="figure-container">
                        <div class="figure-wrapper">
                            <img id="{fig_id}" src="data:image/png;base64,{img_data}">
                            <button class="download-btn" onclick="downloadFigure('{fig_id}', '{actual_fig_filename}')">
                                ⬇️ Download
                            </button>
                        </div>
                        <div class="figure-caption">
                            Figure: Orthogonal view showing connectivity strength for {label}.
                            <br><strong>File:</strong> <code>{brain_map_path.name}</code>
                        </div>
                    </div>
                    '''
                    
            except Exception as e:
                logger.warning(f"Failed to create brain map visualization for {label}: {e}")
                html += f'''
                <h3>{label}</h3>
                <div class="info-box">
                    <p>Failed to visualize brain map: {str(e)}</p>
                    <p><strong>File:</strong> <code>{brain_map_path}</code></p>
                </div>
                '''
        
        html += "</div>"
        return html

    def _build_qa_section(self) -> str:
        """Build quality assurance section."""
        if not self.qa_metrics:
            return ""
        
        self.toc_items.append(("qa", "Quality Assurance"))
        
        metrics_html = ""
        for name, value in self.qa_metrics.items():
            if isinstance(value, float):
                formatted = f"{value:.3f}"
            else:
                formatted = str(value)
            
            metrics_html += f'''
            <div class="metric-card">
                <div class="metric-value">{formatted}</div>
                <div class="metric-label">{name}</div>
            </div>
            '''
        
        html = f'''
        <div class="section" id="qa">
            <h2>✅ Quality Assurance</h2>
            
            <div class="metrics-grid">
                {metrics_html}
            </div>
            
            <div class="alert alert-success">
                <span class="alert-icon">✓</span>
                <div>Quality metrics are within acceptable ranges for functional connectivity analysis.</div>
            </div>
        </div>
        '''
        return html
    
    def _format_command_for_display(self, command: str) -> str:
        """Format CLI command with line breaks for readability.
        
        Breaks long command lines at argument boundaries to make them easier
        to read and copy in the report.
        
        Parameters
        ----------
        command : str
            Raw command line string.
        
        Returns
        -------
        str
            Formatted command with line breaks and proper indentation.
        """
        # Split the command into logical groups
        # Base command stays on first line
        parts = command.split()
        
        if len(parts) <= 4:
            # Short commands fit on one line
            return command
        
        # Start with base command (connectomix /path /path/to/output participant)
        formatted_lines = [" ".join(parts[:4])]
        
        # Group remaining arguments by category for readability
        remaining_args = parts[4:]
        
        # Known argument groups for logical organization
        arg_groups = {
            'filter': ['--participant-label', '--task', '--session', '--run'],
            'method': ['--method', '--atlas', '--roi-atlas', '--roi-mask', '--roi-label',
                      '--seeds-file', '--radius'],
            'connectivity': ['--connectivity-kind'],
            'canica': ['--n-components', '--canica-threshold', '--canica-min-region-size'],
            'temporal': ['--drop-initial', '--conditions', '--transition-buffer'],
            'output': ['--label', '--derivatives'],
        }
        
        # Track which arguments have been used
        used_args = set()
        
        # Add arguments in logical groups
        for group_name, group_keywords in arg_groups.items():
            group_args = []
            i = 0
            while i < len(remaining_args):
                arg = remaining_args[i]
                
                # Check if this arg matches any in the current group
                if any(arg == keyword or arg.startswith(keyword) 
                      for keyword in group_keywords):
                    # Collect the argument and its value(s)
                    arg_with_value = [arg]
                    i += 1
                    
                    # Collect values for this argument
                    while i < len(remaining_args) and not remaining_args[i].startswith('--'):
                        arg_with_value.append(remaining_args[i])
                        i += 1
                    
                    group_args.append(" ".join(arg_with_value))
                    used_args.add(arg)
                else:
                    i += 1
            
            if group_args:
                formatted_lines.append("    " + " ".join(group_args))
        
        # Add any remaining arguments that weren't categorized
        remaining = []
        i = 0
        while i < len(remaining_args):
            if remaining_args[i] not in used_args:
                arg_with_value = [remaining_args[i]]
                i += 1
                while i < len(remaining_args) and not remaining_args[i].startswith('--'):
                    arg_with_value.append(remaining_args[i])
                    i += 1
                remaining.append(" ".join(arg_with_value))
            else:
                i += 1
        
        if remaining:
            formatted_lines.append("    " + " ".join(remaining))
        
        return " \\\n".join(formatted_lines)
    
    def _build_command_section(self) -> str:
        """Build command line / configuration section."""
        self.toc_items.append(("reproducibility", "Reproducibility"))
        
        html = '''
        <div class="section" id="reproducibility">
            <h2>🔄 Reproducibility</h2>
            
            <p>The following information can be used to reproduce this analysis.</p>
        '''
        
        if self.command_line:
            # Format the command for better readability in the report
            formatted_cmd = self._format_command_for_display(self.command_line)
            html += f'''
            <h3>Command Line</h3>
            <p style="font-size: 0.9em; color: #666;">
                <em>Note: Paths are replaced with placeholders for portability.
                Replace <code>/path/to/rawdata</code>, <code>/path/to/derivatives</code>,
                and mask paths with actual paths on your system.</em>
            </p>
            <div class="code-block">
{formatted_cmd}
            </div>
            '''
        
        if self.config_dict:
            config_json = json.dumps(self.config_dict, indent=2, default=str)
            html += f'''
            <h3>Configuration</h3>
            <button class="collapsible">View Full Configuration</button>
            <div class="collapsible-content">
                <div class="code-block">
{config_json}
                </div>
            </div>
            '''
        
        # Software versions
        html += f'''
        <h3>Software Versions</h3>
        <table class="param-table">
            <tr><th>Software</th><th>Version</th></tr>
            <tr><td>Connectomix</td><td><code>{__version__}</code></td></tr>
            <tr><td>Python</td><td><code>{sys.version.split()[0]}</code></td></tr>
            <tr><td>NumPy</td><td><code>{np.__version__}</code></td></tr>
            <tr><td>Pandas</td><td><code>{pd.__version__}</code></td></tr>
        </table>
        </div>
        '''
        return html
    
    def _build_references_section(self) -> str:
        """Build scientific references section."""
        self.toc_items.append(("references", "References"))
        
        # Select relevant references based on analysis
        refs_to_include = ["fmriprep", "nilearn", "connectivity", "denoising"]
        
        if hasattr(self.config, 'atlas'):
            if "schaefer" in self.config.atlas.lower():
                refs_to_include.append("schaefer")
            elif "aal" in self.config.atlas.lower():
                refs_to_include.append("aal")
        
        refs_html = ""
        for ref_key in refs_to_include:
            if ref_key in REFERENCES:
                ref = REFERENCES[ref_key]
                refs_html += f'''
                <div class="reference-item">
                    <strong>{ref["authors"]}</strong> ({ref["year"]}). 
                    {ref["title"]}. <em>{ref["journal"]}</em>. 
                    <a href="{ref["url"]}" target="_blank">DOI: {ref["doi"]}</a>
                </div>
                '''
        
        html = f'''
        <div class="section" id="references">
            <h2>📚 References</h2>
            
            <p>If you use Connectomix in your research, please cite the following:</p>
            
            <div class="references">
                {refs_html}
            </div>
            
            <h3>Software Repository</h3>
            <p>
                Connectomix is open-source software available at:<br>
                <a href="https://github.com/ln2t/connectomix" target="_blank">
                    https://github.com/ln2t/connectomix
                </a>
            </p>
        </div>
        '''
        return html
    
    def _build_nav_bar(self) -> str:
        """Build navigation bar."""
        links = ""
        for section_id, title in self.toc_items:
            links += f'<a href="#{section_id}">{title}</a>'
        
        return f'''
        <nav class="nav-bar">
            <div class="nav-content">
                <div class="nav-brand">🧠 Connectomix Report</div>
                <div class="nav-links">
                    {links}
                </div>
            </div>
        </nav>
        '''
    
    def generate(self) -> Path:
        """Generate the complete HTML report.
        
        Returns:
            Path to generated report file.
        """
        self._logger.info(f"Generating participant report for {self.subject_id}")
        
        # Determine output paths first so we can set up figures directory
        # subject_id could be: '01', 'sub-01', 'sub-01_ses-1_task-rest', etc.
        if self.subject_id.startswith('sub-'):
            # Parse BIDS entities from subject_id
            parts = self.subject_id.split('_')
            sub_part = parts[0]  # sub-XX
            ses_part = None
            for p in parts[1:]:
                if p.startswith('ses-'):
                    ses_part = p
            
            # Build output path
            output_path = self.output_dir / sub_part
            if ses_part:
                output_path = output_path / ses_part
        else:
            # Simple subject ID without BIDS formatting
            output_path = self.output_dir / f"sub-{self.subject_id}"
            if self.session:
                output_path = output_path / f"ses-{self.session}"
        
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Set up figures directory
        self.figures_dir = output_path / "figures"
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        self._logger.debug(f"  Figures directory: {self.figures_dir}")
        
        # Set up connectivity data directory
        self.connectivity_data_dir = output_path / "connectivity_data"
        self.connectivity_data_dir.mkdir(parents=True, exist_ok=True)
        self._logger.debug(f"  Connectivity data directory: {self.connectivity_data_dir}")
        
        # Build all sections (this will save figures to figures_dir)
        sections_html = ""
        sections_html += self._build_overview_section()
        sections_html += self._build_parameters_section()
        sections_html += self._build_resampling_section()
        sections_html += self._build_confounds_section()
        sections_html += self._build_censoring_section()
        sections_html += self._build_connectivity_section()
        sections_html += self._build_brain_maps_section()
        sections_html += self._build_qa_section()
        sections_html += self._build_command_section()
        sections_html += self._build_references_section()
        
        # Build navigation and TOC
        nav_html = self._build_nav_bar()
        toc_html = self._build_toc()
        header_html = self._build_header()
        
        # Build footer
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        footer_html = f'''
        <div class="footer">
            <p>Generated by <strong>Connectomix v{__version__}</strong></p>
            <p>{timestamp}</p>
            <p>
                <a href="https://github.com/ln2t/connectomix" target="_blank">GitHub</a> | 
                <a href="https://github.com/ln2t/connectomix/issues" target="_blank">Report Issues</a>
            </p>
        </div>
        '''
        
        # Build title from subject_id
        title_label = self.subject_id if self.subject_id.startswith('sub-') else f"sub-{self.subject_id}"
        
        # Assemble full HTML
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connectomix Report - {title_label}</title>
    {REPORT_CSS}
</head>
<body>
    {nav_html}
    
    <div class="container">
        {header_html}
        {toc_html}
        {sections_html}
        {footer_html}
    </div>
    
    {REPORT_JS}
</body>
</html>
'''
        
        # Build report filename
        # Get denoising strategy if set
        denoising_strategy = getattr(self.config, 'denoising_strategy', None)
        
        # Sanitize all components for safe filenames
        safe_subject_id = sanitize_filename(self.subject_id)
        safe_denoising_strategy = sanitize_filename(denoising_strategy) if denoising_strategy else None
        safe_censoring = sanitize_filename(self.censoring) if self.censoring else None
        safe_condition = sanitize_filename(self.condition) if self.condition else None
        safe_label = sanitize_filename(self.label) if self.label else None
        safe_desc = sanitize_filename(self.desc) if self.desc else None
        
        if safe_subject_id.startswith('sub-'):
            filename = safe_subject_id
            if safe_denoising_strategy:
                filename += f"_denoise-{safe_denoising_strategy}"
            if safe_censoring:
                filename += f"_censoring-{safe_censoring}"
            if safe_condition:
                filename += f"_condition-{safe_condition}"
            if safe_label:
                filename += f"_label-{safe_label}"
            if safe_desc:
                filename += f"_desc-{safe_desc}"
            filename += "_report.html"
            report_path = output_path / filename
        else:
            filename_parts = [f"sub-{safe_subject_id}"]
            if self.session:
                filename_parts.append(f"ses-{sanitize_filename(self.session)}")
            if self.task:
                filename_parts.append(f"task-{sanitize_filename(self.task)}")
            if safe_denoising_strategy:
                filename_parts.append(f"denoise-{safe_denoising_strategy}")
            if safe_censoring:
                filename_parts.append(f"censoring-{safe_censoring}")
            if safe_condition:
                filename_parts.append(f"condition-{safe_condition}")
            if safe_label:
                filename_parts.append(f"label-{safe_label}")
            if safe_desc:
                filename_parts.append(f"desc-{safe_desc}")
            filename_parts.append("report.html")
            report_path = output_path / "_".join(filename_parts)
        
        # Write report
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        self._logger.info(f"Saved participant report: {report_path}")
        self._logger.info(f"Figures saved to: {self.figures_dir}")
        
        return report_path


# ============================================================================
# Convenience function for backward compatibility
# ============================================================================

def generate_participant_report(
    subject_id: str,
    session: Optional[str],
    run_info: Dict[str, Any],
    output_dir: Path,
    figures: Optional[Dict[str, plt.Figure]] = None,
) -> Path:
    """Generate participant-level analysis report (legacy interface).
    
    For new code, use ParticipantReportGenerator directly.
    """
    from connectomix.config.defaults import ParticipantConfig
    
    # Create a minimal config
    config = ParticipantConfig()
    
    report = ParticipantReportGenerator(
        subject_id=subject_id,
        session=session,
        config=config,
        output_dir=output_dir,
    )
    
    return report.generate()


# ============================================================================
# Group Report Generator
# ============================================================================

class GroupReportGenerator:
    """Generate HTML reports for group-level tangent space connectivity analysis.
    
    Creates comprehensive reports including:
    - Group mean connectivity matrix visualization
    - Individual subject deviation matrices
    - Summary statistics across subjects
    - Analysis parameters and reproducibility info
    
    Example:
        >>> from connectomix.utils.reports import GroupReportGenerator
        >>> report = GroupReportGenerator(
        ...     results=tangent_results,
        ...     config=group_config,
        ...     output_dir=Path("/data/output/group")
        ... )
        >>> report.generate()
    """
    
    def __init__(
        self,
        results: Dict[str, Any],
        config: "GroupConfig",
        output_dir: Path,
        task: Optional[str] = None,
        session: Optional[str] = None,
        atlas_coords: Optional[np.ndarray] = None,
        roi_labels: Optional[List[str]] = None,
        denoising_strategy: Optional[str] = None,
    ):
        """Initialize group report generator.
        
        Args:
            results: Dictionary from compute_tangent_connectivity() containing:
                - group_mean: Group mean connectivity matrix
                - tangent_matrices: Dict of subject tangent matrices
                - subject_ids: List of subject IDs
                - n_regions: Number of ROI regions
                - n_subjects: Number of subjects
            config: GroupConfig instance with analysis parameters.
            output_dir: Directory to save report and figures.
            task: Task name (optional).
            session: Session name (optional).
            atlas_coords: ROI coordinates for connectome plots (optional).
            roi_labels: ROI labels for matrix annotations (optional).
            denoising_strategy: Denoising strategy used (e.g., 'scrubbing5', 'simpleGSR').
        """
        self.results = results
        self.config = config
        self.output_dir = Path(output_dir)
        self.task = task
        self.session = session
        self.atlas_coords = atlas_coords
        self.roi_labels = roi_labels
        
        # Extract key values
        self.group_mean = results['group_mean']
        self.tangent_matrices = results['tangent_matrices']
        self.subject_ids = results['subject_ids']
        self.n_regions = results['n_regions']
        self.n_subjects = results['n_subjects']
        
        # Create figures directory
        self.figures_dir = self.output_dir / "figures"
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        
        self._logger = logger if 'logger' in locals() else logging.getLogger(__name__)
        self._figure_counter = 0
        self.toc_items = []
        
        # Denoising strategy - use parameter if provided, otherwise try config
        self.denoising_strategy = denoising_strategy or getattr(config, 'denoising_strategy', None)
    
    def _get_unique_figure_id(self) -> str:
        """Generate unique figure ID."""
        self._figure_counter += 1
        return f"fig_group_{self._figure_counter}"
    
    def _build_bids_figure_filename(self, figure_type: str, desc: str) -> str:
        """Build BIDS-compliant figure filename for group-level analysis.
        
        Pattern: [task-<task>][_ses-<session>][_denoise-<method>][_atlas-<atlas>]
                 [_desc-<desc>][_<figure_type>].<ext>
        
        Args:
            figure_type: Type of figure (e.g., 'connectivity', 'histogram')
            desc: Description (e.g., 'correlation', 'deviations')
            
        Returns:
            BIDS-compliant filename like: task-rest_atlas-schaefer2018n100_desc-deviations_connectivity.png
        """
        filename_parts = ["group"]
        
        if self.task:
            filename_parts.append(f"task-{self.task}")
        
        if self.session:
            filename_parts.append(f"ses-{self.session}")
        
        # Add denoising strategy
        if self.denoising_strategy and self.denoising_strategy != "none":
            filename_parts.append(f"denoise-{self.denoising_strategy}")
        
        # Add atlas
        if hasattr(self.config, 'atlas') and self.config.atlas:
            filename_parts.append(f"atlas-{self.config.atlas}")
        
        # Add description
        if desc:
            filename_parts.append(f"desc-{desc}")
        
        # Add figure type as suffix
        base_filename = "_".join(filename_parts)
        return f"{base_filename}_{figure_type}.png"
    
    def _figure_to_base64(self, fig: plt.Figure, dpi: int = 150) -> str:
        """Convert matplotlib figure to base64 string."""
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')
    
    def _save_figure_to_disk(self, fig: plt.Figure, figure_type: str, desc: str, dpi: int = 150) -> Path:
        """Save figure to disk with BIDS-compliant filename.
        
        Args:
            fig: Matplotlib figure to save
            figure_type: Type of figure (e.g., 'connectivity', 'histogram')
            desc: Description entity (e.g., 'mean', 'deviations')
            dpi: Resolution for saving
            
        Returns:
            Path to saved figure
        """
        # Build BIDS-compliant filename
        filename = self._build_bids_figure_filename(figure_type, desc)
        filepath = self.figures_dir / filename
        fig.savefig(filepath, format='png', dpi=dpi, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        return filepath
    
    def _create_group_mean_plot(self) -> Optional[plt.Figure]:
        """Create visualization of the group mean connectivity matrix."""
        try:
            n_regions = self.n_regions
            fig, ax = plt.subplots(figsize=(10, 8))
            
            # Plot matrix
            vmax = np.abs(self.group_mean).max()
            im = ax.imshow(self.group_mean, cmap='RdBu_r', vmin=-vmax, vmax=vmax,
                          aspect='equal')
            
            # Colorbar
            cbar = plt.colorbar(im, ax=ax, shrink=0.8)
            cbar.set_label('Covariance', fontsize=11)
            
            # Labels
            if n_regions <= 50 and self.roi_labels:
                ax.set_xticks(range(n_regions))
                ax.set_yticks(range(n_regions))
                ax.set_xticklabels(self.roi_labels, rotation=90, fontsize=7)
                ax.set_yticklabels(self.roi_labels, fontsize=7)
            else:
                ax.set_xlabel(f'Regions (n={n_regions})', fontsize=11)
                ax.set_ylabel(f'Regions (n={n_regions})', fontsize=11)
            
            ax.set_title(f'Group Mean Connectivity\n(Geometric Mean, {self.n_subjects} subjects)',
                        fontsize=13, fontweight='bold', pad=10)
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            self._logger.warning(f"Could not create group mean plot: {e}")
            return None
    
    def _create_tangent_deviation_plot(self) -> Optional[plt.Figure]:
        """Create visualization of tangent deviations across subjects."""
        try:
            # Select first few subjects for visualization
            max_subjects = min(4, self.n_subjects)
            
            fig, axes = plt.subplots(1, max_subjects, figsize=(4 * max_subjects, 4))
            if max_subjects == 1:
                axes = [axes]
            
            # Find common color scale
            all_tangent = np.array(list(self.tangent_matrices.values()))
            vmax = np.percentile(np.abs(all_tangent), 95)
            
            for i, (sub_id, tangent) in enumerate(list(self.tangent_matrices.items())[:max_subjects]):
                ax = axes[i]
                im = ax.imshow(tangent, cmap='RdBu_r', vmin=-vmax, vmax=vmax, aspect='equal')
                ax.set_title(f'sub-{sub_id}', fontsize=11)
                ax.set_xlabel('Regions')
                if i == 0:
                    ax.set_ylabel('Regions')
            
            # Add colorbar
            cbar = fig.colorbar(im, ax=axes, shrink=0.8, pad=0.02)
            cbar.set_label('Tangent Deviation', fontsize=10)
            
            fig.suptitle('Individual Tangent Space Deviations from Group Mean',
                        fontsize=13, fontweight='bold')
            plt.tight_layout()
            return fig
            
        except Exception as e:
            self._logger.warning(f"Could not create tangent deviation plot: {e}")
            return None
    
    def _create_deviation_histogram(self) -> Optional[plt.Figure]:
        """Create histogram of tangent deviations across all subjects."""
        try:
            fig, ax = plt.subplots(figsize=(8, 5))
            
            # Collect all off-diagonal deviations
            all_deviations = []
            for sub_id, tangent in self.tangent_matrices.items():
                upper_tri = tangent[np.triu_indices_from(tangent, k=1)]
                all_deviations.extend(upper_tri)
            
            all_deviations = np.array(all_deviations)
            
            # Plot histogram
            ax.hist(all_deviations, bins=50, density=True, alpha=0.7,
                   color='steelblue', edgecolor='white')
            ax.axvline(0, color='red', linestyle='--', linewidth=1.5, label='Zero')
            ax.axvline(np.mean(all_deviations), color='orange', linestyle='-',
                      linewidth=1.5, label=f'Mean: {np.mean(all_deviations):.3f}')
            
            ax.set_xlabel('Tangent Deviation Value', fontsize=11)
            ax.set_ylabel('Density', fontsize=11)
            ax.set_title('Distribution of Tangent Space Deviations\n(All subjects, all connections)',
                        fontsize=12, fontweight='bold')
            ax.legend(loc='upper right')
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            self._logger.warning(f"Could not create deviation histogram: {e}")
            return None
    
    def _create_subject_variance_plot(self) -> Optional[plt.Figure]:
        """Create plot showing variance across subjects for each connection."""
        try:
            # Stack all tangent matrices
            all_tangent = np.array([self.tangent_matrices[s] for s in self.subject_ids])
            
            # Compute variance across subjects for each connection
            variance = np.var(all_tangent, axis=0)
            
            fig, ax = plt.subplots(figsize=(10, 8))
            
            im = ax.imshow(variance, cmap='viridis', aspect='equal')
            cbar = plt.colorbar(im, ax=ax, shrink=0.8)
            cbar.set_label('Variance Across Subjects', fontsize=11)
            
            ax.set_xlabel(f'Regions (n={self.n_regions})', fontsize=11)
            ax.set_ylabel(f'Regions (n={self.n_regions})', fontsize=11)
            ax.set_title(f'Inter-Subject Variability in Connectivity\n({self.n_subjects} subjects)',
                        fontsize=13, fontweight='bold', pad=10)
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            self._logger.warning(f"Could not create subject variance plot: {e}")
            return None
    
    def _build_summary_section(self) -> str:
        """Build summary statistics section."""
        self.toc_items.append(("summary", "Summary"))
        
        # Compute statistics on group mean
        upper_tri = self.group_mean[np.triu_indices_from(self.group_mean, k=1)]
        mean_conn = np.mean(upper_tri)
        std_conn = np.std(upper_tri)
        
        return f'''
        <section id="summary" class="section">
            <h2>📊 Analysis Summary</h2>
            
            <div class="summary-cards">
                <div class="summary-card">
                    <h3>Subjects</h3>
                    <div class="stat-value">{self.n_subjects}</div>
                    <div class="stat-label">Total Subjects</div>
                </div>
                <div class="summary-card">
                    <h3>Regions</h3>
                    <div class="stat-value">{self.n_regions}</div>
                    <div class="stat-label">ROI Regions</div>
                </div>
                <div class="summary-card">
                    <h3>Connections</h3>
                    <div class="stat-value">{self.n_regions * (self.n_regions - 1) // 2:,}</div>
                    <div class="stat-label">Unique Pairs</div>
                </div>
                <div class="summary-card">
                    <h3>Group Mean</h3>
                    <div class="stat-value">{mean_conn:.3f}</div>
                    <div class="stat-label">± {std_conn:.3f}</div>
                </div>
            </div>
            
            <div class="info-box">
                <h4>📚 About Tangent Space Connectivity</h4>
                <p>This analysis uses the <strong>tangent space</strong> approach from nilearn,
                which provides a principled way to analyze group connectivity:</p>
                <ul>
                    <li><strong>Group Mean</strong>: The geometric mean of covariance matrices across
                    all subjects, capturing shared connectivity patterns.</li>
                    <li><strong>Tangent Vectors</strong>: Individual subject deviations from the group
                    mean, projected into tangent space for proper statistical analysis.</li>
                    <li><strong>Advantages</strong>: Better statistical properties (Euclidean space),
                    captures both correlations and partial correlations information.</li>
                </ul>
                <p><em>Reference: Varoquaux et al., MICCAI 2010</em></p>
            </div>
            
            <h3>Subjects Included</h3>
            <div class="subjects-grid">
                {''.join(f'<span class="subject-badge">sub-{s}</span>' for s in self.subject_ids)}
            </div>
        </section>
        '''
    
    def _build_group_mean_section(self) -> str:
        """Build group mean connectivity section."""
        self.toc_items.append(("group-mean", "Group Mean Connectivity"))
        
        html = '''
        <section id="group-mean" class="section">
            <h2>🧠 Group Mean Connectivity</h2>
            
            <p>The group mean connectivity matrix represents the geometric mean of covariance
            matrices across all subjects. This captures the common connectivity structure
            shared by the group.</p>
        '''
        
        # Add group mean plot
        fig = self._create_group_mean_plot()
        if fig is not None:
            fig_id = self._get_unique_figure_id()
            img_data = self._figure_to_base64(fig, dpi=150)
            saved_path = self._save_figure_to_disk(fig, 'connectivity', 'mean', dpi=150)
            actual_filename = saved_path.name
            plt.close(fig)
            
            html += f'''
            <div class="figure-container">
                <div class="figure-wrapper">
                    <img id="{fig_id}" src="data:image/png;base64,{img_data}">
                    <button class="download-btn" onclick="downloadFigure('{fig_id}', '{actual_filename}')">
                        ⬇️ Download
                    </button>
                </div>
                <div class="figure-caption">
                    Figure: Group mean connectivity matrix showing the geometric mean of covariance
                    matrices across {self.n_subjects} subjects. Atlas: {self.config.atlas}.
                </div>
            </div>
            '''
        
        html += '</section>'
        return html
    
    def _build_tangent_section(self) -> str:
        """Build tangent deviation visualization section."""
        self.toc_items.append(("tangent", "Individual Deviations"))
        
        html = '''
        <section id="tangent" class="section">
            <h2>📈 Individual Tangent Space Deviations</h2>
            
            <p>Each subject's connectivity is represented as a deviation from the group mean
            in tangent space. These matrices show how individual subjects differ from the
            group pattern.</p>
        '''
        
        # Add tangent deviation plot
        fig = self._create_tangent_deviation_plot()
        if fig is not None:
            fig_id = self._get_unique_figure_id()
            img_data = self._figure_to_base64(fig, dpi=150)
            saved_path = self._save_figure_to_disk(fig, 'deviation', 'tangent', dpi=150)
            actual_filename = saved_path.name
            plt.close(fig)
            
            html += f'''
            <div class="figure-container">
                <div class="figure-wrapper">
                    <img id="{fig_id}" src="data:image/png;base64,{img_data}">
                    <button class="download-btn" onclick="downloadFigure('{fig_id}', '{actual_filename}')">​
                        ⬇️ Download
                    </button>
                </div>
                <div class="figure-caption">
                    Figure: Individual tangent space deviations from the group mean connectivity.
                    Red indicates stronger than average connectivity, blue indicates weaker.
                </div>
            </div>
            '''
        
        # Add deviation histogram
        fig = self._create_deviation_histogram()
        if fig is not None:
            fig_id = self._get_unique_figure_id()
            img_data = self._figure_to_base64(fig, dpi=150)
            saved_path = self._save_figure_to_disk(fig, 'histogram', 'deviation', dpi=150)
            actual_filename = saved_path.name
            plt.close(fig)
            
            html += f'''
            <div class="figure-container">
                <div class="figure-wrapper">
                    <img id="{fig_id}" src="data:image/png;base64,{img_data}">
                    <button class="download-btn" onclick="downloadFigure('{fig_id}', '{actual_filename}')">
                        ⬇️ Download
                    </button>
                </div>
                <div class="figure-caption">
                    Figure: Distribution of tangent space deviation values across all subjects
                    and all connections. Centered around zero indicates well-balanced group.
                </div>
            </div>
            '''
        
        # Add variance plot
        fig = self._create_subject_variance_plot()
        if fig is not None:
            fig_id = self._get_unique_figure_id()
            img_data = self._figure_to_base64(fig, dpi=150)
            saved_path = self._save_figure_to_disk(fig, 'variance', 'inter-subject', dpi=150)
            actual_filename = saved_path.name
            plt.close(fig)
            
            html += f'''
            <div class="figure-container">
                <div class="figure-wrapper">
                    <img id="{fig_id}" src="data:image/png;base64,{img_data}">
                    <button class="download-btn" onclick="downloadFigure('{fig_id}', '{actual_filename}')">
                        ⬇️ Download
                    </button>
                </div>
                <div class="figure-caption">
                    Figure: Inter-subject variability showing which connections have the most
                    variance across subjects. High variance connections may be of interest
                    for individual differences research.
                </div>
            </div>
            '''
        
        html += '</section>'
        return html
    
    def _build_methods_section(self) -> str:
        """Build methods and parameters section."""
        self.toc_items.append(("methods", "Methods"))
        
        return f'''
        <section id="methods" class="section">
            <h2>⚙️ Analysis Parameters</h2>
            
            <table class="params-table">
                <tr><th colspan="2">Group Analysis Configuration</th></tr>
                <tr><td>Atlas</td><td><code>{self.config.atlas}</code></td></tr>
                <tr><td>Method</td><td><code>{self.config.method}</code></td></tr>
                <tr><td>Connectivity Measure</td><td><code>tangent</code></td></tr>
                <tr><td>Task Filter</td><td><code>{self.task or 'None'}</code></td></tr>
                <tr><td>Session Filter</td><td><code>{self.session or 'None'}</code></td></tr>
                <tr><td>Subjects Included</td><td><code>{self.n_subjects}</code></td></tr>
                <tr><td>ROI Regions</td><td><code>{self.n_regions}</code></td></tr>
            </table>
            
            <h3>Software Versions</h3>
            <table class="params-table">
                <tr><td>Connectomix</td><td><code>{__version__}</code></td></tr>
                <tr><td>Python</td><td><code>{sys.version.split()[0]}</code></td></tr>
                <tr><td>NumPy</td><td><code>{np.__version__}</code></td></tr>
            </table>
        </section>
        '''
    
    def generate(self) -> Path:
        """Generate the complete HTML report.
        
        Returns:
            Path to the generated HTML report file.
        """
        self._logger.info("Generating group analysis report...")
        
        # Build sections
        summary = self._build_summary_section()
        group_mean = self._build_group_mean_section()
        tangent = self._build_tangent_section()
        methods = self._build_methods_section()
        
        # Build TOC
        toc_html = '<ul class="toc-list">'
        for item_id, item_title in self.toc_items:
            toc_html += f'<li><a href="#{item_id}">{item_title}</a></li>'
        toc_html += '</ul>'
        
        # Build navigation
        nav_html = f'''
        <nav class="nav-bar">
            <div class="nav-content">
                <span class="nav-title">Connectomix Group Report</span>
                <span class="nav-subtitle">
                    Atlas: {self.config.atlas} | 
                    {self.n_subjects} subjects | 
                    {datetime.now().strftime("%Y-%m-%d")}
                </span>
            </div>
        </nav>
        '''
        
        # Assemble full HTML
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connectomix Group Report - {self.config.atlas}</title>
    {REPORT_CSS}
    <style>
        .subjects-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}
        .subject-badge {{
            background: var(--primary-color);
            color: white;
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    {nav_html}
    <div class="container">
        <header class="header">
            <h1>🧠 Connectomix Group Analysis Report</h1>
            <p class="header-subtitle">Tangent Space Connectivity Analysis</p>
        </header>
        
        <nav class="toc">
            <h3>📋 Contents</h3>
            {toc_html}
        </nav>
        
        {summary}
        {group_mean}
        {tangent}
        {methods}
        
        <footer class="footer">
            <p>Generated by Connectomix v{__version__} on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        </footer>
    </div>
    
    {REPORT_JS}
</body>
</html>
'''
        
        # Determine output filename
        filename_parts = []
        if self.task:
            filename_parts.append(f"task-{self.task}")
        if self.session:
            filename_parts.append(f"ses-{self.session}")
        filename_parts.append(f"atlas-{self.config.atlas}")
        if self.config.label:
            filename_parts.append(f"label-{self.config.label}")
        filename_parts.append("group_report.html")
        
        report_path = self.output_dir / "_".join(filename_parts)
        
        # Write report
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        self._logger.info(f"Saved group report: {report_path}")
        self._logger.info(f"Figures saved to: {self.figures_dir}")
        
        return report_path

