"""Authentication module.

Handles user authentication and security credentials validation.
"""
from whitespace_tool.auth.services import authenticate
from whitespace_tool.auth.routes import handle_auth_post

__all__ = ["authenticate", "handle_auth_post"]

