"""Configuration loading and validation for Connectomix."""

from connectomix.config.defaults import ParticipantConfig, GroupConfig, ConditionMaskingConfig
from connectomix.config.loader import load_config_file, merge_configs, config_from_dict
from connectomix.config.validator import ConfigValidator

__all__ = [
    "ParticipantConfig",
    "GroupConfig",
    "ConditionMaskingConfig",
    "load_config_file",
    "merge_configs",
    "config_from_dict",
    "ConfigValidator",
]
