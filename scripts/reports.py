#!/usr/bin/env python3
"""Generate read-only administrator reports from the inventory ledger."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import sys

import inventory


def location_path(data, identifier):
    names = []
    current = identifier
    while current is not None:
        entry = data["location"][current]
        names.append(entry["name"])
        current = entry.get("parent")
    return " / ".join(reversed(names))


def collect(data, state, as_of, expiry_days):
    balances, loans, held = state
    overdue = []
    for event_id, loan in sorted(loans.items()):
        due = date.fromisoformat(loan["due_on"])
        if loan["remaining"] and due < as_of:
            overdue.append({
                "loan": event_id, "object": loan["object"],
                "name": data["object"][loan["object"]]["name"],
                "borrower": loan["borrower"], "remaining": loan["remaining"],
                "due_on": loan["due_on"], "issue": loan["issue"],
                "days_overdue": (as_of - due).days,
            })

    expiring = []
    cutoff = as_of + timedelta(days=expiry_days)
    for object_id, obj in sorted(data["object"].items()):
        expires = obj.get("expires_on")
        if not expires or object_id not in {identifier for identifier, _ in balances}:
            continue
        expires_on = date.fromisoformat(expires)
        quantity = sum(quantity for (identifier, _), quantity in balances.items()
                       if identifier == object_id)
        if quantity and expires_on <= cutoff:
            expiring.append({
                "object": object_id, "name": obj["name"], "expires_on": expires,
                "quantity": quantity, "days_remaining": (expires_on - as_of).days,
            })

    held_items = []
    for object_id in sorted(held):
        obj = data["object"][object_id]
        held_items.append({"object": object_id, "name": obj["name"]})

    stock = []
    for (object_id, location), quantity in sorted(balances.items()):
        if quantity:
            stock.append({
                "object": object_id, "name": data["object"][object_id]["name"],
                "location": location, "location_path": location_path(data, location),
                "quantity": quantity,
            })
    return {
        "as_of": as_of.isoformat(),
        "expiry_days": expiry_days,
        "overdue_loans": overdue,
        "expiring_batches": expiring,
        "held_objects": held_items,
        "stock": stock,
    }


def render(report):
    lines = [
        "# 管理提醒报告", "",
        "> 自动生成的只读报告，不会直接修改台账或 Issue。", "",
        f"- 报告日期：{report['as_of']}",
        f"- 临期范围：未来 {report['expiry_days']} 天（含当天）",
        "",
        "## 需要处理",
        "",
        f"- 逾期借用：{len(report['overdue_loans'])} 项",
        f"- 临期或已过期批次：{len(report['expiring_batches'])} 项",
        f"- 隔离待处置对象：{len(report['held_objects'])} 项",
        "",
        "## 逾期借用",
        "",
        "| 借出记录 | 对象 | 借用人 | 未归还数量 | 预计归还 | 逾期天数 | Issue |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for entry in report["overdue_loans"]:
        lines.append("| " + " | ".join([
            entry["loan"], entry["object"], entry["borrower"], str(entry["remaining"]),
            entry["due_on"], str(entry["days_overdue"]),
            f"[#{entry['issue']}](https://github.com/BETA-SDC/inventory/issues/{entry['issue']})",
        ]) + " |")
    if not report["overdue_loans"]:
        lines.append("| - | 无 | - | - | - | - | - |")

    lines += [
        "", "## 临期或已过期批次", "",
        "| 批次 | 名称 | 剩余数量 | 到期日期 | 距报告日 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in report["expiring_batches"]:
        lines.append("| " + " | ".join([
            entry["object"], entry["name"], str(entry["quantity"]),
            entry["expires_on"], str(entry["days_remaining"]),
        ]) + " |")
    if not report["expiring_batches"]:
        lines.append("| - | 无 | - | - | - |")

    lines += ["", "## 隔离待处置对象", "", "| 对象 | 名称 |", "| --- | --- |"]
    for entry in report["held_objects"]:
        lines.append(f"| {entry['object']} | {entry['name']} |")
    if not report["held_objects"]:
        lines.append("| - | 无 |")

    lines += ["", "## 当前库存位置", "", "| 对象 | 名称 | 位置 | 数量 |",
              "| --- | --- | --- | --- |"]
    for entry in report["stock"]:
        lines.append("| " + " | ".join([
            entry["object"], entry["name"], entry["location_path"], str(entry["quantity"]),
        ]) + " |")
    if not report["stock"]:
        lines.append("| - | 无 | - | - |")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=inventory.ROOT)
    parser.add_argument("--as-of", required=True, help="Report date in YYYY-MM-DD")
    parser.add_argument("--expiry-days", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        as_of = date.fromisoformat(args.as_of)
        inventory.require(args.expiry_days >= 0, "expiry-days cannot be negative")
        data = inventory.load(args.root)
        report = collect(data, inventory.validate(data), as_of, args.expiry_days)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render(report), encoding="utf-8")
        print(f"Generated {args.output}")
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(f"Report failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
