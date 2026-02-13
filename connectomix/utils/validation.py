"""Input validation functions."""

from pathlib import Path
from typing import Any, List, Optional


def validate_alpha(value: float, name: str = "alpha") -> None:
    """Validate alpha value is in [0, 1].
    
    Args:
        value: Value to validate
        name: Parameter name for error message
    
    Raises:
        ValueError: If value is not in valid range
    """
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {type(value).__name__}")
    
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1, got {value}")


def validate_positive(value: float, name: str = "value") -> None:
    """Validate value is positive.
    
    Args:
        value: Value to validate
        name: Parameter name for error message
    
    Raises:
        ValueError: If value is not positive
    """
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {type(value).__name__}")
    
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")


def validate_non_negative(value: float, name: str = "value") -> None:
    """Validate value is non-negative.
    
    Args:
        value: Value to validate
        name: Parameter name for error message
    
    Raises:
        ValueError: If value is negative
    """
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {type(value).__name__}")
    
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")


def validate_file_exists(path: Path, name: str = "file") -> None:
    """Validate file exists.
    
    Args:
        path: Path to validate
        name: Parameter name for error message
    
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If path is not a file
    """
    if not isinstance(path, Path):
        path = Path(path)
    
    if not path.exists():
        raise FileNotFoundError(f"{name} not found: {path}")
    
    if not path.is_file():
        raise ValueError(f"{name} is not a file: {path}")


def validate_dir_exists(path: Path, name: str = "directory") -> None:
    """Validate directory exists.
    
    Args:
        path: Path to validate
        name: Parameter name for error message
    
    Raises:
        FileNotFoundError: If directory doesn't exist
        ValueError: If path is not a directory
    """
    if not isinstance(path, Path):
        path = Path(path)
    
    if not path.exists():
        raise FileNotFoundError(f"{name} not found: {path}")
    
    if not path.is_dir():
        raise ValueError(f"{name} is not a directory: {path}")


def validate_choice(
    value: Any,
    choices: List[Any],
    name: str = "parameter"
) -> None:
    """Validate value is in allowed choices.
    
    Args:
        value: Value to validate
        choices: List of allowed values
        name: Parameter name for error message
    
    Raises:
        ValueError: If value not in choices
    """
    if value not in choices:
        raise ValueError(
            f"{name} must be one of {choices}, got '{value}'"
        )


def validate_list_not_empty(
    value: List[Any],
    name: str = "list"
) -> None:
    """Validate list is not empty.
    
    Args:
        value: List to validate
        name: Parameter name for error message
    
    Raises:
        ValueError: If list is empty
    """
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list, got {type(value).__name__}")
    
    if len(value) == 0:
        raise ValueError(f"{name} cannot be empty")


def validate_string_not_empty(
    value: str,
    name: str = "string"
) -> None:
    """Validate string is not empty.
    
    Args:
        value: String to validate
        name: Parameter name for error message
    
    Raises:
        ValueError: If string is empty
    """
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}")
    
    if len(value.strip()) == 0:
        raise ValueError(f"{name} cannot be empty")


def sanitize_filename(value: str) -> str:
    """Sanitize a string for use in filenames.
    
    Replaces problematic characters that can cause issues in filenames:
    - Spaces → underscores
    - Forward slashes → underscores
    - Backslashes → underscores
    - Colons → removed (common in timestamps)
    - Other special characters → removed or replaced
    
    This ensures filenames are compatible across all operating systems
    and don't contain characters that interfere with BIDS filename parsing.
    
    Args:
        value: String to sanitize
    
    Returns:
        Sanitized string safe for use in filenames
    
    Example:
        >>> sanitize_filename("7Networks DMN: PCC")
        '7Networks_DMN_PCC'
    """
    if not isinstance(value, str):
        return str(value)
    
    # Replace spaces with underscores
    value = value.replace(' ', '_')
    
    # Replace path separators with underscores
    value = value.replace('/', '_').replace('\\', '_')
    
    # Remove colons (common in timestamps)
    value = value.replace(':', '')
    
    # Remove other problematic characters but keep alphanumeric, underscores, and hyphens
    # This preserves BIDS-style entity names like "7Networks_DMN_PCC"
    sanitized = ""
    for char in value:
        if char.isalnum() or char in ('_', '-', '.'):
            sanitized += char
    
    # Clean up multiple consecutive underscores
    while '__' in sanitized:
        sanitized = sanitized.replace('__', '_')
    
    # Remove leading/trailing underscores/hyphens
    sanitized = sanitized.strip('_-')
    
    return sanitized
