"""Prompt template loading.

Prompts live in `.jinja2` files next to this module, never inline in Python.
They are the part of the system most likely to be tuned, and keeping them in
files means a prompt change is reviewable as a prompt change.

Templates are written in English because instruction-following is more
reliable that way, but every user-visible field they ask for (title,
explanation) is required to be Turkish.
"""

from functools import lru_cache

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.config import PROMPTS_DIR


@lru_cache
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(PROMPTS_DIR),
        undefined=StrictUndefined,  # a missing variable is a bug, not a blank
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,  # rendering prompts, not HTML
    )


def render(template_name: str, /, **context: object) -> str:
    """Render `template_name` with `context`."""
    return _environment().get_template(template_name).render(**context)
