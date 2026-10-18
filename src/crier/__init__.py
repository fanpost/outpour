"""Crier - Cross-post your content to dev.to, Hashnode, Medium, and more."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("crier")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"  # only hit if package metadata is missing
