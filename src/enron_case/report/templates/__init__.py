"""Document templates with `{{name}}` placeholders, filled by `render.inject`."""

from __future__ import annotations

from importlib import resources


def load_template(name: str) -> str:
    return resources.files(__name__).joinpath(name).read_text(encoding="utf-8")
