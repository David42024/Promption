"""Compatibility alias for promption.utils.structured_logger."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.utils.structured_logger")
