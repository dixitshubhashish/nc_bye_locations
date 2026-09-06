"""Template Library Module.

Manages predefined brand templates, workflow templates catalog, and template version saving.
"""
from whitespace_tool.templates.services import predefined_templates, list_templates, save_template_version
from whitespace_tool.templates.routes import handle_templates_get, handle_templates_post

__all__ = [
    "predefined_templates",
    "list_templates",
    "save_template_version",
    "handle_templates_get",
    "handle_templates_post",
]

