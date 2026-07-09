"""Vytvoří ukázková PDF rozpisy pro vyzkoušení aplikace.

Slouží jen k demonstraci a testování (žádná reálná data). Vyrobí několik
denních rozpisů do složky ``sample_pdfs/``.

Spuštění:  python tools/make_sample_pdfs.py
Vyžaduje knihovnu ``reportlab`` (pip install reportlab).
"""

from __future__ import annotations

import os
from datetime import date, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_pdfs")

# Výchozí font Helvetica neumí všechna česká písmena (č, ř, ž, ě, ů, š).
# Zkusíme zaregistrovat unicode TTF font; když žádný nenajdeme, použijeme
# Helveticu (česká diakritika se pak ve vzorku nemusí vykreslit správně).
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
]


def _register_font() -> str:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("AppFont", path))
                return "AppFont"
            except Exception:  # noqa: BLE001
                continue
    return "Helvetica"


FONT = _register_font()

# (jméno, začátek, konec) – pár lidí, kteří se v měsíci střídají.
ROSTER = [
    [("Novák Jan", "6:00", "14:30"), ("Svobodová Petra", "9:00", "17:00"),
     ("Dvořák Petr", "14:00", "22:00"), ("Černá Eva", "17:00", "23:30")],
    [("Svobodová Petra", "6:00", "14:00"), ("Procházka Tomáš", "8:00", "16:30"),
     ("Novák Jan", "14:00", "22:00"), ("Veselá Lucie", "16:00", "24:00")],
    [("Dvořák Petr", "6:00", "14:30"), ("Černá Eva", "10:00", "18:00"),
     ("Procházka Tomáš", "14:00", "22:00"), ("Novák Jan", "22:00", "6:00")],
]


def make_day_pdf(path: str, day: date, rows) -> None:
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    y = height - 60
    c.setFont(FONT, 16)
    c.drawString(50, y, "McDonald's – denní rozpis směn")
    y -= 28
    c.setFont(FONT, 12)
    c.drawString(50, y, f"Datum: {day.strftime('%d.%m.%Y')}")
    y -= 30
    c.setFont(FONT, 11)
    c.drawString(50, y, "Jméno")
    c.drawString(320, y, "Směna")
    y -= 6
    c.line(50, y, 500, y)
    y -= 20
    c.setFont(FONT, 11)
    for name, start, end in rows:
        c.drawString(50, y, name)
        c.drawString(320, y, f"{start} - {end}")
        y -= 20
    c.save()


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    start_day = date(2026, 6, 1)
    for i in range(6):  # 6 ukázkových dní
        day = start_day + timedelta(days=i)
        rows = ROSTER[i % len(ROSTER)]
        path = os.path.join(OUT_DIR, f"rozpis_{day.isoformat()}.pdf")
        make_day_pdf(path, day, rows)
        print("vytvořeno:", path)


if __name__ == "__main__":
    main()
