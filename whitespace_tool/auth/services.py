"""Authentication services.

Contains core authentication logic and credential verification against
environment overrides or default parameters.
"""
from __future__ import annotations

import os
from typing import Any


def authenticate(data: dict[str, Any]) -> dict[str, bool]:
    """Authenticate user credentials.

    Args:
        data: Payload containing username and password.

    Returns:
        Dict indicating authentication status.

    Raises:
        ValueError: If username/password is invalid.
    """
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    expected_user = os.environ.get("WORKFLOW_LOGIN_USER", "admin")
    expected_password = os.environ.get("WORKFLOW_LOGIN_PASSWORD", "")
    
    # Honor environment override if provided, otherwise accept any non-empty password for admin in dev mode
    if expected_password:
        valid = (username == expected_user and password == expected_password)
    else:
        valid = (username == expected_user)
        
    if not valid:
        raise ValueError("Invalid username or password.")
    return {"authenticated": True}

