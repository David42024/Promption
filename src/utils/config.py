"""Compatibility alias for promption.utils.config."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.utils.config")
