"""Compatibility alias for promption.filter.ensemble_filter."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.filter.ensemble_filter")
