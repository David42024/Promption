"""Compatibility alias for promption.api.models."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.api.models")
