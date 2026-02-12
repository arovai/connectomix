"""Command-line interface for Connectomix."""

import argparse
import sys
import textwrap
from pathlib import Path
from connectomix.core.version import __version__


# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


class ColoredHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom formatter with colored output and better organization."""
    
    def __init__(self, prog, indent_increment=2, max_help_position=40, width=100):
        super().__init__(prog, indent_increment, max_help_position, width)
    
    def _format_usage(self, usage, actions, groups, prefix):
        if prefix is None:
            prefix = f'{Colors.BOLD}Usage:{Colors.END} '
        return super()._format_usage(usage, actions, groups, prefix)
    
    def start_section(self, heading):
        # Add color to section headings
        if heading:
            heading = f'{Colors.BOLD}{Colors.CYAN}{heading}{Colors.END}'
        super().start_section(heading)


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser.
    
    Returns:
        Configured ArgumentParser instance with detailed help.
    """
    
    # Detailed description
    description = textwrap.dedent(f"""
    {Colors.BOLD}{Colors.GREEN}╔══════════════════════════════════════════════════════════════════════════════╗
    ║                              CONNECTOMIX v{__version__}                              ║
    ║      Functional Connectivity Analysis from fmridenoiser Outputs           ║
    ╚══════════════════════════════════════════════════════════════════════════════╝{Colors.END}
    
    {Colors.BOLD}Description:{Colors.END}
      Connectomix performs functional connectivity analysis on pre-denoised fMRI data.
      It supports multiple connectivity methods at the participant level.
      Input data must be pre-denoised (e.g., from fmridenoiser or similar denoising pipeline).
    
    {Colors.BOLD}Connectivity Methods:{Colors.END}
      • {Colors.CYAN}seed-to-voxel{Colors.END}  - Correlation between seed regions and all brain voxels
      • {Colors.CYAN}roi-to-voxel{Colors.END}   - Correlation between atlas ROIs and all brain voxels
      • {Colors.CYAN}seed-to-seed{Colors.END}   - Correlation matrix between user-defined seeds
      • {Colors.CYAN}roi-to-roi{Colors.END}     - Correlation matrix between atlas regions
    
    {Colors.BOLD}Note:{Colors.END}
      Group-level analysis is under development and not yet available for use.
    """)
    
    # Detailed epilog with examples
    epilog = textwrap.dedent(f"""
    {Colors.BOLD}{Colors.GREEN}═══════════════════════════════════════════════════════════════════════════════{Colors.END}
    {Colors.BOLD}EXAMPLES{Colors.END}
    {Colors.GREEN}═══════════════════════════════════════════════════════════════════════════════{Colors.END}
    
    {Colors.BOLD}Basic Usage (Recommended):{Colors.END}
    
      {Colors.YELLOW}# Specify denoised derivatives location (recommended approach){Colors.END}
      connectomix /data/bids /data/output participant \
          --derivatives fmridenoiser=/path/to/fmridenoiser
    
      {Colors.YELLOW}# Alternative: Use denoised output directory directly{Colors.END}
      connectomix /data/denoised_output /data/output participant
    
    {Colors.BOLD}With Configuration File:{Colors.END}
    
      {Colors.YELLOW}# Use a YAML or JSON configuration file{Colors.END}
      connectomix /data/bids /data/output participant --config analysis_config.yaml
    
    {Colors.BOLD}Filtering Subjects/Sessions:{Colors.END}
    
      {Colors.YELLOW}# Process only subject 01 (with --derivatives approach){Colors.END}
      connectomix /data/bids /data/output participant \
          --derivatives fmridenoiser=/path/to/fmridenoiser \
          --participant-label 01
    
      {Colors.YELLOW}# Process specific task, session, and run{Colors.END}
      connectomix /data/bids /data/output participant \\
          --participant-label 01 \\
          --task restingstate \\
          --session 1 \\
          --run 1
    
      {Colors.YELLOW}# Apply condition-based temporal masking{Colors.END}
      connectomix /data/bids /data/output participant \
          --conditions face house \
          --fd-threshold 0.5
    
    {Colors.BOLD}{Colors.GREEN}═══════════════════════════════════════════════════════════════════════════════{Colors.END}
    {Colors.BOLD}CONFIGURATION FILE{Colors.END}
    {Colors.GREEN}═══════════════════════════════════════════════════════════════════════════════{Colors.END}
    
    Configuration files (YAML or JSON) allow fine-grained control over analysis
    parameters. See documentation for full configuration options.
    
    {Colors.BOLD}Example participant config (YAML):{Colors.END}
    
      method: seed-to-voxel
      seeds_file: /path/to/seeds.tsv
      space: MNI152NLin2009cAsym
      atlas: schaefer2018n200
      alpha: 0.05
    
    {Colors.BOLD}{Colors.GREEN}═══════════════════════════════════════════════════════════════════════════════{Colors.END}
    {Colors.BOLD}OUTPUT STRUCTURE{Colors.END}
    {Colors.GREEN}═══════════════════════════════════════════════════════════════════════════════{Colors.END}
    
    Connectomix outputs are BIDS-compliant derivatives:
    
      output_dir/
      ├── dataset_description.json
      ├── sub-01/
      │   └── func/
      │       ├── sub-01_task-rest_space-MNI_desc-connectivity_bold.nii.gz
      │       └── sub-01_task-rest_space-MNI_desc-connectivity_bold.json
      └── sub-02/
          └── ...
    
    {Colors.BOLD}{Colors.GREEN}═══════════════════════════════════════════════════════════════════════════════{Colors.END}
    {Colors.BOLD}MORE INFORMATION{Colors.END}
    {Colors.GREEN}═══════════════════════════════════════════════════════════════════════════════{Colors.END}
    
      Documentation:  https://github.com/ln2t/connectomix
      Report Issues:  https://github.com/ln2t/connectomix/issues
      Version:        {__version__}
    """)
    
    parser = argparse.ArgumentParser(
        prog="connectomix",
        description=description,
        epilog=epilog,
        formatter_class=ColoredHelpFormatter,
        add_help=False,  # We'll add custom help
    )
    
    # =========================================================================
    # REQUIRED ARGUMENTS
    # =========================================================================
    required = parser.add_argument_group(
        f'{Colors.BOLD}Required Arguments{Colors.END}'
    )
    
    required.add_argument(
        "bids_dir",
        type=Path,
        metavar="BIDS_DIR",
        help="Path to the BIDS dataset root directory. Must contain a valid "
             "dataset_description.json file.",
    )
    
    required.add_argument(
        "output_dir",
        type=Path,
        metavar="OUTPUT_DIR",
        help="Path to output directory where Connectomix derivatives will be "
             "stored. Will be created if it does not exist.",
    )
    
    required.add_argument(
        "analysis_level",
        choices=["participant"],
        metavar="{participant}",
        help="Analysis level to perform. Currently only 'participant'-level "
             "processing is available (first-level analysis).",
    )
    
    # =========================================================================
    # OPTIONAL ARGUMENTS - General
    # =========================================================================
    general = parser.add_argument_group(
        f'{Colors.BOLD}General Options{Colors.END}'
    )
    
    general.add_argument(
        "-h", "--help",
        action="help",
        default=argparse.SUPPRESS,
        help="Show this help message and exit.",
    )
    
    general.add_argument(
        "--version",
        action="version",
        version=f"connectomix {__version__}",
        help="Show program version and exit.",
    )
    
    general.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output (DEBUG level logging). Useful for "
             "troubleshooting.",
    )
    
    general.add_argument(
        "-c", "--config",
        type=Path,
        metavar="FILE",
        help="Path to configuration file (.json, .yaml, or .yml). Configuration "
             "files allow detailed control over analysis parameters. Command-line "
             "arguments override config file settings.",
    )
    
    # =========================================================================
    # OPTIONAL ARGUMENTS - Derivatives
    # =========================================================================
    derivatives = parser.add_argument_group(
        f'{Colors.BOLD}Derivatives Options{Colors.END}'
    )
    
    derivatives.add_argument(
        "-d", "--derivatives",
        action="append",
        metavar="NAME=PATH",
        dest="derivatives",
        help="Specify location of denoised derivatives. Format: name=path "
             "(e.g., fmridenoiser=/data/fmridenoiser). "
             "Use this flag if denoised outputs are in non-standard locations.",
    )
    
    # =========================================================================
    # OPTIONAL ARGUMENTS - BIDS Filters
    # =========================================================================
    filters = parser.add_argument_group(
        f'{Colors.BOLD}BIDS Entity Filters{Colors.END}',
        "Filter which data to process based on BIDS entities. "
        "Useful for processing subsets of data."
    )
    
    filters.add_argument(
        "-p", "--participant-label",
        metavar="LABEL",
        dest="participant_label",
        nargs='+',
        help="Process one or more participants. Specify without 'sub-' prefix "
             "(e.g., '01' or '01 02 03', not 'sub-01'). Can be multiple labels.",
    )
    
    filters.add_argument(
        "-t", "--task",
        metavar="TASK",
        help="Process only this task (e.g., 'restingstate', 'nback'). "
             "Specify without 'task-' prefix.",
    )
    
    filters.add_argument(
        "-s", "--session",
        metavar="SESSION",
        help="Process only this session (e.g., '1', 'pre', 'post'). "
             "Specify without 'ses-' prefix.",
    )
    
    filters.add_argument(
        "-r", "--run",
        metavar="RUN",
        type=int,
        help="Process only this run number (e.g., 1, 2).",
    )
    
    filters.add_argument(
        "--space",
        metavar="SPACE",
        help="Process only data in this template space "
             "(e.g., 'MNI152NLin2009cAsym', 'MNI152NLin6Asym'). "
             "Must match the space of denoised input data.",
    )
    
    filters.add_argument(
        "--label",
        metavar="STRING",
        help="Add a custom label to ALL output filenames as a BIDS-style entity "
             "(e.g., --label myanalysis will add 'label-myanalysis' to filenames). "
             "Useful for distinguishing different analysis runs.",
    )
    
    # =========================================================================
    # OPTIONAL ARGUMENTS - Temporal Censoring
    # =========================================================================
    censoring = parser.add_argument_group(
        f'{Colors.BOLD}Condition-Based Masking (Task fMRI){Colors.END}',
        "Select specific timepoints based on experimental conditions. Available for task fMRI."
    )
    
    censoring.add_argument(
        "--conditions",
        metavar="COND",
        nargs="+",
        help="Enable condition-based censoring for task fMRI. "
             "Specify one or more condition names from the events.tsv file. "
             "A separate connectivity matrix will be computed for each condition. "
             "Use 'baseline' to select inter-trial intervals (timepoints not in any task). "
             "Example: --conditions face house  OR  --conditions baseline",
    )
    
    censoring.add_argument(
        "--events-file",
        metavar="FILE",
        dest="events_file",
        help="Path to events.tsv file (default: auto-detect from BIDS). "
             "Only used with --conditions.",
    )
    
    censoring.add_argument(
        "--include-baseline",
        action="store_true",
        dest="include_baseline",
        help="When using --conditions, also compute connectivity for baseline "
             "(timepoints not in any condition). Equivalent to adding 'baseline' to --conditions.",
    )
    
    censoring.add_argument(
        "--transition-buffer",
        metavar="SEC",
        type=float,
        dest="transition_buffer",
        default=0.0,
        help="Seconds to exclude around condition boundaries (default: 0). "
             "Accounts for hemodynamic response lag.",
    )
    

    
    # =========================================================================
    # OPTIONAL ARGUMENTS - Analysis Method & Atlas
    # =========================================================================
    analysis_opts = parser.add_argument_group(
        f'{Colors.BOLD}Analysis Options{Colors.END}',
        "Connectivity method and atlas selection."
    )
    
    analysis_opts.add_argument(
        "--atlas",
        metavar="ATLAS",
        help="Atlas for ROI-to-ROI connectivity. "
             "Available: schaefer2018n100, schaefer2018n200, aal, harvardoxford. "
             "Default: schaefer2018n100.",
    )
    
    analysis_opts.add_argument(
        "--method",
        metavar="METHOD",
        choices=["seedToVoxel", "roiToVoxel", "seedToSeed", "roiToRoi"],
        help="Connectivity method. "
             "Choices: %(choices)s. Default: roiToRoi.",
    )
    
    return parser


def parse_derivatives_arg(derivatives_list: list) -> dict:
    """Parse derivatives arguments into dictionary.
    
    Args:
        derivatives_list: List of strings in format "name=path"
    
    Returns:
        Dictionary mapping derivative names to paths
    
    Raises:
        ValueError: If derivative argument format is invalid
    """
    if not derivatives_list:
        return {}
    
    derivatives_dict = {}
    for derivative_arg in derivatives_list:
        if "=" not in derivative_arg:
            raise ValueError(
                f"Invalid derivatives argument: {derivative_arg}. "
                f"Expected format: name=path (e.g., fmriprep=/path/to/fmriprep)"
            )
        
        name, path = derivative_arg.split("=", 1)
        derivatives_dict[name] = Path(path)
    
    return derivatives_dict
