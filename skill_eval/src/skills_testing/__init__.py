"""skills_testing package metadata."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("amd-skills-test")
except PackageNotFoundError:
    __version__ = "0.1.0.dev0"
