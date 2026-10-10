#!/usr/bin/env python3
"""Check local documentation links and GitHub Issue Form structure."""

from pathlib import Path
import re
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]


def main():
    forms = list((ROOT / ".github/ISSUE_TEMPLATE").glob("[0-9]*.yml"))
    assert len(forms) == 7, "Expected seven application forms"
    for path in forms:
        form = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert form["name"] and form["description"] and form["title"], path
        identifiers = set()
        for field in form["body"]:
            assert field["type"] in {"markdown", "input", "textarea", "dropdown", "checkboxes"}, path
            if field["type"] == "markdown":
                assert field["attributes"]["value"], path
                continue
            assert field["id"] not in identifiers, path
            identifiers.add(field["id"])
            assert field["attributes"]["label"], path
            if field["type"] in {"dropdown", "checkboxes"}:
                assert field["attributes"]["options"], path
    for path in ROOT.rglob("*.md"):
        if any(part in {".git", ".venv", ".scratch", "output"} for part in path.relative_to(ROOT).parts):
            continue
        for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", path.read_text(encoding="utf-8")):
            if ":" in target or target.startswith("#"):
                continue
            destination = (path.parent / target.split("#", 1)[0]).resolve()
            assert destination.is_relative_to(ROOT) and destination.exists(), f"{path}: {target}"
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        yaml.safe_load(path.read_text(encoding="utf-8"))
    print("Seven forms, workflow YAML and local documentation links passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
