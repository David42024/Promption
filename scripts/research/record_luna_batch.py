"""Persist returned subagent text without inferring or repairing its decisions."""
import argparse
import json
import sys
from pathlib import Path

from luna_primary import accept, dump, load, verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    verify(directory)
    state = load(directory / "state.json")
    for item in json.load(sys.stdin):
        raw = item["response"]
        if not isinstance(raw, str):
            raise TypeError("Preserve the subagent's returned text as a string")
        path = directory / "responses" / (item["job"] + ".returned.txt")
        path.write_text(raw)
        accept(directory, state, item["job"], path, item["agent"])
        dump(directory / "state.json", state)
        print(item["job"], "recorded")


if __name__ == "__main__":
    main()
