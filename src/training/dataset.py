"""Compatibility entry point for promption.training.dataset."""
from importlib import import_module
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if __name__ == "__main__":
    runpy.run_module("promption.training.dataset", run_name="__main__")
else:
    sys.modules[__name__] = import_module("promption.training.dataset")
