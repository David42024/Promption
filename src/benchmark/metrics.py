"""Compatibility alias for promption.benchmark.metrics."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.benchmark.metrics")
