"""Compatibility alias for promption.utils.visualizer."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.utils.visualizer")
