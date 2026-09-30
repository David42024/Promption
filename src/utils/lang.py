"""Compatibility alias for promption.utils.lang."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.utils.lang")
