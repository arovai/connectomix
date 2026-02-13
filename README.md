# Connectomix

<p align="center">
  <strong>Functional Connectivity Analysis from fmridenoiser Outputs</strong>
</p>

<p align="center">
  <a href="#installation">Installation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#configuration">Configuration</a>
</p>

---

## Overview

**Connectomix** is a BIDS-compliant tool for computing functional connectivity from pre-denoised fMRI data. Built on **Nilearn**, it works with denoised outputs from **fmridenoiser** (recommended) or other denoising pipelines that produce BIDS `desc-denoised_bold` files. Connectomix supports multiple connectivity methods at the participant level, with comprehensive HTML reports for quality assurance.

**Note:** Group-level analysis is under development and should not be used yet.

### Key Features

- 🧠 **Four connectivity methods**: seed-to-voxel, ROI-to-voxel, seed-to-seed, ROI-to-ROI
- 📊 **Four connectivity measures**: correlation, covariance, partial correlation, precision
- 📈 **Participant-level analysis**: Process individual subjects (first-level analysis)
- ⏱️ **Condition-based temporal masking**: select specific task conditions for analysis
- 📋 **BIDS-compliant**: standardized input/output structure
- 📄 **HTML reports**: connectivity matrices, connectome plots, atlas visualizations

### Technology Stack

- Python 3.8+
- [Nilearn](https://nilearn.github.io/) for neuroimaging operations
- [PyBIDS](https://bids-standard.github.io/pybids/) for BIDS compliance
- [Nibabel](https://nipy.org/nibabel/) for NIfTI I/O
- NumPy, Pandas, SciPy for data processing

---

## Installation

```bash
# Clone the repository
git clone https://github.com/ln2t/connectomix.git
cd connectomix

# Install in development mode
pip install -e .

# Verify installation
connectomix --version
```

**Requirements:**
- Python 3.8+
- fMRIPrep outputs (produced by [fMRIPrep](https://fmriprep.org/))
- Denoised data from [fmridenoiser](https://github.com/ln2t/fmridenoiser) or similar pipeline

---

## Quick Start

### Preprocessing Requirement

Connectomix requires **pre-denoised fMRI data**. Before running Connectomix, you must first denoise your data using [fmridenoiser](https://github.com/ln2t/fmridenoiser) or another denoising pipeline that produces BIDS `desc-denoised_bold` files.

Note that fmridenoiser expects fMRIPrep output as input (not raw BIDS data) - see [fmridenoiser](https://github.com/ln2t/fmridenoiser) for more information.

**Complete Workflow:**

```bash
# Step 1: Run fMRIPrep on your raw BIDS data (if not already done)
fmriprep /path/to/bids /path/to/fmriprep_output participant

# Step 2: Denoise fMRIPrep outputs with fmridenoiser
fmridenoiser /path/to/fmriprep_output /path/to/fmridenoiser_output participant

# Step 3: Run Connectomix on the denoised outputs
connectomix /path/to/fmridenoiser_output /path/to/connectomix_output participant
```

### Common Workflow Examples

```bash
# Process specific participant with default settings
connectomix /path/to/fmridenoiser_output /data/output participant \
    --participant-label 01

# Process task and custom atlas
connectomix /path/to/fmridenoiser_output /data/output participant \
    --task rest --atlas aal

# Using configuration  for fully customized processing
connectomix /path/to/fmridenoiser_output /data/output participant \
    --config analysis_config.yaml
```

### Four Processing Methods

Connectomix supports four distinct connectivity analysis methods, each suited for different research questions:

| Method | Input | Output | Best For |
|--------|-------|--------|----------|
| **Seed-to-Voxel** | Seed region(s) + whole brain | NIfTI maps (one per seed) | Identifying voxels connected to specific regions of interest |
| **ROI-to-Voxel** | ROI region(s) + whole brain | NIfTI maps (one per ROI) | Mapping connectivity from anatomically or functionally defined areas |
| **Seed-to-Seed** | Multiple seed regions | Correlation matrix | Analyzing connectivity within a predefined network |
| **ROI-to-ROI** | Standard or custom atlas | Connectivity matrices (4 measures) | Whole-brain parcellation-based connectivity (most common) |

**Quick Reference:**
- Use **Seed-to-Voxel** or **ROI-to-Voxel** for hypothesis-driven analyses with a priori regions
- Use **Seed-to-Seed** or **ROI-to-ROI** for network-level connectivity (correlation, covariance, partial correlation, precision)
- **ROI-to-ROI** is the most common approach, using standard atlases like Schaefer or AAL

See the [Configuration](#configuration) section for detailed examples and configuration options for each method.

#### Condition-Based Temporal Censoring with Raw Data

If you need to apply condition-based masking (selecting specific task conditions), you must provide access to the task events file:

```bash
# Use denoised output directory with events file
connectomix /path/to/fmridenoiser_output /data/output participant \
    --events-file /path/to/task-events.tsv \
    --conditions "go,baseline"
```

Alternatively, provide events from raw BIDS:

```bash
# If using raw BIDS with derivatives path
connectomix /data/bids /data/output participant \
    --derivatives fmridenoiser=/path/to/fmridenoiser \
    --conditions "go,stop"
```


### Common Command-Line Arguments

| Argument | Short | Description | Example |
|----------|-------|-------------|---------|
| `--derivatives` | `-d` | Denoised derivatives location | `-d fmridenoiser=/path/to/fmridenoiser` |
| `--participant-label` | `-p` | Subject(s) to process | `-p 01` |
| `--task` | `-t` | Task name to process | `-t restingstate` |
| `--session` | `-s` | Session to process | `-s 1` |
| `--run` | `-r` | Run to process | `-r 1` |
| `--space` | | MNI space to use | `--space MNI152NLin2009cAsym` |
| `--config` | `-c` | Config file path | `-c my_config.yaml` |
| `--atlas` | | Atlas for ROI connectivity | `--atlas schaefer2018n200` |
| `--method` | | Connectivity method | `--method roiToRoi` |
| `--roi-atlas` | | Atlas for roi-to-voxel method | `--roi-atlas schaefer_100` |
| `--roi-label` | | ROI label(s) from atlas or mask | `--roi-label 7Networks_DMN_PCC` |
| `--roi-mask` | | Path to binary ROI mask file(s) | `--roi-mask /path/to/roi.nii.gz` |
| `--conditions` | | Task conditions for temporal masking | `--conditions face house` |
| `--events-file` | | Path to events.tsv file (optional) | `--events-file events.tsv` |
| `--label` | | Custom output label | `--label myanalysis` |
| `--verbose` | `-v` | Enable debug output | `-v` |

---

## ⚠️ Important Note

**Group-level analysis is currently under development and should NOT be used yet.**

Connectomix currently supports participant-level (first-level) connectivity analysis only. Group-level statistical inference is planned for a future release. Please use the participant-level analysis workflow for your analyses.

---

## Manual Atlas Dataset Download (Optional)

By default, Connectomix automatically downloads standard atlases (Schaefer, AAL, Harvard-Oxford) on first use via nilearn. However, in offline environments or for pre-caching purposes, you can manually download and cache these datasets locally.

#### Where Connectomix Looks for Atlases

Connectomix (via nilearn) searches for atlas data in this order:

1. `$NILEARN_DATA` environment variable (if set)
2. `~/nilearn_data` (nilearn default cache)

#### Manual Setup Steps

##### 1. Create the Cache Directory

```bash
# Create the nilearn data directory (default location)
mkdir -p ~/nilearn_data
```

##### 2. Download Schaefer 2018 Atlas

**Download URLs:**
- 100 parcels: https://raw.githubusercontent.com/ThomasYeoLab/CBIG/v0.14.3-Update_Yeo2011_Schaefer2018_labelname/stable_projects/brain_parcellation/Schaefer2018_LocalGlobal/Parcellations/MNI/Schaefer2018_100Parcels_7Networks_order_FSLMNI152_2mm.nii.gz
- 100 parcels labels: https://raw.githubusercontent.com/ThomasYeoLab/CBIG/v0.14.3-Update_Yeo2011_Schaefer2018_labelname/stable_projects/brain_parcellation/Schaefer2018_LocalGlobal/Parcellations/MNI/Schaefer2018_100Parcels_7Networks_order.txt
- 200 parcels: (replace `100Parcels` with `200Parcels` in the URL above)

**Installation:**

```bash
# Create Schaefer directory
mkdir -p ~/nilearn_data/schaefer_2018

# Download 100-parcel version
cd ~/nilearn_data/schaefer_2018

# Using wget
wget https://raw.githubusercontent.com/ThomasYeoLab/CBIG/v0.14.3-Update_Yeo2011_Schaefer2018_labelname/stable_projects/brain_parcellation/Schaefer2018_LocalGlobal/Parcellations/MNI/Schaefer2018_100Parcels_7Networks_order_FSLMNI152_2mm.nii.gz
wget https://raw.githubusercontent.com/ThomasYeoLab/CBIG/v0.14.3-Update_Yeo2011_Schaefer2018_labelname/stable_projects/brain_parcellation/Schaefer2018_LocalGlobal/Parcellations/MNI/Schaefer2018_100Parcels_7Networks_order.txt

# OR using curl
curl -O https://raw.githubusercontent.com/ThomasYeoLab/CBIG/v0.14.3-Update_Yeo2011_Schaefer2018_labelname/stable_projects/brain_parcellation/Schaefer2018_LocalGlobal/Parcellations/MNI/Schaefer2018_100Parcels_7Networks_order_FSLMNI152_2mm.nii.gz
curl -O https://raw.githubusercontent.com/ThomasYeoLab/CBIG/v0.14.3-Update_Yeo2011_Schaefer2018_labelname/stable_projects/brain_parcellation/Schaefer2018_LocalGlobal/Parcellations/MNI/Schaefer2018_100Parcels_7Networks_order.txt
```

##### 3. Download AAL Atlas

**Download URL:**
- AAL SPM12: https://www.gin.cnrs.fr/wp-content/uploads/aal_for_SPM12.tar.gz
- AAL v3.2: https://www.gin.cnrs.fr/wp-content/uploads/AAL3v2_for_SPM12.tar.gz

**Installation:**

```bash
# Create AAL directory
mkdir -p ~/nilearn_data/aal_SPM12

# Download and extract
cd ~/nilearn_data

# Using wget
wget https://www.gin.cnrs.fr/wp-content/uploads/aal_for_SPM12.tar.gz
tar -xzf aal_for_SPM12.tar.gz -C aal_SPM12/

# OR using curl
curl -O https://www.gin.cnrs.fr/wp-content/uploads/aal_for_SPM12.tar.gz
tar -xzf aal_for_SPM12.tar.gz -C aal_SPM12/

# Verify the structure
ls aal_SPM12/aal/atlas/
# Should contain: AAL.nii, AAL.xml, ROI_MNI_V4.txt, ROI_MNI_V4.xml
```

##### 4. Download Harvard-Oxford Atlas

Harvard-Oxford is typically distributed as part of FSL. The easiest way is to extract it from the FSL distribution or download directly.

**From FSL GitHub:**

```bash
# Create FSL directory
mkdir -p ~/nilearn_data/fsl/data/atlases/HarvardOxford

cd ~/nilearn_data/fsl/data/atlases/HarvardOxford

# Download Harvard-Oxford cortical atlas (2mm resolution)
wget https://fsl.fmrib.ox.ac.uk/fsldownloads/fslconda/data/HarvardOxford-cort-maxprob-thr25-2mm.nii.gz

# Download Harvard-Oxford subcortical atlas
wget https://fsl.fmrib.ox.ac.uk/fsldownloads/fslconda/data/HarvardOxford-sub-maxprob-thr25-2mm.nii.gz

# Download XML labels (from FSL repository)
wget https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/Atlases/HarvardOxford-Cortical.xml -O ./HarvardOxford-Cortical.xml
```

**From local FSL installation (if FSL is already installed):**

```bash
# Copy from FSL installation
cp -r $FSLDIR/data/atlases/HarvardOxford ~/nilearn_data/fsl/data/atlases/
```

#### Verify the Installation

Test that Connectomix can access the cached atlases:

```bash
# This will use the cached schaefer2018n100 atlas
connectomix /path/to/fmridenoiser_output /data/output participant --atlas schaefer2018n100

# This will use the cached AAL atlas
connectomix /path/to/fmridenoiser_output /data/output participant --atlas aal

# This will use the cached Harvard-Oxford atlas
connectomix /path/to/fmridenoiser_output /data/output participant --atlas harvardoxford
```

If Connectomix finds the cached datasets, it will proceed without attempting to download.

#### Troubleshooting

**Atlas not found error:**

```
Unknown atlas: schaefer2018n100
```

Check that files are in the correct location:

```bash
# For Schaefer
ls ~/nilearn_data/schaefer_2018/Schaefer2018_100Parcels_7Networks_order_FSLMNI152_2mm.nii.gz

# For AAL
ls ~/nilearn_data/aal_SPM12/aal/atlas/AAL.nii

# For Harvard-Oxford
ls ~/nilearn_data/fsl/data/atlases/HarvardOxford/HarvardOxford-cort-maxprob-thr25-2mm.nii.gz
```

**Using a custom cache location:**

```bash
# Set environment variable before running Connectomix
export NILEARN_DATA=/custom/atlas/path
connectomix /path/to/fmridenoiser_output /data/output participant --atlas schaefer2018n100
```

---

### Using a Custom Atlas

Connectomix allows you to use a custom parcellation atlas for ROI-to-ROI or ROI-to-voxel analysis. A custom atlas requires:

1. **A parcellation NIfTI file** — 3D image where each ROI has a unique non-zero integer label (background = 0)
2. **(Optional) A labels file** — human-readable ROI names
3. **(Optional) MNI coordinates** — for connectome (glass brain) visualizations

#### Option 1: Provide a Direct Path

Pass the full path to a NIfTI parcellation file:

```bash
connectomix /path/to/fmridenoiser_output /data/output participant \
  --atlas /path/to/my_atlas.nii.gz
```

If you have a labels file, name it with the **same basename** as your NIfTI file:
- `my_atlas.nii.gz` → `my_atlas.csv`, `my_atlas.tsv`, `my_atlas.txt`, or `my_atlas.json`

#### Option 2: Place the Atlas in Nilearn's Data Directory

Create a folder in `~/nilearn_data` (or `$NILEARN_DATA`) with your atlas:

```bash
mkdir -p ~/nilearn_data/my_custom_atlas
cp /path/to/atlas.nii.gz ~/nilearn_data/my_custom_atlas/
cp /path/to/labels.csv ~/nilearn_data/my_custom_atlas/
```

Then reference it by folder name:

```bash
connectomix /path/to/fmridenoiser_output /data/output participant --atlas my_custom_atlas
```

#### Supported Label File Formats

Connectomix supports multiple formats for specifying ROI names and coordinates:

**CSV with coordinates (recommended for connectome plots):**

```csv
x,y,z,name,network
-53.28,-8.88,32.36,L Auditory,Auditory
53.47,-6.49,27.52,R Auditory,Auditory
-0.15,51.42,7.58,Frontal DMN,DMN
```

Columns `x`, `y`, `z` specify MNI coordinates for each ROI centroid. These are used for:
- Glass brain / connectome visualizations
- Spatial reference in JSON sidecars

**TSV (like Schaefer atlas):**

```tsv
1	7Networks_LH_Vis_1	120	18	131	0
2	7Networks_LH_Vis_2	120	18	132	0
```

The second column is used as the ROI name.

**Plain text (one label per line):**

```text
LeftHippocampus
RightHippocampus
LeftAmygdala
RightAmygdala
```

**As a space-separated file:**

```txt
LeftHippocampus RightHippocampus LeftAmygdala RightAmygdala
```

#### File Naming Convention

Labels files are searched in this priority order:

1. **Same basename as NIfTI**: `my_atlas.csv` for `my_atlas.nii.gz`
2. **Generic labels file**: `labels.csv`, `labels.tsv`, `labels.txt`, `labels.json`

#### What Happens Without a Labels File?

If no labels file is found, Connectomix will:
1. Extract unique integer values from the parcellation image
2. Generate labels as `ROI_1`, `ROI_2`, etc.
3. Compute ROI centroid coordinates automatically using nilearn

> **Tip:** For publication-quality connectome plots, provide a CSV with MNI coordinates and meaningful ROI names.

---

## Configuration

### Configuration File

For complex analyses, use a YAML configuration file:

```bash
connectomix /path/to/fmridenoiser_output /data/output participant -c config.yaml
```

### Participant-Level Configuration

```yaml
# participant_config.yaml

# BIDS filters
subject: ["01", "02", "03"]
tasks: ["restingstate"]
sessions: null
spaces: ["MNI152NLin2009cAsym"]

# Analysis method
method: "roiToRoi"
atlas: "schaefer2018n100"
connectivity_kind: "correlation"

# Denoising
confounds: ["csf", "white_matter", "trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"]
high_pass: 0.01
low_pass: 0.08

# Temporal censoring (optional)
temporal_censoring:
  enabled: true
  drop_initial_volumes: 4
  condition_selection:
    enabled: true
    conditions: ["face", "house"]
```

---

## Output Structure

```
output_dir/
├── dataset_description.json          # BIDS derivative metadata
├── config/
│   └── backups/
│       └── config_TIMESTAMP.json     # Configuration backups
├── sub-01/
│   ├── figures/                      # Report figures (with denoising strategy)
│   │   ├── connectivity_correlation_denoise-simpleGSR.png
│   │   ├── connectivity_covariance_denoise-simpleGSR.png
│   │   ├── connectivity_partial-correlation_denoise-simpleGSR.png
│   │   ├── connectivity_precision_denoise-simpleGSR.png
│   │   ├── histogram_correlation_denoise-simpleGSR.png       # Value distributions
│   │   ├── temporal_censoring_denoise-simpleGSR.png
│   │   └── sub-01_report_denoise-simpleGSR.html
│   ├── func/                         # Denoised functional data
│   │   ├── sub-01_task-rest_desc-denoised_bold.nii.gz
│   │   └── sub-01_task-rest_desc-denoised_bold.json
│   └── connectivity_data/            # Connectivity matrices & time series
│       ├── sub-01_task-rest_atlas-schaefer_desc-correlation_connectivity.npy
│       ├── sub-01_task-rest_atlas-schaefer_desc-covariance_connectivity.npy
│       ├── sub-01_task-rest_atlas-schaefer_desc-partial-correlation_connectivity.npy
│       ├── sub-01_task-rest_atlas-schaefer_desc-precision_connectivity.npy
│       └── sub-01_task-rest_atlas-schaefer_timeseries.npy
├── sub-02/
│   └── ...
```
```

### Connectivity Data Files

Each connectivity matrix (`.npy`) has an accompanying JSON sidecar with metadata:

```json
{
    "ConnectivityMeasure": "correlation",
    "AtlasName": "schaefer2018n100",
    "NumRegions": 100,
    "MatrixShape": [100, 100],
    "ROILabels": ["7Networks_LH_Vis_1", "7Networks_LH_Vis_2", "..."],
    "ROICoordinates": [[-22.0, -93.0, -9.0], [-26.0, -81.0, -11.0], "..."],
    "CoordinateSpace": "MNI152NLin2009cAsym",
    "fMRIPrepVersion": "23.1.0",
    "EffectiveVolumeCount": 180,
    "HighPass": 0.01,
    "LowPass": 0.08
}
```

**ROICoordinates** are MNI centroids (x, y, z) for each ROI, enabling connectome glass brain visualization with tools like nilearn's `plot_connectome()`.

**Atlas matrix shapes:**
| Atlas | Regions | Matrix Shape |
|-------|---------|--------------|
| `schaefer2018n100` | 100 | 100 × 100 |
| `schaefer2018n200` | 200 | 200 × 200 |
| `aal` | 116 | 116 × 116 |
| `harvardoxford` | 96 | 96 × 96 |


### Loading Connectivity Data

```python
import numpy as np
import json
from pathlib import Path

# Load connectivity matrix
conn_file = Path('sub-01/connectivity_data/sub-01_task-rest_atlas-schaefer_desc-correlation_connectivity.npy')
connectivity = np.load(conn_file)

# Load metadata from JSON sidecar
json_file = conn_file.with_suffix('.json')
with open(json_file) as f:
    metadata = json.load(f)

# Access ROI coordinates for connectome plotting
roi_coords = np.array(metadata['ROICoordinates'])
roi_labels = metadata['ROILabels']

# Plot connectome using nilearn
from nilearn.plotting import plot_connectome
plot_connectome(connectivity, roi_coords, 
                edge_threshold='95%', 
                node_size=20,
                title=f"Subject 01 - {metadata['ConnectivityMeasure']}")
```

### Vectorization for Machine Learning

Connectivity matrices can be vectorized for machine learning applications:

```python
def matrix_to_vector(matrix):
    """Convert symmetric matrix to upper triangle vector."""
    indices = np.triu_indices(matrix.shape[0], k=1)
    return matrix[indices]

def vector_to_matrix(vector, n_regions):
    """Reconstruct symmetric matrix from vector."""
    matrix = np.zeros((n_regions, n_regions))
    indices = np.triu_indices(n_regions, k=1)
    matrix[indices] = vector
    matrix = matrix + matrix.T
    return matrix

# Stack connectivity vectors from multiple subjects
n_regions = 100
n_subjects = 50
connectivity_vectors = np.zeros((n_subjects, n_regions*(n_regions-1)//2))

for i, sub_dir in enumerate(Path('/output').glob('sub-*')):
    conn = np.load(sub_dir / 'connectivity_data' / '*_desc-correlation_connectivity.npy')
    connectivity_vectors[i] = matrix_to_vector(conn)
```

### HTML Report Contents

Each participant-level HTML report includes:

| Section | Contents |
|---------|----------|
| **Summary** | Subject info, processing parameters, key metrics |
| **Denoising** | Confound time series, inter-correlation matrix, before/after histogram |
| **Temporal Censoring** | Volume counts, censoring reasons, visual mask (if enabled) |
| **Connectivity** | For each measure: matrix heatmap, connectome glass brain, value histogram |
| **References** | Relevant citations for methods used |

---

## Common Workflows

### Workflow 1: Basic Resting-State Analysis

```bash
# 1. Run participant-level connectivity analysis
connectomix /path/to/fmridenoiser_output /data/output participant \
  -c participant_config.yaml -v

# 2. Check HTML reports for quality assurance
ls /data/output/sub-*/*.html
```

### Workflow 2: Task-Based Connectivity

```bash
# Compute connectivity for each condition
connectomix /path/to/fmridenoiser_output /data/output participant \
  -t faces \
  --conditions face house scrambled \
  --fd-threshold 0.5 \
  -v
```


---

## Troubleshooting

### "No functional files found"
Check your BIDS entity filters. Use `-v` to see query details.

### "Confound not found"
Check fMRIPrep's confounds TSV columns. Use `--denoising minimal` for basic motion parameters, or use wildcards (e.g., `a_comp_cor_*`) to match multiple components.

### "Too few volumes after censoring"
Relax your censoring thresholds (e.g., increase `--fd-threshold`).

### "Geometric consistency check failed"
Connectomix will automatically resample if subjects have different geometries.

---

## Tips and Best Practices

1. **Start small**: Test with 1-2 subjects before full dataset
2. **Use verbose mode** (`-v`) when debugging
3. **Check HTML reports** for quality assurance

---

## Configuration Reference

### Participant-Level Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `subject` | list | null | Subject IDs (without "sub-") |
| `tasks` | list | null | Task names |
| `sessions` | list | null | Session IDs |
| `runs` | list | null | Run numbers |
| `spaces` | list | null | MNI spaces |
| `method` | string | "roiToRoi" | Analysis method |
| `confounds` | list | [6 motion] | Confound columns (supports wildcards: `*`, `?`) |
| `high_pass` | float | 0.01 | High-pass cutoff (Hz) |
| `low_pass` | float | 0.08 | Low-pass cutoff (Hz) |
| `seeds_file` | path | null | Seeds TSV file |
| `radius` | float | 5.0 | Seed sphere radius (mm) |
| `atlas` | string | "schaefer2018n100" | Atlas name |
| `connectivity_kind` | string | "correlation" | Connectivity measure |

---

## Getting Help

```bash
# Check version
connectomix --version

# Get help
connectomix --help
```

**Links:**
- [GitHub Repository](https://github.com/ln2t/connectomix)
- [Report Issues](https://github.com/ln2t/connectomix/issues)

---

## Citation

If you use Connectomix in your research, please refer to the [GitHub repository](https://github.com/ln2t/connectomix).

---

## Acknowledgments

Connectomix is built on [Nilearn](https://nilearn.github.io/), a powerful Python library for analyzing neuroimaging data. For questions about connectivity measures and neuroimaging analysis, refer to the [Nilearn documentation](https://nilearn.github.io/).

---

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0). See [LICENSE](LICENSE) for details.
