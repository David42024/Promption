"""Compatibility alias for promption.output_guard.detector."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.output_guard.detector")
