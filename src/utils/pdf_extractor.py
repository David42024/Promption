"""Compatibility alias for promption.utils.pdf_extractor."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.utils.pdf_extractor")
