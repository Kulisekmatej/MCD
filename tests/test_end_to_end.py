"""Test celé cesty: vytvořit PDF -> přečíst -> sečíst -> export.

Přeskočí se, pokud nejsou nainstalované knihovny (reportlab / pdfplumber /
openpyxl). Na Windows při běžném používání jsou potřeba jen pdfplumber a
openpyxl; reportlab slouží jen k vytvoření testovacích PDF.
"""

import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import pdfplumber  # noqa: F401
    import reportlab  # noqa: F401
    HAVE_PDF_LIBS = True
except Exception:  # noqa: BLE001
    HAVE_PDF_LIBS = False

try:
    import openpyxl  # noqa: F401
    HAVE_OPENPYXL = True
except Exception:  # noqa: BLE001
    HAVE_OPENPYXL = False


@unittest.skipUnless(HAVE_PDF_LIBS, "vyžaduje pdfplumber a reportlab")
class EndToEndTest(unittest.TestCase):
    def _make_pdf(self, path, day, rows):
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(path, pagesize=A4)
        _, height = A4
        y = height - 60
        c.drawString(50, y, f"Datum: {day.strftime('%d.%m.%Y')}")
        y -= 30
        for name, start, end in rows:
            c.drawString(50, y, name)
            c.drawString(300, y, f"{start} - {end}")
            y -= 20
        c.save()

    def test_full_pipeline(self):
        from hours_tracker.aggregator import aggregate
        from hours_tracker.parser import parse_pdf

        with tempfile.TemporaryDirectory() as tmp:
            p1 = os.path.join(tmp, "rozpis_2026-06-01.pdf")
            p2 = os.path.join(tmp, "rozpis_2026-06-02.pdf")
            # ASCII jména: výchozí font reportlabu neumí všechna česká písmena;
            # parsování diakritiky je pokryté testy na úrovni textu.
            self._make_pdf(p1, date(2026, 6, 1),
                           [("Novak Jan", "9:00", "17:00"),
                            ("Eva Bila", "10:00", "16:00")])
            self._make_pdf(p2, date(2026, 6, 2),
                           [("Novak Jan", "8:00", "14:00")])

            shifts = parse_pdf(p1) + parse_pdf(p2)
            totals = {t.employee: t for t in aggregate(shifts)}

            self.assertIn("Novak Jan", totals)
            self.assertEqual(totals["Novak Jan"].total_minutes, 8 * 60 + 6 * 60)
            self.assertEqual(totals["Novak Jan"].day_count, 2)
            self.assertEqual(totals["Eva Bila"].total_minutes, 6 * 60)

            if HAVE_OPENPYXL:
                from hours_tracker.exporter import export_xlsx
                out = os.path.join(tmp, "out.xlsx")
                export_xlsx(list(aggregate(shifts)), out, period="1.6.–2.6.2026")
                self.assertTrue(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
