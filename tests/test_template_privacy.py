"""Published medication templates contain headings, never patient records."""
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import openpyxl


ASSETS = Path(__file__).resolve().parents[1] / "assets"


class TemplatePrivacyTest(unittest.TestCase):
    def test_medication_templates_only_contain_title_and_headers(self):
        for name in ("medication-reminder-template.xlsx", "medication-list-template.xlsx"):
            with self.subTest(template=name):
                book = openpyxl.load_workbook(ASSETS / name, read_only=True)
                try:
                    allowed_strings = set()
                    for sheet in book:
                        rows = list(sheet.values)
                        self.assertGreaterEqual(len(rows), 2)
                        self.assertTrue(any(rows[1]))
                        self.assertFalse(any(value is not None for row in rows[2:] for value in row))
                        allowed_strings.update(value for row in rows[:2] for value in row if isinstance(value, str))
                    with zipfile.ZipFile(ASSETS / name) as archive:
                        if "xl/sharedStrings.xml" in archive.namelist():
                            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                            self.assertTrue(all("".join(item.itertext()) in allowed_strings for item in root))
                finally:
                    book.close()


if __name__ == "__main__":
    unittest.main()
