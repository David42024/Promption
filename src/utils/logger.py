"""Compatibility alias for promption.utils.logger."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.utils.logger")
