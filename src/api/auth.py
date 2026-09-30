"""Compatibility alias for promption.api.auth."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.api.auth")
