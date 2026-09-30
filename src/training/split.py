"""Compatibility alias for promption.training.split."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.training.split")
