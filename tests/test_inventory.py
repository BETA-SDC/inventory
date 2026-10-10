import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "inventory", Path(__file__).resolve().parents[1] / "scripts/inventory.py"
)
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def fixture():
    return {
        "categories": [
            {"id": "equipment", "name": "Equipment", "kind": "asset"},
            {"id": "food", "name": "Food", "kind": "batch"},
        ],
        "units": ["piece", "bottle"],
        "administrators": ["test-admin"],
        "location": {
            "LOC-000001": {"id": "LOC-000001", "name": "Room", "parent": None,
                           "description": "Test room", "storage": False},
            "LOC-000002": {"id": "LOC-000002", "name": "Shelf A", "parent": "LOC-000001",
                           "description": "Test shelf", "storage": True},
            "LOC-000003": {"id": "LOC-000003", "name": "Shelf B", "parent": "LOC-000001",
                           "description": "Test shelf", "storage": True},
        },
        "item": {
            "ITM-000001": {"id": "ITM-000001", "name": "Projector", "category": "equipment", "unit": "piece"},
            "ITM-000002": {"id": "ITM-000002", "name": "Milk", "category": "food", "unit": "bottle"},
        },
        "object": {
            "AST-000001": {"id": "AST-000001", "name": "Projector", "item": "ITM-000001"},
            "BAT-000001": {"id": "BAT-000001", "name": "Milk batch", "item": "ITM-000002",
                           "expires_on": "2026-10-20"},
        },
        "record": {},
    }


def event(number, operation, obj="AST-000001", quantity=1, **fields):
    record = {
        "id": f"EVT-{number:06d}", "type": operation, "object": obj, "quantity": quantity,
        "location": "LOC-000002", "occurred_at": "2026-10-10T10:00:00+08:00",
        "issue": number, "operation_key": "operation-1", "administrator": "test-admin",
        "reason": "Test operation",
    }
    record.update(fields)
    return record


def append(data, record):
    data["record"][record["id"]] = record


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def test_complete_loan_and_return_to_different_location(self):
        append(self.data, event(1, "receive"))
        append(self.data, event(2, "loan", borrower="test-member", due_on="2026-10-12"))
        state = inventory.validate(self.data)
        self.assertEqual(state[1]["EVT-000002"]["remaining"], 1)
        self.assertEqual(state[0][("AST-000001", "LOC-000002")], 0)
        append(self.data, event(3, "return", loan="EVT-000002", location="LOC-000003"))
        balances, loans, _ = inventory.validate(self.data)
        self.assertEqual(balances[("AST-000001", "LOC-000003")], 1)
        self.assertEqual(loans["EVT-000002"]["remaining"], 0)

    def test_batch_receipt_transfer_consumption(self):
        append(self.data, event(1, "receive", "BAT-000001", 10))
        append(self.data, event(2, "transfer", "BAT-000001", 4, destination="LOC-000003"))
        append(self.data, event(3, "consume", "BAT-000001", 3, location="LOC-000003"))
        balances, _, _ = inventory.validate(self.data)
        self.assertEqual(balances[("BAT-000001", "LOC-000002")], 6)
        self.assertEqual(balances[("BAT-000001", "LOC-000003")], 1)

    def test_negative_inventory_rejected(self):
        append(self.data, event(1, "consume", "BAT-000001", 1))
        with self.assertRaisesRegex(ValueError, "negative inventory"):
            inventory.validate(self.data)

    def test_duplicate_submission_rejected(self):
        append(self.data, event(1, "receive", "BAT-000001", 3))
        append(self.data, event(2, "receive", "BAT-000001", 3, issue=1))
        with self.assertRaisesRegex(ValueError, "duplicate issue"):
            inventory.validate(self.data)

    def test_double_loan_rejected(self):
        append(self.data, event(1, "receive"))
        append(self.data, event(2, "loan", borrower="member-a", due_on="2026-10-12"))
        append(self.data, event(3, "loan", borrower="member-b", due_on="2026-10-12"))
        with self.assertRaisesRegex(ValueError, "negative inventory"):
            inventory.validate(self.data)

    def test_double_asset_receipt_rejected(self):
        append(self.data, event(1, "receive"))
        append(self.data, event(2, "receive"))
        with self.assertRaisesRegex(ValueError, "exists more than once"):
            inventory.validate(self.data)

    def test_excess_return_rejected(self):
        append(self.data, event(1, "receive"))
        append(self.data, event(2, "loan", borrower="test-member", due_on="2026-10-12"))
        append(self.data, event(3, "return", loan="EVT-000002"))
        append(self.data, event(4, "return", loan="EVT-000002"))
        with self.assertRaisesRegex(ValueError, "excess return"):
            inventory.validate(self.data)

    def test_return_before_loan_rejected(self):
        append(self.data, event(1, "receive"))
        append(self.data, event(2, "loan", borrower="test-member", due_on="2026-10-12"))
        append(self.data, event(3, "return", loan="EVT-000002",
                                occurred_at="2026-10-09T10:00:00+08:00"))
        with self.assertRaisesRegex(ValueError, "return before"):
            inventory.validate(self.data)

    def test_expired_food_can_be_written_off_but_not_consumed(self):
        append(self.data, event(1, "receive", "BAT-000001", 4))
        record = event(2, "consume", "BAT-000001", 4, occurred_at="2026-10-21T10:00:00+08:00")
        append(self.data, record)
        with self.assertRaisesRegex(ValueError, "expired food"):
            inventory.validate(self.data)
        record["type"] = "writeoff"
        balances, _, _ = inventory.validate(self.data)
        self.assertEqual(balances[("BAT-000001", "LOC-000002")], 0)

    def test_hold_prevents_normal_issue_and_release_restores_it(self):
        append(self.data, event(1, "receive", "BAT-000001", 4))
        append(self.data, event(2, "hold", "BAT-000001"))
        append(self.data, event(3, "consume", "BAT-000001"))
        with self.assertRaisesRegex(ValueError, "object is held"):
            inventory.validate(self.data)
        self.data["record"]["EVT-000003"] = event(3, "release", "BAT-000001")
        append(self.data, event(4, "consume", "BAT-000001"))
        self.assertEqual(inventory.validate(self.data)[0][("BAT-000001", "LOC-000002")], 3)

    def test_location_cycle_and_unknown_parent_rejected(self):
        self.data["location"]["LOC-000001"]["parent"] = "LOC-000002"
        with self.assertRaisesRegex(ValueError, "cyclic location"):
            inventory.validate(self.data)
        self.data["location"]["LOC-000001"]["parent"] = "LOC-999999"
        with self.assertRaisesRegex(ValueError, "unknown parent"):
            inventory.validate(self.data)

    def test_unknown_admin_and_noninteger_quantity_rejected(self):
        append(self.data, event(1, "receive", administrator="outsider"))
        with self.assertRaisesRegex(ValueError, "unknown administrator"):
            inventory.validate(self.data)
        self.data["record"]["EVT-000001"] = event(1, "receive", quantity=True)
        with self.assertRaisesRegex(ValueError, "positive integer"):
            inventory.validate(self.data)

    def test_no_public_phone_field(self):
        self.data["object"]["AST-000001"]["phone"] = "NOT-A-REAL-NUMBER"
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            inventory.validate(self.data)

    def test_render_expands_location_and_escapes_content(self):
        append(self.data, event(1, "receive"))
        self.data["object"]["AST-000001"]["name"] = "<script>|test"
        text = inventory.render(self.data, inventory.validate(self.data))
        self.assertIn("Room / Shelf A", text)
        self.assertIn("&lt;script&gt;&#124;test", text)
        self.assertNotIn("<script>", text)


class RegistrationTests(unittest.TestCase):
    def populate(self, root):
        data = fixture()
        (root / "catalogs").mkdir()
        for name in ("categories", "units", "administrators"):
            (root / f"catalogs/{name}.json").write_text(json.dumps(data[name]), encoding="utf-8")
        for kind, directory in inventory.DIRECTORIES.items():
            (root / directory).mkdir()
            for identifier, entry in data[kind].items():
                (root / directory / f"{identifier}.json").write_text(json.dumps(entry), encoding="utf-8")

    def test_add_assigns_number_and_failed_record_leaves_no_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.populate(root)
            draft = root / "draft.json"
            record = event(1, "receive")
            del record["id"]
            draft.write_text(json.dumps(record), encoding="utf-8")
            path = inventory.add(root, "record", draft)
            self.assertEqual(path.relative_to(root).as_posix(), "records/2026/10/EVT-000001.json")
            inventory.validate(inventory.load(root))
            # A duplicate submitted operation must not create a second file.
            with self.assertRaisesRegex(ValueError, "duplicate issue"):
                inventory.add(root, "record", draft)
            self.assertEqual(len(list((root / "records").rglob("*.json"))), 1)

    def test_unknown_reference_leaves_no_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.populate(root)
            draft = root / "draft.json"
            draft.write_text(json.dumps({"name": "Bad", "item": "ITM-999999"}), encoding="utf-8")
            before = list((root / "objects").rglob("*.json"))
            with self.assertRaisesRegex(ValueError, "Unknown item"):
                inventory.add(root, "object", draft)
            self.assertEqual(before, list((root / "objects").rglob("*.json")))


if __name__ == "__main__":
    unittest.main()
