"""Main entry point for Connectomix."""

import sys
import logging
from pathlib import Path

from connectomix.cli import create_parser, parse_derivatives_arg
from connectomix.utils.logging import setup_logging
from connectomix.config.defaults import (
    ParticipantConfig,
    GroupConfig,
)
from connectomix.config.loader import load_config_file
from connectomix.core.participant import run_participant_pipeline
from connectomix.core.group import run_group_pipeline
from connectomix.core.version import __version__


def main():
    """Main entry point for Connectomix.
    
    Parses command-line arguments and runs the appropriate pipeline
    (participant-level or group-level analysis).
    """
    # Parse arguments
    parser = create_parser()
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(verbose=args.verbose)
    
    # Print header
    logger.info("=" * 60)
    logger.info(f"Connectomix v{__version__}")
    logger.info(f"Analysis level: {args.analysis_level}")
    logger.info("=" * 60)
    
    try:
        # Parse derivatives argument
        derivatives_dict = parse_derivatives_arg(args.derivatives)
        
        # Run appropriate pipeline
        if args.analysis_level == "participant":
            # Load or create participant config
            if args.config:
                logger.info(f"Loading configuration from: {args.config}")
                config_dict = load_config_file(args.config)
                config = ParticipantConfig(**config_dict)
            else:
                logger.info("Using default configuration")
                config = ParticipantConfig()
            
            # Get participant labels to process (convert to list if needed)
            participant_labels = args.participant_label if args.participant_label else [None]
            
            # Loop over each participant label
            for participant_label in participant_labels:
                # Create fresh config for each participant
                if args.config:
                    config_dict = load_config_file(args.config)
                    config = ParticipantConfig(**config_dict)
                else:
                    config = ParticipantConfig()
                
                # Override config with CLI arguments
                if participant_label:
                    config.subject = [participant_label]
                # Note: config uses plural field names for tasks/sessions/runs/spaces
                if args.task:
                    config.tasks = [args.task]
                if args.session:
                    config.sessions = [args.session]
                if args.run:
                    config.runs = [args.run]
                if args.space:
                    config.spaces = [args.space]
                if args.label:
                    config.label = args.label
                if args.atlas:
                    config.atlas = args.atlas
                if args.method:
                    config.method = args.method
                
                # Handle condition-based masking CLI options
                _configure_condition_masking(args, config, logger)
                
                run_participant_pipeline(
                    bids_dir=args.bids_dir,
                    output_dir=args.output_dir,
                    config=config,
                    derivatives=derivatives_dict,
                    logger=logger,
                )
        else:  # group
            # Load or create group config
            if args.config:
                logger.info(f"Loading configuration from: {args.config}")
                config_dict = load_config_file(args.config)
                config = GroupConfig(**config_dict)
            else:
                logger.info("Using default configuration")
                config = GroupConfig()
            
            # Override config with CLI arguments
            if hasattr(args, 'participant_derivatives') and args.participant_derivatives:
                config.participant_derivatives = args.participant_derivatives
            if args.participant_label:
                # For group-level, participant_label is a list of labels
                config.subjects = args.participant_label
            if args.task:
                config.tasks = [args.task]
            if args.session:
                config.sessions = [args.session]
            if hasattr(args, 'atlas') and args.atlas:
                config.atlas = args.atlas
            if hasattr(args, 'method') and args.method:
                config.method = args.method
            if args.label:
                config.label = args.label
            
            run_group_pipeline(
                bids_dir=args.bids_dir,
                output_dir=args.output_dir,
                config=config,
                derivatives=derivatives_dict,
                logger=logger,
            )
        
        logger.info("=" * 60)
        logger.info("Analysis completed successfully!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        if args.verbose:
            logger.exception("Full traceback:")
        sys.exit(1)


def _configure_condition_masking(args, config: ParticipantConfig, logger: logging.Logger):
    """Configure condition-based masking from CLI arguments.
    
    Args:
        args: Parsed CLI arguments.
        config: ParticipantConfig to update.
        logger: Logger instance.
    """
    # Check if condition-based masking is enabled
    has_conditions = hasattr(args, 'conditions') and args.conditions
    
    if not has_conditions:
        return  # No condition-based masking specified
    
    # Enable condition masking
    config.condition_masking.enabled = True
    config.condition_masking.conditions = args.conditions
    logger.info(f"Condition-based masking enabled: {args.conditions}")
    
    if hasattr(args, 'events_file') and args.events_file:
        config.condition_masking.events_file = args.events_file
    
    if hasattr(args, 'include_baseline') and args.include_baseline:
        config.condition_masking.include_baseline = True
        logger.info("  Including baseline periods")
    
    if hasattr(args, 'transition_buffer') and args.transition_buffer > 0:
        config.condition_masking.transition_buffer = args.transition_buffer
        logger.info(f"  Transition buffer: {args.transition_buffer}s")


if __name__ == "__main__":
    main()
