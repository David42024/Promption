"""Compatibility alias for promption.filter.ml_filter_lightweight."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.filter.ml_filter_lightweight")
