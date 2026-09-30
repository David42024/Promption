"""Compatibility alias for promption.llm.openai_client."""
from importlib import import_module
import sys

sys.modules[__name__] = import_module("promption.llm.openai_client")
