#!/usr/bin/env python3
"""Administrator-operated inventory ledger and generated public views."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import html
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
PREFIXES = {"location": "LOC", "item": "ITM", "object": None, "record": "EVT"}
DIRECTORIES = {"location": "locations", "item": "items", "object": "objects", "record": "records"}
OPERATIONS = {
    "receive", "loan", "return", "consume", "transfer",
    "hold", "release", "writeoff", "adjust-in", "adjust-out",
}
FIELDS = {
    "location": {"id", "name", "parent", "description", "storage"},
    "item": {"id", "name", "category", "unit", "model", "storage_requirements"},
    "object": {"id", "name", "item", "serial_number", "batch", "expires_on", "notes"},
    "record": {
        "id", "type", "object", "quantity", "occurred_at", "issue", "operation_key",
        "administrator", "reason", "location", "destination", "borrower", "due_on",
        "loan", "corrects",
    },
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def username(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", value)


def positive_int(value):
    return type(value) is int and value > 0


def load(root):
    data = {
        "categories": read_json(root / "catalogs/categories.json"),
        "units": read_json(root / "catalogs/units.json"),
        "administrators": read_json(root / "catalogs/administrators.json"),
    }
    for kind, directory in DIRECTORIES.items():
        entries = {}
        for path in sorted((root / directory).rglob("*.json")):
            entry = read_json(path)
            require(isinstance(entry, dict), f"{path}: expected an object")
            identifier = entry.get("id")
            require(isinstance(identifier, str), f"{path}: missing id")
            require(path.stem == identifier, f"{path}: filename must match id")
            require(identifier not in entries, f"Duplicate id: {identifier}")
            if kind == "record":
                try:
                    occurred = datetime.fromisoformat(entry["occurred_at"])
                except (KeyError, TypeError, ValueError):
                    raise ValueError(f"{identifier}: invalid occurred_at") from None
                require(path.parent == root / directory / occurred.strftime("%Y/%m"),
                        f"{identifier}: record must be filed by actual year/month")
            entries[identifier] = entry
        data[kind] = entries
    return data


def validate(data):
    categories = data["categories"]
    require(isinstance(categories, list), "Categories must be a list")
    category_map = {}
    for category in categories:
        require(isinstance(category, dict), "Invalid category")
        identifier = category.get("id")
        require(isinstance(identifier, str) and re.fullmatch(r"[a-z][a-z0-9-]*", identifier),
                "Invalid category id")
        require(identifier not in category_map, f"Duplicate category: {identifier}")
        require(category.get("kind") in {"asset", "batch"} and category.get("name"),
                f"{identifier}: invalid category")
        category_map[identifier] = category
    require(isinstance(data["units"], list) and all(isinstance(unit, str) and unit for unit in data["units"]),
            "Units must be nonempty strings")
    require(len(set(data["units"])) == len(data["units"]), "Duplicate units")
    admins = data["administrators"]
    require(isinstance(admins, list) and all(username(admin) for admin in admins),
            "Administrators must be GitHub usernames")
    require(len({admin.lower() for admin in admins}) == len(admins), "Duplicate administrators")

    for kind in DIRECTORIES:
        for identifier, entry in data[kind].items():
            require(not set(entry) - FIELDS[kind], f"{identifier}: unsupported fields")
            prefix = PREFIXES[kind] or ("AST" if identifier.startswith("AST-") else "BAT")
            require(re.fullmatch(rf"{prefix}-[0-9]{{6}}", identifier) and int(identifier[4:]) > 0,
                    f"Invalid id: {identifier}")
            if kind != "record":
                require(isinstance(entry.get("name"), str) and entry["name"].strip(),
                        f"{identifier}: missing name")

    locations = data["location"]
    for identifier, location in locations.items():
        require(type(location.get("storage")) is bool and isinstance(location.get("description"), str),
                f"{identifier}: storage and description required")
        visited = {identifier}
        parent = location.get("parent")
        while parent is not None:
            require(isinstance(parent, str) and parent in locations, f"{identifier}: unknown parent")
            require(parent not in visited, f"{identifier}: cyclic location")
            visited.add(parent)
            parent = locations[parent].get("parent")

    items = data["item"]
    for identifier, item in items.items():
        require(item.get("category") in category_map, f"{identifier}: unknown category")
        require(item.get("unit") in data["units"], f"{identifier}: unknown unit")
    objects = data["object"]
    for identifier, obj in objects.items():
        require(obj.get("item") in items, f"{identifier}: unknown item")
        item = items[obj["item"]]
        prefix = "AST" if category_map[item["category"]]["kind"] == "asset" else "BAT"
        require(identifier.startswith(prefix + "-"), f"{identifier}: category/type mismatch")
        if item["category"] == "food":
            try:
                date.fromisoformat(obj["expires_on"])
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"{identifier}: valid expires_on required") from None

    balances = defaultdict(int)
    loans = {}
    held = set()
    operation_keys = set()
    for identifier, event in sorted(data["record"].items()):
        if "corrects" in event:
            require(isinstance(event["corrects"], str) and event["corrects"] in data["record"] and
                    event["corrects"] < identifier, f"{identifier}: previous correction reference required")
        operation = event.get("type")
        obj_id = event.get("object")
        require(operation in OPERATIONS and obj_id in objects, f"{identifier}: unknown operation/object")
        quantity = event.get("quantity")
        require(positive_int(quantity), f"{identifier}: quantity must be a positive integer")
        require(isinstance(event.get("administrator"), str) and
                event["administrator"].lower() in {admin.lower() for admin in admins},
                f"{identifier}: unknown administrator")
        require(positive_int(event.get("issue")), f"{identifier}: positive issue number required")
        operation_key = event.get("operation_key")
        require(isinstance(operation_key, str) and re.fullmatch(r"[a-z0-9-]+", operation_key),
                f"{identifier}: invalid operation_key")
        key = (event["issue"], operation_key)
        require(key not in operation_keys, f"{identifier}: duplicate issue/operation_key")
        operation_keys.add(key)
        require(isinstance(event.get("reason"), str) and event["reason"].strip(),
                f"{identifier}: reason required")
        try:
            occurred = datetime.fromisoformat(event["occurred_at"])
            require(occurred.tzinfo is not None, f"{identifier}: explicit timezone required")
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{identifier}: valid zoned occurred_at required") from None
        asset = obj_id.startswith("AST-")
        require(not asset or quantity == 1, f"{identifier}: asset quantity must be 1")
        if operation in {"hold", "release"}:
            require(quantity == 1, f"{identifier}: hold/release uses quantity 1 for the whole object")
            if operation == "hold":
                require(obj_id not in held, f"{identifier}: object already held")
                held.add(obj_id)
            else:
                require(obj_id in held, f"{identifier}: object is not held")
                held.remove(obj_id)
            continue
        location = event.get("location")
        require(location in locations and locations[location]["storage"],
                f"{identifier}: valid storage location required")
        balance_key = (obj_id, location)
        if operation in {"loan", "consume", "transfer"}:
            require(obj_id not in held, f"{identifier}: object is held")
            expiry = objects[obj_id].get("expires_on")
            require(not expiry or date.fromisoformat(expiry) >= occurred.date(),
                    f"{identifier}: expired food cannot be issued normally")
        if operation in {"receive", "adjust-in", "return"}:
            if operation == "return":
                original = event.get("loan")
                require(original in loans and loans[original]["object"] == obj_id,
                        f"{identifier}: original loan required")
                require(loans[original]["remaining"] >= quantity, f"{identifier}: excess return")
                require(occurred >= loans[original]["occurred_at"],
                        f"{identifier}: return before original loan")
                loans[original]["remaining"] -= quantity
            balances[balance_key] += quantity
        elif operation == "transfer":
            destination = event.get("destination")
            require(destination in locations and locations[destination]["storage"] and destination != location,
                    f"{identifier}: different valid destination required")
            balances[balance_key] -= quantity
            balances[(obj_id, destination)] += quantity
        else:
            require(operation != "consume" or not asset, f"{identifier}: assets cannot be consumed")
            balances[balance_key] -= quantity
            if operation == "loan":
                require(asset and username(event.get("borrower")), f"{identifier}: asset and borrower required")
                try:
                    due = date.fromisoformat(event["due_on"])
                except (KeyError, TypeError, ValueError):
                    raise ValueError(f"{identifier}: valid due_on required") from None
                require(due >= occurred.date(), f"{identifier}: due date before loan")
                loans[identifier] = {
                    "object": obj_id, "borrower": event["borrower"], "due_on": event["due_on"],
                    "remaining": quantity, "issue": event["issue"], "occurred_at": occurred,
                }
        require(balances[balance_key] >= 0, f"{identifier}: negative inventory")
        if asset:
            total = sum(value for (object_id, _), value in balances.items() if object_id == obj_id)
            total += sum(loan["remaining"] for loan in loans.values() if loan["object"] == obj_id)
            require(total <= 1, f"{identifier}: asset exists more than once")
    return balances, loans, held


def cell(value):
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ")


def render(data, state):
    balances, loans, held = state
    lines = ["# 查询台账", "", "> 由管理员工具生成，不手工修改。", "",
             "余额包含隔离库存，隔离对象不可正常领用。归还仅在管理员检查后记账。",
             "", "## 库存与资产", "",
             "| 编号 | 名称 | 完整位置 | 数量 | 基本单位 | 到期日期 | 状态 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for (identifier, location), quantity in sorted(balances.items()):
        if quantity == 0:
            continue
        chain = []
        current = location
        while current is not None:
            entry = data["location"][current]
            chain.append(entry["name"])
            current = entry.get("parent")
        obj = data["object"][identifier]
        item = data["item"][obj["item"]]
        row = [identifier, obj["name"], " / ".join(reversed(chain)), quantity,
               item["unit"], obj.get("expires_on", ""), "held" if identifier in held else "in-stock"]
        lines.append("| " + " | ".join(map(cell, row)) + " |")
    lines += ["", "## 未结借用", "", "| 借出记录 | 对象 | 借用人 | 数量 | 预计归还 | 申请 |",
              "| --- | --- | --- | --- | --- | --- |"]
    for identifier, loan in sorted(loans.items()):
        if loan["remaining"]:
            row = [identifier, loan["object"], loan["borrower"], loan["remaining"],
                   loan["due_on"], f"#{loan['issue']}"]
            lines.append("| " + " | ".join(map(cell, row)) + " |")
    lines += ["", "归还待检查、待补充和待审核的申请请查看 Issues；本表只包含已登记的事实。", ""]
    return "\n".join(lines)


def add(root, kind, draft_path):
    data = load(root)
    validate(data)
    draft = read_json(draft_path)
    require(isinstance(draft, dict) and "id" not in draft, "Draft must be an object without id")
    prefix = PREFIXES[kind]
    if kind == "object":
        require(draft.get("item") in data["item"], "Unknown item")
        category_id = data["item"][draft["item"]]["category"]
        category = next(entry for entry in data["categories"] if entry["id"] == category_id)
        prefix = "AST" if category["kind"] == "asset" else "BAT"
    numbers = [int(identifier[4:]) for identifier in data[kind] if identifier.startswith(prefix + "-")]
    next_number = max(numbers, default=0) + 1
    require(next_number <= 999999, "Identifier range exhausted")
    identifier = f"{prefix}-{next_number:06d}"
    draft["id"] = identifier
    data[kind][identifier] = draft
    validate(data)
    directory = root / DIRECTORIES[kind]
    if kind == "item":
        directory /= draft["category"]
    elif kind == "object":
        directory /= data["item"][draft["item"]]["category"]
        if prefix == "BAT":
            directory /= str(datetime.now(timezone(timedelta(hours=8))).year)
    elif kind == "record":
        directory /= datetime.fromisoformat(draft["occurred_at"]).strftime("%Y/%m")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{identifier}.json"
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(draft, ensure_ascii=False, indent=2) + "\n")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("check")
    subcommands.add_parser("build")
    command = subcommands.add_parser("add")
    command.add_argument("kind", choices=PREFIXES)
    command.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "add":
            print(add(args.root, args.kind, args.input))
        else:
            data = load(args.root)
            state = validate(data)
            if args.command == "build":
                output = args.root / "views/README.md"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(render(data, state), encoding="utf-8")
                print(f"Generated {output}")
            else:
                print("Inventory validation passed.")
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
