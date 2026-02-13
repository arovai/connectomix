# Connectomix Configuration Examples

This directory contains template configuration files demonstrating how to use Connectomix for different connectivity analyses, with a focus on the new **inline seeds feature** for seed-based methods.

## Files

### Seed-Based Methods with Inline Seeds (Recommended)

- **`seed_to_voxel_inline_seeds.yaml`** - Seed-to-voxel analysis with seeds defined directly in the config
- **`seed_to_seed_inline_seeds.yaml`** - Seed-to-seed analysis with seeds defined directly in the config

### ROI-Based Methods

- **`roi_to_voxel_atlas.yaml`** - ROI-to-voxel analysis with ROIs extracted from a standard atlas by label
- **`roi_to_voxel_masks.yaml`** - ROI-to-voxel analysis with ROIs defined by binary mask files

### Seed-Based Methods with External TSV Files

- **`seed_to_voxel_from_file.yaml`** - Seed-to-voxel analysis loading seeds from external TSV
- **`seeds.tsv`** - Example seeds file (tab-separated format)

### Reference and Comparison

- **`seeds_options_comparison.yaml`** - Detailed comparison of both seeds approaches

## Quick Start

### Option 1: Inline Seeds (Self-Contained Config)

Use inline seeds when you want all parameters in one configuration file:

```bash
# Copy and customize the template
cp seed_to_voxel_inline_seeds.yaml my_analysis.yaml
# Edit my_analysis.yaml with your parameters
connectomix /path/to/bids /path/to/output participant -c my_analysis.yaml
```

**Benefits:**
- Single file contains all analysis parameters
- Easy to version control and share
- No need to manage separate seed files
- Self-documenting configuration

**Best for:**
- Small numbers of seeds (5-20)
- Reproducible research workflows
- Sharing complete analysis pipelines

### Option 2: External TSV File (Split Config)

Use a seeds TSV file when you want to separate seed definitions from other parameters:

```bash
# Copy and customize
cp seed_to_voxel_from_file.yaml my_analysis.yaml
cp seeds.tsv my_seeds.tsv
# Edit both files
connectomix /path/to/bids /path/to/output participant -c my_analysis.yaml
```

**Benefits:**
- Reuse same seed file across multiple analyses
- Keep seed list organized separately
- Easier to manage large seed sets

**Best for:**
- Large numbers of seeds (20+)
- Sharing seed lists with other researchers
- Maintaining seed atlases

## Seed Format

### Inline Seeds (in YAML config)

```yaml
seeds:
  - name: "PCC"           # Seed name (used in output filenames)
    x: 0                  # MNI x coordinate (mm)
    y: -52                # MNI y coordinate (mm)
    z: 18                 # MNI z coordinate (mm)
  
  - name: "mPFC"
    x: 0
    y: 52
    z: 0
```

### TSV File Format

```tsv
name	x	y	z
PCC	0	-52	18
mPFC	0	52	0
LIPL	-45	-70	35
```

**Important:**
- First row is header (name, x, y, z)
- Separator is TAB character (not spaces)
- Coordinates are in MNI space (mm)
- Both formats are functionally equivalent

## ROI-Based Methods

### ROI-to-Voxel Analysis

ROI-to-voxel connectivity correlates a region-of-interest (ROI) with every voxel in the brain. 

**Option 1: ROIs from Atlas Labels (Recommended)**

Extract specific ROI regions from a standard atlas:

```bash
connectomix /path/to/bids /path/to/output participant \
  --config roi_to_voxel_atlas.yaml \
  --derivatives fmridenoiser=/path/to/fmridenoiser
```

**Benefits:**
- Use standard, published atlases
- No need to create/align mask files
- Reproducible and shareable
- Easy label-based specification

**Example configuration:**
```yaml
method: "roiToVoxel"
roi_atlas: "schaefer_100"
roi_label:
  - "7Networks_DMN_PCC"
  - "7Networks_DMN_mPFC"
```

**Available atlases:**
- `schaefer_100`, `schaefer_200`, `schaefer_400` (7 networks)
- `schaefer_100_17`, `schaefer_200_17`, `schaefer_400_17` (17 networks)
- `aal` (Automated Anatomical Labeling, 116 regions)
- `harvard_oxford_cort`, `harvard_oxford_sub` (Harvard-Oxford)
- `destrieux` (FreeSurfer-based, 148 regions)
- `difumo_64`, `difumo_128` (Dictionary-based functional)
- `msdl` (Multi-Subject Dictionary Learning, 39 regions)

**Option 2: ROIs from Binary Mask Files**

Use custom mask files when you have pre-defined ROI regions:

```bash
connectomix /path/to/bids /path/to/output participant \
  --config roi_to_voxel_masks.yaml \
  --derivatives fmridenoiser=/path/to/fmridenoiser
```

**Benefits:**
- Use custom or subject-specific ROIs
- Total control over ROI definition
- Can combine manually-drawn and atlas-based masks

**Example configuration:**
```yaml
method: "roiToVoxel"
roi_masks:
  - "/path/to/my_roi_1.nii.gz"
  - "/path/to/my_roi_2.nii.gz"
```

**Mask file requirements:**
- Binary NIfTI images (.nii or .nii.gz)
- Should be in the same space as functional data
- Values > 0 define the ROI region
- Automatically resampled if needed to match functional image

## Common Parameters

All templates support these common parameters:

| Parameter | Example | Description |
|-----------|---------|-------------|
| `subject` | `["01", "02"]` | Subject IDs to process |
| `tasks` | `["rest"]` | Task names |
| `sessions` | `null` | Session IDs (null = all) |
| `spaces` | `["MNI152NLin2009cAsym"]` | MNI spaces |
| `radius` | `5.0` | Seed sphere radius (mm) |
| `connectivity_kind` | `"correlation"` | Connectivity measure |
| `label` | `null` | Custom output label |

## Temporal Censoring (Optional)

Both templates include optional temporal censoring parameters:

```yaml
condition_masking:
  enabled: false
  # Uncomment and modify for condition-based analysis:
  # events_file: "auto"
  # conditions: ["go", "stop"]
  # transition_buffer: 0.0
  # min_volumes_retained: 50
```

## Usage Examples

### Basic seed-to-voxel with inline seeds

```bash
connectomix /data/bids /data/output participant \
  --config seed_to_voxel_inline_seeds.yaml \
  --derivatives fmridenoiser=/path/to/fmridenoiser
```

### Seed-to-seed for specific subjects

```bash
connectomix /data/bids /data/output participant \
  --config seed_to_seed_inline_seeds.yaml \
  --derivatives fmridenoiser=/path/to/fmridenoiser \
  --participant-label 01 02 03
```

### Using external seeds file

```bash
connectomix /data/bids /data/output participant \
  --config seed_to_voxel_from_file.yaml \
  --derivatives fmridenoiser=/path/to/fmridenoiser
```

### ROI-to-voxel with atlas labels

```bash
connectomix /data/bids /data/output participant \
  --config roi_to_voxel_atlas.yaml \
  --derivatives fmridenoiser=/path/to/fmridenoiser
```

### ROI-to-voxel with mask files

```bash
connectomix /data/bids /data/output participant \
  --config roi_to_voxel_masks.yaml \
  --derivatives fmridenoiser=/path/to/fmridenoiser
```

### Command-line ROI-to-voxel with atlas labels

```bash
connectomix /data/bids /data/output participant \
  --method roiToVoxel \
  --roi-atlas schaefer_100 \
  --roi-label 7Networks_DMN_PCC 7Networks_DMN_mPFC \
  --derivatives fmridenoiser=/path/to/fmridenoiser
```

### Command-line ROI-to-voxel with mask files

```bash
connectomix /data/bids /data/output participant \
  --method roiToVoxel \
  --roi-mask /path/to/putamen.nii.gz /path/to/caudate.nii.gz \
  --roi-label putamen caudate \
  --derivatives fmridenoiser=/path/to/fmridenoiser
```

## Customizing Templates

### Adding Seeds

For inline seeds, simply add more entries to the `seeds:` list:

```yaml
seeds:
  - name: "PCC"
    x: 0
    y: -52
    z: 18
  
  - name: "NewSeed"        # Add new seed
    x: 10
    y: 20
    z: -5
```

### Changing Seed Sphere Radius

Adjust the `radius` parameter (in mm):

```yaml
radius: 8.0     # Larger sphere (default is 5.0)
```

### Filtering Subjects/Sessions

Modify BIDS entity filters:

```yaml
subject: ["01"]                    # Process only subject 01
sessions: ["01", "02"]             # Process only sessions 01 and 02
tasks: ["rest"]                    # Process only resting-state task
```

### Enabling Temporal Censoring

For task-based connectivity, enable condition masking:

```yaml
condition_masking:
  enabled: true
  conditions: ["go", "stop"]       # Analyze these conditions
  transition_buffer: 2.0           # Exclude 2 sec around transitions
  min_volumes_retained: 50         # Require at least 50 volumes per condition
```

## Troubleshooting

### "seeds_file is required"

**Problem:** Config has neither `seeds_file` nor `seeds` defined.

**Solution:** Add either:
```yaml
seeds_file: "seeds.tsv"     # Option A: external file
```
or:
```yaml
seeds:                      # Option B: inline
  - name: "PCC"
    x: 0
    y: -52
    z: 18
```

### "Missing required keys"

**Problem:** A seed is missing the `name`, `x`, `y`, or `z` key.

**Solution:** Ensure all four keys are present:
```yaml
- name: "PCC"    # Required
  x: 0           # Required
  y: -52         # Required
  z: 18          # Required
```

### "coordinate values must be numeric"

**Problem:** Seed coordinates are not numbers.

**Solution:** Use numeric values, not strings:
```yaml
# ✓ Correct
- name: "PCC"
  x: 0
  y: -52
  z: 18

# ✗ Wrong
- name: "PCC"
  x: "zero"
  y: "minus 52"
  z: "eighteen"
```

## More Information

- See [README.md](../README.md) for full documentation
- See [STATUS.md](../STATUS.md) for implementation status
- See [ROADMAP.md](../ROADMAP.md) for planned features
