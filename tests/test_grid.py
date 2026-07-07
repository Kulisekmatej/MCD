import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hours_tracker.parser import (  # noqa: E402
    contract_hours_from_tokens,
    grid_name_from_tokens,
    parse_cell_shift,
    parse_leave_cell,
    parse_period_start,
)


class PeriodTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(
            parse_period_start("Rozpis směn 01.06.2026 - 14.06.2026"),
            date(2026, 6, 1),
        )

    def test_with_dashes_and_spaces(self):
        self.assertEqual(
            parse_period_start("Rozpis směn 1. 6. 2026 – 14. 6. 2026"),
            date(2026, 6, 1),
        )

    def test_none(self):
        self.assertIsNone(parse_period_start("něco bez období"))


class CellShiftTest(unittest.TestCase):
    def test_day_shift(self):
        # 06:00–15:30 = 9 h 30 min
        self.assertEqual(parse_cell_shift("0600\n1530"), (360, 930, 570))

    def test_ends_at_midnight(self):
        # 16:00–00:00 = 8 h (konec o půlnoci)
        self.assertEqual(parse_cell_shift("1600\n0000"), (960, 0, 480))

    def test_overnight(self):
        # 22:00–06:00 = 8 h přes půlnoc
        self.assertEqual(parse_cell_shift("2200\n0600"), (1320, 360, 480))

    def test_quarter_hours(self):
        # 11:15–17:15 = 6 h
        self.assertEqual(parse_cell_shift("1115\n1715"), (675, 1035, 360))

    def test_empty_and_codes(self):
        self.assertIsNone(parse_cell_shift(""))
        self.assertIsNone(parse_cell_shift(None))
        self.assertIsNone(parse_cell_shift("D(1d)"))
        self.assertIsNone(parse_cell_shift("D(4h.)"))

    def test_single_time_is_ignored(self):
        self.assertIsNone(parse_cell_shift("0800"))

    def test_invalid_times_rejected(self):
        # 24:30 ani 25:00 nejsou platné časy; 24:00 jako konec ano.
        self.assertIsNone(parse_cell_shift("2430\n0600"))
        self.assertIsNone(parse_cell_shift("2500\n0600"))
        self.assertEqual(parse_cell_shift("1600\n2400"), (960, 1440, 480))


class LeaveCellTest(unittest.TestCase):
    def test_vacation_day(self):
        self.assertEqual(parse_leave_cell("D(1d)"), ("vacation", 1.0, 0.0))

    def test_vacation_multiple_days(self):
        self.assertEqual(parse_leave_cell("D(2d)"), ("vacation", 2.0, 0.0))

    def test_vacation_hours(self):
        self.assertEqual(parse_leave_cell("D(4h.)"), ("vacation", 0.0, 4.0))

    def test_sick_hours(self):
        self.assertEqual(parse_leave_cell("PN(7.5h.)"), ("sick", 0.0, 7.5))

    def test_sick_day(self):
        self.assertEqual(parse_leave_cell("PN(1d)"), ("sick", 1.0, 0.0))

    def test_sick_garbled_overlap(self):
        # V PDF se PN text někdy ztrojí/překrývá – bereme první výskyt.
        self.assertEqual(parse_leave_cell("PN(7.5h.P)N(7.5h.P)N(7.5h.)"),
                         ("sick", 0.0, 7.5))

    def test_not_leave(self):
        self.assertIsNone(parse_leave_cell(""))
        self.assertIsNone(parse_leave_cell(None))
        self.assertIsNone(parse_leave_cell("0600\n1400"))   # běžná směna


class ContractHoursTest(unittest.TestCase):
    def test_ftz_variants(self):
        self.assertEqual(contract_hours_from_tokens(["CAPANITCAIA", "Irina", "FTz4"]), 4.0)
        self.assertEqual(contract_hours_from_tokens(["X", "FTz5"]), 5.0)
        self.assertEqual(contract_hours_from_tokens(["X", "FTz6"]), 6.0)
        self.assertEqual(contract_hours_from_tokens(["X", "FTz4h"]), 4.0)
        self.assertEqual(contract_hours_from_tokens(["VAVRUŠOVÁ", "Eva", "FT4"]), 4.0)
        self.assertEqual(contract_hours_from_tokens(["DO", "Tuan", "Hung", "4h"]), 4.0)

    def test_decimal(self):
        self.assertEqual(contract_hours_from_tokens(["PLATOVA", "Olena", "(7,5)"]), 7.5)

    def test_none(self):
        self.assertIsNone(contract_hours_from_tokens(["BENONI", "Adam", "Vitold"]))
        self.assertIsNone(contract_hours_from_tokens(["PLIUSKOVA", "Mariia", "HPP"]))


class GridNameTest(unittest.TestCase):
    def test_plain_name(self):
        self.assertEqual(
            grid_name_from_tokens(["BENONI", "Adam", "Vitold"]),
            "BENONI Adam Vitold",
        )

    def test_strips_ftz_contract(self):
        self.assertEqual(
            grid_name_from_tokens(["CAPANITCAIA", "Irina", "FTz4"]),
            "CAPANITCAIA Irina",
        )

    def test_strips_hours_contract(self):
        self.assertEqual(
            grid_name_from_tokens(["DO", "Tuan", "Hung", "4h"]),
            "DO Tuan Hung",
        )

    def test_strips_hpp(self):
        self.assertEqual(
            grid_name_from_tokens(["PLIUSKOVA", "Mariia", "HPP"]),
            "PLIUSKOVA Mariia",
        )


if __name__ == "__main__":
    unittest.main()
