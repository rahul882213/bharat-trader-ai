"""Unit Tests for Module 12: Screener.in Integration."""
import io
import sys
import tempfile
import os
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.workflow import load_module_fn

screener_mod = load_module_fn("trader-screener", "screener_importer.py")


def _make_minimal_xlsx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets>'
            '<sheet name="Data Sheet" sheetId="1" r:id="rId1"/>'
            '<sheet name="Profit &amp; Loss" sheetId="2" r:id="rId2"/>'
            '</sheets></workbook>',
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
            '</Relationships>',
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            '<row r="1"><c r="A1" t="inlineStr"><is><t>Company Name</t></is></c><c r="B1" t="inlineStr"><is><t>Oriana Power Limited</t></is></c></row>'
            '<row r="2"><c r="A2" t="inlineStr"><is><t>Market Cap</t></is></c><c r="B2"><v>4520</v></c></row>'
            '<row r="3"><c r="A3" t="inlineStr"><is><t>Stock P/E</t></is></c><c r="B3"><v>34.5</v></c></row>'
            '<row r="4"><c r="A4" t="inlineStr"><is><t>ROCE</t></is></c><c r="B4"><v>28.4</v></c></row>'
            '<row r="5"><c r="A5" t="inlineStr"><is><t>ROE</t></is></c><c r="B5"><v>31.2</v></c></row>'
            '</sheetData></worksheet>',
        )
        zf.writestr(
            "xl/worksheets/sheet2.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            '<row r="1"><c r="A1" t="inlineStr"><is><t>Report Date</t></is></c>'
            '<c r="B1" t="inlineStr"><is><t>Mar 2023</t></is></c>'
            '<c r="C1" t="inlineStr"><is><t>Mar 2024</t></is></c>'
            '<c r="D1" t="inlineStr"><is><t>Mar 2025</t></is></c></row>'
            '<row r="2"><c r="A2" t="inlineStr"><is><t>Sales</t></is></c><c r="B2"><v>135</v></c><c r="C2"><v>382</v></c><c r="D2"><v>610</v></c></row>'
            '<row r="3"><c r="A3" t="inlineStr"><is><t>Operating Profit</t></is></c><c r="B3"><v>24</v></c><c r="C3"><v>81</v></c><c r="D3"><v>132</v></c></row>'
            '<row r="4"><c r="A4" t="inlineStr"><is><t>Net Profit</t></is></c><c r="B4"><v>12</v></c><c r="C4"><v>54</v></c><c r="D4"><v>89</v></c></row>'
            '</sheetData></worksheet>',
        )
    return buf.getvalue()


class TestScreenerIntegration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._prev_db = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{self._tmp.name}"

    def tearDown(self):
        if self._prev_db is not None:
            os.environ["DATABASE_URL"] = self._prev_db
        else:
            os.environ.pop("DATABASE_URL", None)
        if Path(self._tmp.name).exists():
            Path(self._tmp.name).unlink()

    def test_csv_multi_company_import_and_deduplication(self):
        csv_data = (
            "S.No.,Name,BSE Code,NSE Code,ISIN,CMP Rs.,P/E,Mar Cap Rs.Cr.,ROCE %,ROE %,Debt to equity,Sales growth 5Years %\n"
            "1,Hindustan Aeronautics Ltd,541154,HAL,INE066F01020,4250,36.2,284000,28.5,24.1,0.0,11.4\n"
            "2,Mazagon Dock Shipbuilders Ltd,543237,MAZDOCK,INE249Z01020,2100,29.8,85000,34.0,27.5,0.01,18.2\n"
            "3,Hindustan Aeronautics Ltd,541154,HAL,INE066F01020,4255,36.3,284500,28.5,24.1,0.0,11.4\n"
        )
        res = screener_mod.import_screener_csv(csv_data, filename="defence_screen.csv", screen_name="Defence Leaders")
        self.assertTrue(res["success"])
        self.assertEqual(res["duplicates_in_file"], 1)
        self.assertEqual(res["processed_companies"], 3)

        hal = screener_mod.get_screener_company("HAL")
        self.assertTrue(hal["available"])
        self.assertEqual(hal["ratios"]["roce_pct"], 28.5)
        self.assertIn("Balance Sheet", hal["missing_fields"])

    def test_xlsx_import_and_business_notes(self):
        xlsx_bytes = _make_minimal_xlsx()
        res = screener_mod.import_screener_xlsx(
            xlsx_bytes,
            filename="OrianaPower.xlsx",
            symbol_hint="ORIANAPOWER",
            screener_url="https://www.screener.in/company/ORIANA/consolidated/",
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["pnl_periods"], 3)
        screener_mod.update_business_notes("ORIANAPOWER", {"order_book_cr": 2400, "industry_outlook": "Solar EPC expansion"})
        comp = screener_mod.get_screener_company("ORIANAPOWER")
        self.assertTrue(comp["available"])
        self.assertEqual(comp["ratios"]["roce_pct"], 28.4)
        self.assertEqual(comp["business_notes"]["order_book_cr"], 2400)


if __name__ == "__main__":
    unittest.main()
