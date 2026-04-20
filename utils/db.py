import re

def validate_sql_identifier(identifier: str) -> None:
    """Validates that an identifier only contains safe characters to prevent SQL injection."""
    if not re.match(r"^[a-zA-Z0-9_]+$", identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}. Only alphanumeric characters and underscores are allowed.")
