"""Compatibility alias for promption.api.routes."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.api.routes")
