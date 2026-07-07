import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hours_tracker.parser import (  # noqa: E402
    parse_date_from_filename,
    parse_shifts_from_text,
)


class ParseShiftsTest(unittest.TestCase):
    def test_basic_line(self):
        shifts = parse_shifts_from_text("Novák Jan        9:00 - 17:30")
        self.assertEqual(len(shifts), 1)
        s = shifts[0]
        self.assertEqual(s.employee, "Novák Jan")
        self.assertEqual(s.start_minutes, 9 * 60)
        self.assertEqual(s.end_minutes, 17 * 60 + 30)
        self.assertEqual(s.span_minutes, 8 * 60 + 30)

    def test_separators_and_dot_times(self):
        for line in [
            "Svobodová Petra 11.00–19.00",
            "Svobodová Petra 11:00 — 19:00",
            "Svobodová Petra 11:00 do 19:00",
            "Svobodová Petra 11:00 až 19:00",
        ]:
            shifts = parse_shifts_from_text(line)
            self.assertEqual(len(shifts), 1, line)
            self.assertEqual(shifts[0].span_minutes, 8 * 60, line)

    def test_overnight_shift(self):
        shifts = parse_shifts_from_text("Dvořák Petr 22:00 - 6:00")
        self.assertEqual(len(shifts), 1)
        self.assertEqual(shifts[0].span_minutes, 8 * 60)

    def test_leading_numbering_is_stripped(self):
        shifts = parse_shifts_from_text("1. Novák Jan 9:00 - 17:00")
        self.assertEqual(shifts[0].employee, "Novák Jan")

    def test_header_and_empty_lines_ignored(self):
        text = "\n".join([
            "McDonald's denní rozpis",
            "Datum: 01.06.2026",
            "Jméno            Směna",
            "",
            "Novák Jan        9:00 - 17:00",
            "Celkem           8:00",
        ])
        shifts = parse_shifts_from_text(text)
        names = [s.employee for s in shifts]
        self.assertEqual(names, ["Novák Jan"])

    def test_date_from_header_assigned(self):
        text = "Datum: 15.06.2026\nNovák Jan 9:00 - 17:00"
        shifts = parse_shifts_from_text(text)
        self.assertEqual(shifts[0].day, date(2026, 6, 15))

    def test_no_times_no_shifts(self):
        self.assertEqual(parse_shifts_from_text("Jen nějaký text bez časů"), [])

    def test_multiple_ranges_span(self):
        # Dělená směna na jednom řádku: sečtou se délky částí, mezera se nepočítá.
        shifts = parse_shifts_from_text("Novák Jan 8:00 - 12:00 13:00 - 17:00")
        self.assertEqual(len(shifts), 1)
        self.assertEqual(shifts[0].start_minutes, 8 * 60)
        self.assertEqual(shifts[0].end_minutes, 17 * 60)
        self.assertEqual(shifts[0].span_minutes, 8 * 60)  # 4 + 4 h, bez mezery

    def test_multiple_ranges_gap_not_counted(self):
        # 8–12 a 16–20 = 8 h práce, ne 12 h okna.
        shifts = parse_shifts_from_text("Novák Jan 8:00 - 12:00 16:00 - 20:00")
        self.assertEqual(shifts[0].span_minutes, 8 * 60)

    def test_od_do_separator_not_in_name(self):
        # Zápis "od 9:00 do 17:00" nesmí nechat "od" ve jménu.
        shifts = parse_shifts_from_text("Novák Jan od 9:00 do 17:00")
        self.assertEqual(len(shifts), 1)
        self.assertEqual(shifts[0].employee, "Novák Jan")
        self.assertEqual(shifts[0].span_minutes, 8 * 60)


class FilenameDateTest(unittest.TestCase):
    def test_iso(self):
        self.assertEqual(parse_date_from_filename("rozpis_2026-06-01.pdf"),
                         date(2026, 6, 1))

    def test_dotted(self):
        self.assertEqual(parse_date_from_filename("01.06.2026.pdf"),
                         date(2026, 6, 1))

    def test_none(self):
        self.assertIsNone(parse_date_from_filename("rozpis.pdf"))


if __name__ == "__main__":
    unittest.main()
