"""Compatibility alias for promption.utils.audio_transcriber."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.utils.audio_transcriber")
