#!/usr/bin/env python3
"""Read public Issues and prepare administrator-reviewed local drafts."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import yaml

import inventory


REPOSITORY = "BETA-SDC/inventory"
TYPES = {"intake", "borrow", "return", "consume", "transfer", "incident", "stocktake"}


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def snapshot(issue):
    inventory.require(inventory.positive_int(issue.get("number")), "Invalid Issue number")
    number = issue["number"]
    inventory.require(issue.get("url") == f"https://github.com/{REPOSITORY}/issues/{number}",
                      "Issue must belong to BETA-SDC/inventory")
    inventory.require(isinstance(issue.get("title"), str) and isinstance(issue.get("body"), str),
                      "Issue title and body required")
    author = issue.get("author", {}).get("login")
    inventory.require(inventory.username(author), "Invalid author")
    return {"number": number, "url": issue["url"], "title": issue["title"],
            "body": issue["body"], "author": author}


def fetch_issue(number):
    inventory.require(inventory.positive_int(number), "Positive Issue number required")
    command = (["opencli", "gh"] if shutil.which("opencli") else ["gh"])
    result = subprocess.run(
        command + ["issue", "view", str(number), "--repo", REPOSITORY,
                   "--json", "number,url,title,body,author"],
        check=True, capture_output=True, text=True, timeout=60,
    )
    return json.loads(result.stdout)


def parse_sections(body):
    sections = {}
    label = None
    lines = []

    def store():
        if label is not None:
            inventory.require(label not in sections, "Duplicate form heading")
            text = "\n".join(lines).strip()
            sections[label] = "" if text == "_No response_" else text

    for line in body.splitlines():
        if line.startswith("### "):
            store()
            label = line[4:].strip()
            lines = []
        elif label is not None:
            lines.append(line)
    store()
    return sections


def form_for(root, kind):
    for path in sorted((root / ".github/ISSUE_TEMPLATE").glob("[0-9]*.yml")):
        form = yaml.safe_load(path.read_text(encoding="utf-8"))
        if form["title"].strip() == f"[{kind}]":
            return form
    raise ValueError("Unsupported application type")


def field_problem(field, value):
    if field.get("validations", {}).get("required") and not value:
        return "缺少必填内容"
    if field["type"] == "dropdown" and value and value not in field["attributes"]["options"]:
        return "选项不匹配"
    if field["type"] == "checkboxes":
        expected = [option["label"] for option in field["attributes"]["options"] if option.get("required")]
        if any(f"- [X] {label}" not in value and f"- [x] {label}" not in value for label in expected):
            return "尚未确认必选条目"
    return None


def references(text, prefix):
    return list(dict.fromkeys(re.findall(rf"\b{prefix}-[0-9]{{6}}\b", text)))


def prepare(root, issue):
    source = snapshot(issue)
    match = re.match(r"^\[([a-z]+)\] ", source["title"])
    inventory.require(match and match[1] in TYPES, "Unsupported Issue title prefix")
    kind = match[1]
    form = form_for(root, kind)
    sections = parse_sections(source["body"])
    fields = {}
    problems = []
    for field in form["body"]:
        if field["type"] == "markdown":
            continue
        label = field["attributes"]["label"]
        value = sections.get(label, "")
        fields[field["id"]] = value
        problem = field_problem(field, value)
        if problem:
            problems.append(f"{label}：{problem}")
    expected = {field["attributes"]["label"] for field in form["body"] if field["type"] != "markdown"}
    if set(sections) - expected:
        problems.append("包含模板以外的字段，请管理员检查")
    if fields.get("timing") == "特殊情况补登记" and not fields.get("exception"):
        problems.append("补登记说明：需填写实际时间、原因和知情管理员")
    if kind == "intake" and fields.get("kind") == "食品饮料" and not fields.get("batch"):
        problems.append("食品或批次信息：需填写到期日期及保存要求")
    if re.search(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", source["body"]):
        problems.append("疑似手机号：请在公开申请中移除，按私有信息规范提交")
    contact = fields.get("contact", "")
    if contact.startswith("http") and not re.fullmatch(
        r"https://github\.com/BETA-SDC/community-private-information/blob/[^/\s]+/"
        r"text/contacts/[A-Za-z0-9_./-]+\.md#(?:contact|role)-[a-z0-9-]+", contact
    ):
        problems.append("私有联系人记录：请引用组织联系人文件中的稳定标题")

    data = inventory.load(root)
    state = inventory.validate(data)
    summary = []
    records = []
    object_text = fields.get("assets") or fields.get("items") or ""
    object_ids = references(object_text, "AST") + references(object_text, "BAT")
    locations = references(fields.get("location") or fields.get("source") or "", "LOC")
    destination = references(fields.get("destination", ""), "LOC")
    parent_number = None
    if fields.get("parent"):
        parent_match = re.fullmatch(
            r"(?:#?([1-9]\d*)|https://github\.com/BETA-SDC/inventory/issues/([1-9]\d*))",
            fields["parent"].strip(),
        )
        if parent_match:
            parent_number = int(parent_match[1] or parent_match[2])
        else:
            problems.append("关联申请：需填写本仓库编号或完整链接")

    for object_id in object_ids:
        obj = data["object"].get(object_id)
        if obj is None:
            problems.append(f"{object_id}：正式台账中不存在")
            continue
        stocks = [{"location": location, "quantity": quantity}
                  for (identifier, location), quantity in sorted(state[0].items())
                  if identifier == object_id and quantity]
        suggested_locations = locations
        if kind == "borrow" and not locations and len(stocks) == 1:
            suggested_locations = [stocks[0]["location"]]
        summary.append({"object": object_id, "name": obj["name"], "stock": stocks,
                        "held": object_id in state[2], "expires_on": obj.get("expires_on")})
        operation = {"borrow": "loan", "return": "return", "consume": "consume",
                     "transfer": "transfer"}.get(kind)
        if not operation:
            continue
        record = {
            "type": operation, "object": object_id,
            "quantity": 1 if object_id.startswith("AST-") else None,
            "location": suggested_locations[0] if len(suggested_locations) == 1 else None,
            "occurred_at": None, "issue": source["number"],
            "operation_key": f"{kind}-{object_id.lower()}-1",
            "administrator": None, "reason": None,
            "source_digest": digest(source),
        }
        if operation == "loan":
            borrower = fields.get("borrower", "").strip().removeprefix("@")
            record["borrower"] = borrower if inventory.username(borrower) else None
            record["due_on"] = fields.get("due") or None
        elif operation == "return":
            loans = [identifier for identifier, loan in state[1].items()
                     if loan["object"] == object_id and loan["remaining"] and loan["issue"] == parent_number]
            record["loan"] = loans[0] if len(loans) == 1 else None
        elif operation == "transfer":
            record["destination"] = destination[0] if len(destination) == 1 else None
        records.append(record)
    if kind in {"borrow", "return", "consume", "transfer"} and not object_ids:
        problems.append("未识别到正式对象编号，需管理员确认后补充")
    if kind in {"intake", "incident", "stocktake"}:
        summary.append({"notice": "该类型需管理员先确认对象、处置方式或盘点差异，再填写实际操作记录"})
    return {
        "version": 1, "issue": source["number"], "kind": kind,
        "source_digest": digest(source), "ledger_digest": digest(data),
        "form_problems": problems, "review_summary": summary,
        "confirmed_member": False, "confirmed_contact": False, "confirmed_physical_operation": False,
        "records": records,
    }


def verified_candidate(root, draft, issue):
    inventory.require(draft.get("version") == 1, "Unsupported draft version")
    source = snapshot(issue)
    inventory.require(draft.get("issue") == source["number"] and draft.get("source_digest") == digest(source),
                      "Issue changed: prepare and review a new draft")
    fresh = prepare(root, issue)
    inventory.require(not fresh["form_problems"], "Issue is incomplete or requires privacy review")
    for field in ("confirmed_member", "confirmed_contact", "confirmed_physical_operation"):
        inventory.require(draft.get(field) is True, f"Administrator confirmation required: {field}")
    data = inventory.load(root)
    inventory.validate(data)
    inventory.require(draft.get("ledger_digest") == digest(data), "Ledger changed: prepare a new draft")
    records = draft.get("records")
    inventory.require(isinstance(records, list) and records, "At least one actual record required")
    candidate = deepcopy(data)
    maximum = max((int(identifier[4:]) for identifier in data["record"]), default=0)
    for offset, record in enumerate(records, 1):
        inventory.require(isinstance(record, dict) and "id" not in record, "Record must have no id")
        inventory.require(record.get("issue") == source["number"] and
                          record.get("source_digest") == draft["source_digest"], "Record source mismatch")
        require_type = {"borrow": {"loan"}, "return": {"return"}, "consume": {"consume"},
                        "transfer": {"transfer"}, "intake": {"receive"},
                        "incident": {"hold", "release", "writeoff"},
                        "stocktake": {"adjust-in", "adjust-out"}}[fresh["kind"]]
        inventory.require(record.get("type") in require_type, "Record operation does not match application")
        identifier = f"EVT-{maximum + offset:06d}"
        candidate["record"][identifier] = dict(record, id=identifier)
    inventory.validate(candidate)
    return data, candidate


def apply(root, draft, issue):
    _, candidate = verified_candidate(root, draft, issue)
    data = inventory.load(root)
    inventory.require(digest(data) == draft["ledger_digest"], "Ledger changed before writing")
    created = []
    try:
        for identifier in sorted(set(candidate["record"]) - set(data["record"])):
            record = candidate["record"][identifier]
            occurred = inventory.datetime.fromisoformat(record["occurred_at"])
            path = root / "records" / occurred.strftime("%Y/%m") / f"{identifier}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as output:
                created.append(path)
                output.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    except Exception:
        for path in created:
            path.unlink()
        raise
    return created


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=inventory.ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare")
    source = command.add_mutually_exclusive_group(required=True)
    source.add_argument("--issue", type=int)
    source.add_argument("--input", type=Path, help="Read an exported public Issue JSON offline")
    command.add_argument("--output", type=Path, required=True)
    for name in ("check", "apply"):
        command = commands.add_parser(name)
        command.add_argument("--draft", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            output = args.output.resolve()
            scratch = (args.root / ".scratch").resolve()
            inventory.require(output.is_relative_to(scratch), "Draft output must be inside .scratch/")
            issue = inventory.read_json(args.input) if args.input else fetch_issue(args.issue)
            draft = prepare(args.root, issue)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as target:
                target.write(json.dumps(draft, ensure_ascii=False, indent=2) + "\n")
            print(f"Draft created: {output}. Review notices: {len(draft['form_problems'])}.")
        else:
            draft = inventory.read_json(args.draft)
            issue = fetch_issue(draft["issue"])
            if args.command == "check":
                verified_candidate(args.root, draft, issue)
                print("Draft, live Issue and candidate ledger passed.")
            else:
                paths = apply(args.root, draft, issue)
                print(f"Created {len(paths)} records. Run build, review the diff, then commit.")
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        # Do not echo subprocess stderr, which can contain copied Issue content.
        message = type(error).__name__ if isinstance(error, subprocess.SubprocessError) else str(error)
        print(f"Request processing failed: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
