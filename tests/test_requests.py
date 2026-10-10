from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from test_inventory import fixture, event


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("request_tools", ROOT / "scripts/requests.py")
requests = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(requests)


def issue(kind="borrow", number=42):
    form = requests.form_for(ROOT, kind)
    values = {
        "assets": "AST-000001", "borrower": "@test-member", "purpose": "Test use",
        "start": "2026-10-10 10:00", "due": "2026-10-12", "timing": "领取前申请",
        "contact": "", "exception": "", "parent": "#2",
        "returned": "2026-10-10 11:00", "location": "LOC-000002", "condition": "Intact",
        "source": "LOC-000002", "destination": "LOC-000003",
        "items": "BAT-000001 / Milk / 2 / bottle", "time": "2026-10-10 10:00",
        "handover": "Test handover", "kind": "设备", "evidence": "Intact",
        "facts": "Test facts", "scope": "LOC-000002", "result": "Test plan",
    }
    body = []
    for field in form["body"]:
        if field["type"] == "markdown":
            continue
        value = values.get(field["id"], "")
        if field["type"] == "dropdown":
            value = field["attributes"]["options"][0]
        if field["type"] == "checkboxes":
            value = "\n".join("- [X] " + option["label"] for option in field["attributes"]["options"])
        body.extend(["### " + field["attributes"]["label"], "", value or "_No response_", ""])
    return {"number": number, "url": f"https://github.com/BETA-SDC/inventory/issues/{number}",
            "title": f"[{kind}] Test request", "body": "\n".join(body),
            "author": {"login": "test-member"}}


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / ".github/ISSUE_TEMPLATE", self.root / ".github/ISSUE_TEMPLATE")
        data = fixture()
        received = event(1, "receive")
        data["record"][received["id"]] = received
        (self.root / "catalogs").mkdir()
        for name in ("categories", "units", "administrators"):
            (self.root / f"catalogs/{name}.json").write_text(json.dumps(data[name]), encoding="utf-8")
        for kind, directory in requests.inventory.DIRECTORIES.items():
            for identifier, entry in data[kind].items():
                target = self.root / directory
                if kind == "record":
                    target /= "2026/10"
                target.mkdir(parents=True, exist_ok=True)
                (target / f"{identifier}.json").write_text(json.dumps(entry), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def reviewed(self):
        source = issue()
        draft = requests.prepare(self.root, source)
        draft.update(confirmed_member=True, confirmed_contact=True, confirmed_physical_operation=True)
        draft["records"][0].update(location="LOC-000002", occurred_at="2026-10-10T10:00:00+08:00",
                                   administrator="test-admin", reason="Confirmed physical handover")
        return source, draft

    def test_prepare_does_not_modify_ledger(self):
        before = requests.digest(requests.inventory.load(self.root))
        draft = requests.prepare(self.root, issue())
        self.assertEqual(draft["form_problems"], [])
        self.assertFalse(draft["confirmed_member"])
        self.assertIsNone(draft["records"][0]["occurred_at"])
        self.assertIsNone(draft["records"][0]["administrator"])
        self.assertEqual(draft["records"][0]["borrower"], "test-member")
        self.assertEqual(requests.digest(requests.inventory.load(self.root)), before)

    def test_seven_templates_parse(self):
        for kind in requests.TYPES:
            with self.subTest(kind=kind):
                draft = requests.prepare(self.root, issue(kind))
                self.assertEqual(draft["kind"], kind)
                self.assertFalse(draft["form_problems"])

    def test_missing_required_and_unchecked_confirmation(self):
        source = issue()
        source["body"] = source["body"].replace("@test-member", "_No response_").replace("- [X]", "- [ ]")
        draft = requests.prepare(self.root, source)
        self.assertEqual(len(draft["form_problems"]), 2)

    def test_phone_is_reported_without_copying_it_to_draft(self):
        source = issue()
        source["body"] = source["body"].replace("Test use", "Phone 13800000000")
        draft = requests.prepare(self.root, source)
        self.assertTrue(any("疑似手机号" in problem for problem in draft["form_problems"]))
        self.assertNotIn("13800000000", json.dumps(draft))

    def test_wrong_repository_and_duplicate_sections_rejected(self):
        source = issue()
        source["url"] = "https://github.com/another/repo/issues/42"
        with self.assertRaisesRegex(ValueError, "must belong"):
            requests.prepare(self.root, source)
        source = issue()
        source["body"] += "\n### 实际借用人\n\n@other"
        with self.assertRaisesRegex(ValueError, "Duplicate form"):
            requests.prepare(self.root, source)

    def test_application_changes_require_new_review(self):
        source, draft = self.reviewed()
        source["body"] += "\nChanged"
        with self.assertRaisesRegex(ValueError, "Issue changed"):
            requests.verified_candidate(self.root, draft, source)

    def test_missing_confirmation_and_new_ledger_rejected(self):
        source, draft = self.reviewed()
        draft["confirmed_contact"] = False
        with self.assertRaisesRegex(ValueError, "confirmation required"):
            requests.verified_candidate(self.root, draft, source)
        draft["confirmed_contact"] = True
        (self.root / "catalogs/units.json").write_text('["piece", "bottle", "gram"]', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Ledger changed"):
            requests.verified_candidate(self.root, draft, source)

    def test_actual_apply_and_duplicate_apply(self):
        source, draft = self.reviewed()
        paths = requests.apply(self.root, draft, source)
        self.assertEqual(len(paths), 1)
        state = requests.inventory.validate(requests.inventory.load(self.root))
        self.assertEqual(state[1]["EVT-000002"]["remaining"], 1)
        with self.assertRaisesRegex(ValueError, "Ledger changed"):
            requests.apply(self.root, draft, source)

    def test_multiple_records_validated_before_any_write(self):
        source, draft = self.reviewed()
        extra = deepcopy(draft["records"][0])
        extra["operation_key"] = "second-loan"
        draft["records"].append(extra)
        with self.assertRaisesRegex(ValueError, "negative inventory"):
            requests.apply(self.root, draft, source)
        self.assertEqual(len(list((self.root / "records").rglob("*.json"))), 1)

    def test_batch_write_rolls_back_on_io_failure(self):
        source = issue("consume")
        record = event(2, "receive", "BAT-000001", 3)
        path = self.root / "records/2026/10/EVT-000002.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        draft = requests.prepare(self.root, source)
        draft.update(confirmed_member=True, confirmed_contact=True, confirmed_physical_operation=True)
        draft["records"][0].update(quantity=1, location="LOC-000002",
                                   occurred_at="2026-10-10T10:00:00+08:00",
                                   administrator="test-admin", reason="Consumed")
        extra = deepcopy(draft["records"][0])
        extra["operation_key"] = "second-portion"
        draft["records"].append(extra)
        original = Path.open

        def fail_second(path, mode="r", *args, **kwargs):
            if path.name == "EVT-000004.json" and mode == "x":
                raise OSError("Test disk failure")
            return original(path, mode, *args, **kwargs)

        with patch.object(Path, "open", fail_second):
            with self.assertRaisesRegex(OSError, "Test disk failure"):
                requests.apply(self.root, draft, source)
        self.assertFalse((self.root / "records/2026/10/EVT-000003.json").exists())

    def test_return_matches_original_issue_and_loan(self):
        loan = event(2, "loan", borrower="test-member", due_on="2026-10-12")
        path = self.root / "records/2026/10/EVT-000002.json"
        path.write_text(json.dumps(loan), encoding="utf-8")
        draft = requests.prepare(self.root, issue("return"))
        self.assertEqual(draft["records"][0]["loan"], "EVT-000002")

    def test_request_operation_mismatch_rejected(self):
        source, draft = self.reviewed()
        draft["records"][0]["type"] = "writeoff"
        with self.assertRaisesRegex(ValueError, "does not match"):
            requests.verified_candidate(self.root, draft, source)


if __name__ == "__main__":
    unittest.main()
