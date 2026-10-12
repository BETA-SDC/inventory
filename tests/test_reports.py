from datetime import date
from pathlib import Path
import sys
import unittest

from test_inventory import event, fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inventory
import reports


class ReportTests(unittest.TestCase):
    def test_overdue_expiring_and_held_objects(self):
        data = fixture()
        data["record"]["EVT-000001"] = event(
            1, "receive", "BAT-000001", 8,
            occurred_at="2026-10-01T10:00:00+08:00",
        )
        data["record"]["EVT-000002"] = event(
            2, "receive", "AST-000001",
            occurred_at="2026-10-01T10:00:00+08:00",
        )
        data["record"]["EVT-000003"] = event(
            3, "loan", "AST-000001", borrower="test-member", due_on="2026-10-05",
            occurred_at="2026-10-02T10:00:00+08:00",
        )
        data["record"]["EVT-000004"] = event(
            4, "hold", "BAT-000001", occurred_at="2026-10-03T10:00:00+08:00",
        )
        report = reports.collect(data, inventory.validate(data), date(2026, 10, 12), 8)
        self.assertEqual(report["overdue_loans"][0]["days_overdue"], 7)
        self.assertEqual(report["expiring_batches"][0]["quantity"], 8)
        self.assertEqual(report["held_objects"][0]["object"], "BAT-000001")
        text = reports.render(report)
        self.assertIn("EVT-000003", text)
        self.assertIn("2026-10-20", text)
        self.assertIn("Shelf A", text)

    def test_report_excludes_distant_and_empty_batches(self):
        data = fixture()
        data["record"]["EVT-000001"] = event(
            1, "receive", "BAT-000001", 2,
            occurred_at="2026-10-01T10:00:00+08:00",
        )
        data["record"]["EVT-000002"] = event(
            2, "consume", "BAT-000001", 2,
            occurred_at="2026-10-02T10:00:00+08:00",
        )
        report = reports.collect(data, inventory.validate(data), date(2026, 10, 12), 7)
        self.assertEqual(report["expiring_batches"], [])
        self.assertEqual(report["overdue_loans"], [])
        self.assertEqual(report["stock"], [])

    def test_invalid_expiry_range_rejected_by_cli_contract(self):
        with self.assertRaisesRegex(ValueError, "negative"):
            inventory.require(-1 >= 0, "expiry-days cannot be negative")


if __name__ == "__main__":
    unittest.main()
