from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest

from pypdf import PdfReader

from test_inventory import fixture, event


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inventory
import labels


class LabelTests(unittest.TestCase):
    def test_label_has_stable_link_and_no_personal_or_current_location_info(self):
        data = fixture()
        entries = labels.label_data(data, ["AST-000001", "BAT-000001", "LOC-000002"])
        self.assertTrue(entries[0]["url"].endswith("/objects/AST-000001.md"))
        self.assertEqual(entries[0]["detail"], "")
        self.assertIn("2026-10-20", entries[1]["detail"])
        self.assertTrue(entries[2]["url"].endswith("/locations/LOC-000002.md"))

    def test_pdf_text_links_and_pagination(self):
        data = fixture()
        for number in range(2, 12):
            identifier = f"AST-{number:06d}"
            data["object"][identifier] = dict(data["object"]["AST-000001"], id=identifier)
        content = labels.create_pdf(data, list(data["object"]))
        reader = PdfReader(BytesIO(content))
        self.assertEqual(len(reader.pages), 2)
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("AST-000001", text)
        self.assertIn("2026-10-20", text)
        annotations = [item.get_object() for page in reader.pages for item in page.get("/Annots", [])]
        self.assertEqual(len(annotations), 12)
        self.assertTrue(all(item["/A"]["/URI"].startswith(labels.BASE_URL) for item in annotations))
        for page in reader.pages:
            fonts = page["/Resources"]["/Font"].get_object()
            embedded = [font.get_object() for font in fonts.values()
                        if "/FontDescriptor" in font.get_object()]
            self.assertTrue(embedded)
            self.assertTrue(all("/FontFile2" in font["/FontDescriptor"] for font in embedded))

    def test_generated_views_have_valid_local_links_and_prefilled_form(self):
        data = fixture()
        data["record"]["EVT-000001"] = event(1, "receive")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            views = inventory.build_views(root, data, inventory.validate(data))
            self.assertEqual(len(views), 6)
            text = (root / "views/objects/AST-000001.md").read_text(encoding="utf-8")
            self.assertIn("assets=AST-000001", text)
            self.assertIn("LOC-000002", text)
            self.assertTrue((root / "views/locations/LOC-000002.md").exists())
            inventory.build_views(root, data, inventory.validate(data), check=True)
            (root / "views/objects/AST-000001.md").unlink()
            with self.assertRaisesRegex(ValueError, "missing or stale"):
                inventory.build_views(root, data, inventory.validate(data), check=True)

    def test_unknown_label_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown label"):
            labels.label_data(fixture(), ["AST-999999"])


if __name__ == "__main__":
    unittest.main()
