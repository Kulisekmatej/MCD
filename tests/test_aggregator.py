import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hours_tracker.aggregator import (  # noqa: E402
    aggregate,
    grand_total_minutes,
    is_weekend,
    night_minutes,
)
from hours_tracker.config import (  # noqa: E402
    BREAK_CHOICES,
    BreakConfig,
    break_config_for_choice,
)
from hours_tracker.models import Shift  # noqa: E402
from hours_tracker.parser import normalize_key  # noqa: E402


def shift(name, span, day=None):
    return Shift(employee=name, start_minutes=0, end_minutes=span,
                 span_minutes=span, day=day)


class AggregateTest(unittest.TestCase):
    def test_sum_across_shifts(self):
        shifts = [
            shift("Novák Jan", 8 * 60, date(2026, 6, 1)),
            shift("Novák Jan", 6 * 60, date(2026, 6, 2)),
            shift("Eva Černá", 5 * 60, date(2026, 6, 1)),
        ]
        totals = {t.employee: t for t in aggregate(shifts)}
        self.assertEqual(totals["Novák Jan"].total_minutes, 14 * 60)
        self.assertEqual(totals["Novák Jan"].shift_count, 2)
        self.assertEqual(totals["Novák Jan"].day_count, 2)
        self.assertEqual(totals["Eva Černá"].total_minutes, 5 * 60)

    def test_name_merge_case_and_spaces(self):
        shifts = [
            shift("Novák Jan", 60),
            shift("novák  jan", 60),
            shift("Novák Jan", 60),
        ]
        totals = aggregate(shifts)
        self.assertEqual(len(totals), 1)
        # Zobrazí se nejčastější tvar.
        self.assertEqual(totals[0].employee, "Novák Jan")
        self.assertEqual(totals[0].total_minutes, 180)

    def test_sorted_alphabetically(self):
        shifts = [shift("Zelený Petr", 60), shift("Adam Bílý", 60)]
        names = [t.employee for t in aggregate(shifts)]
        self.assertEqual(names, ["Adam Bílý", "Zelený Petr"])

    def test_break_auto_over_six_hours(self):
        cfg = BreakConfig(mode="auto", auto_rules=[(6 * 60, 30)])
        totals = aggregate([shift("A", 8 * 60), shift("B", 5 * 60)], cfg)
        by = {t.employee: t.total_minutes for t in totals}
        self.assertEqual(by["A"], 8 * 60 - 30)  # přesáhl 6 h -> -30 min
        self.assertEqual(by["B"], 5 * 60)        # pod 6 h -> beze změny

    def test_break_fixed(self):
        cfg = BreakConfig(mode="fixed", fixed_minutes=30)
        totals = aggregate([shift("A", 8 * 60)], cfg)
        self.assertEqual(totals[0].total_minutes, 8 * 60 - 30)

    def test_grand_total(self):
        totals = aggregate([shift("A", 60), shift("B", 120)])
        self.assertEqual(grand_total_minutes(totals), 180)


class WeekendTest(unittest.TestCase):
    SATURDAY = date(2026, 6, 6)
    MONDAY = date(2026, 6, 8)

    def test_is_weekend(self):
        self.assertTrue(is_weekend(self.SATURDAY))
        self.assertTrue(is_weekend(date(2026, 6, 7)))   # neděle
        self.assertFalse(is_weekend(self.MONDAY))
        self.assertFalse(is_weekend(None))

    def test_weekend_split(self):
        shifts = [shift("A", 8 * 60, self.SATURDAY), shift("A", 5 * 60, self.MONDAY)]
        t = aggregate(shifts)[0]
        self.assertEqual(t.total_minutes, 13 * 60)
        self.assertEqual(t.weekend_minutes, 8 * 60)
        self.assertEqual(t.weekday_minutes, 5 * 60)

    def test_no_date_not_weekend(self):
        t = aggregate([shift("A", 8 * 60, None)])[0]
        self.assertEqual(t.weekend_minutes, 0)


class NightTest(unittest.TestCase):
    def test_full_night_shift(self):
        # 22:00–06:00 = celá noční (8 h)
        self.assertEqual(night_minutes(22 * 60, 30 * 60), 8 * 60)

    def test_day_shift_no_night(self):
        # 06:00–14:30 a 14:00–22:00 = žádná noční
        self.assertEqual(night_minutes(6 * 60, 14 * 60 + 30), 0)
        self.assertEqual(night_minutes(14 * 60, 22 * 60), 0)

    def test_partial_evening(self):
        # 16:00–00:00 = noční jen 22:00–24:00 = 2 h
        self.assertEqual(night_minutes(16 * 60, 24 * 60), 2 * 60)

    def test_early_morning(self):
        # 00:00–06:00 = celé noční
        self.assertEqual(night_minutes(0, 6 * 60), 6 * 60)

    def test_aggregate_weekend_night(self):
        sat = date(2026, 6, 6)  # sobota
        night = Shift(employee="A", start_minutes=22 * 60, end_minutes=30 * 60,
                      span_minutes=8 * 60, kind="work", day=sat)
        t = aggregate([night])[0]
        self.assertEqual(t.night_minutes, 8 * 60)
        self.assertEqual(t.weekend_night_minutes, 8 * 60)
        self.assertEqual(t.weekend_minutes, 8 * 60)

    def test_aggregate_weekday_night_not_weekend(self):
        mon = date(2026, 6, 8)  # pondělí
        night = Shift(employee="A", start_minutes=22 * 60, end_minutes=30 * 60,
                      span_minutes=8 * 60, kind="work", day=mon)
        t = aggregate([night])[0]
        self.assertEqual(t.night_minutes, 8 * 60)
        self.assertEqual(t.weekend_night_minutes, 0)

    def test_friday_night_weekend_part_after_midnight(self):
        # Pá 22:00 – so 6:00: do víkendu patří jen sobotních 6 h po půlnoci.
        fri = date(2026, 6, 5)
        night = Shift(employee="A", start_minutes=22 * 60, end_minutes=30 * 60,
                      span_minutes=8 * 60, kind="work", day=fri)
        t = aggregate([night])[0]
        self.assertEqual(t.total_minutes, 8 * 60)
        self.assertEqual(t.weekend_minutes, 6 * 60)
        self.assertEqual(t.weekend_night_minutes, 6 * 60)

    def test_sunday_night_weekend_part_before_midnight(self):
        # Ne 22:00 – po 6:00: do víkendu patří jen nedělní 2 h před půlnocí.
        sun = date(2026, 6, 7)
        night = Shift(employee="A", start_minutes=22 * 60, end_minutes=30 * 60,
                      span_minutes=8 * 60, kind="work", day=sun)
        t = aggregate([night])[0]
        self.assertEqual(t.weekend_minutes, 2 * 60)
        self.assertEqual(t.weekend_night_minutes, 2 * 60)

    def test_night_never_exceeds_worked_with_break(self):
        # Noční 22:00–6:00 s auto přestávkou: noční hodiny nesmí přesáhnout
        # odpracovaný čas (přestávka se poměrně rozpočítá).
        cfg = BreakConfig(mode="auto")
        night = Shift(employee="A", start_minutes=22 * 60, end_minutes=30 * 60,
                      span_minutes=8 * 60, kind="work")
        t = aggregate([night], cfg)[0]
        self.assertEqual(t.total_minutes, 8 * 60 - 30)
        self.assertEqual(t.night_minutes, 8 * 60 - 30)
        self.assertLessEqual(t.night_minutes, t.total_minutes)


class MinorsTest(unittest.TestCase):
    def test_minor_flag(self):
        shifts = [shift("Mladý Jan", 60), shift("Starý Petr", 60)]
        minors = {normalize_key("mladý  jan")}
        totals = {t.employee: t for t in aggregate(shifts, minors=minors)}
        self.assertTrue(totals["Mladý Jan"].is_minor)
        self.assertEqual(totals["Mladý Jan"].status_label, "Nezletilý")
        self.assertFalse(totals["Starý Petr"].is_minor)
        self.assertEqual(totals["Starý Petr"].status_label, "Zletilý")

    def test_minor_gets_stricter_break_in_aggregate(self):
        # Stejná 5h směna: nezletilému se v auto režimu odečte pauza, dospělému ne.
        cfg = break_config_for_choice(BREAK_CHOICES[-1])
        shifts = [shift("Mladý Jan", 5 * 60), shift("Starý Petr", 5 * 60)]
        minors = {normalize_key("Mladý Jan")}
        totals = {t.employee: t for t in aggregate(shifts, cfg, minors)}
        self.assertEqual(totals["Mladý Jan"].total_minutes, 5 * 60 - 30)
        self.assertEqual(totals["Starý Petr"].total_minutes, 5 * 60)


class VacationTest(unittest.TestCase):
    def _vac_day(self, name, days, contract=None, day=None):
        return Shift(employee=name, start_minutes=0, end_minutes=0, span_minutes=0,
                     kind="vacation", leave_days=days, contract_hours=contract, day=day)

    def _vac_hours(self, name, hours, contract=None):
        return Shift(employee=name, start_minutes=0, end_minutes=0,
                     span_minutes=int(hours * 60), kind="vacation",
                     contract_hours=contract)

    def _sick_day(self, name, days, contract=None):
        return Shift(employee=name, start_minutes=0, end_minutes=0, span_minutes=0,
                     kind="sick", leave_days=days, contract_hours=contract)

    def test_vacation_separate_from_worked(self):
        shifts = [shift("A", 8 * 60), self._vac_hours("A", 8)]
        t = aggregate(shifts)[0]
        self.assertEqual(t.total_minutes, 8 * 60)        # jen práce
        self.assertEqual(t.vacation_minutes, 8 * 60)     # dovolená zvlášť
        self.assertEqual(t.shift_count, 1)               # dovolená není směna

    def test_vacation_day_uses_pdf_contract(self):
        # D(1d) u úvazku 6 h = 6 h.
        t = aggregate([self._vac_day("A", 1, contract=6)])[0]
        self.assertEqual(t.vacation_minutes, 6 * 60)
        self.assertEqual(t.contract_hours, 6)

    def test_vacation_day_default_when_unknown(self):
        # Bez úvazku (z PDF ani ručně) se použije výchozí 7,5 h.
        t = aggregate([self._vac_day("A", 1, contract=None)])[0]
        self.assertEqual(t.vacation_minutes, int(7.5 * 60))

    def test_manual_contract_overrides_pdf(self):
        # Ruční úvazek 4 h má přednost před PDF (6 h).
        shifts = [self._vac_day("Jan Novák", 1, contract=6)]
        contracts = {normalize_key("Jan Novák"): 4.0}
        t = aggregate(shifts, contracts=contracts)[0]
        self.assertEqual(t.vacation_minutes, 4 * 60)

    def test_sick_by_contract(self):
        t = aggregate([self._sick_day("A", 2, contract=5)])[0]
        self.assertEqual(t.sick_minutes, 2 * 5 * 60)
        self.assertEqual(t.vacation_minutes, 0)

    def test_pdf_contract_prefers_latest_date(self):
        # Když se úvazek mezi rozpisy změní, platí ten z nejnovějšího data –
        # bez ohledu na pořadí zpracování souborů.
        older = Shift(employee="A", start_minutes=8 * 60, end_minutes=16 * 60,
                      span_minutes=8 * 60, contract_hours=4, day=date(2026, 6, 1))
        newer = Shift(employee="A", start_minutes=8 * 60, end_minutes=16 * 60,
                      span_minutes=8 * 60, contract_hours=6, day=date(2026, 6, 8))
        vac = self._vac_day("A", 1, day=date(2026, 6, 9))
        t = aggregate([older, newer, vac])[0]
        self.assertEqual(t.contract_hours, 6)
        self.assertEqual(t.vacation_minutes, 6 * 60)
        # Stejný výsledek i při opačném pořadí souborů.
        t2 = aggregate([newer, older, vac])[0]
        self.assertEqual(t2.contract_hours, 6)

    def test_leave_no_break_applied(self):
        cfg = break_config_for_choice(BREAK_CHOICES[-1])
        t = aggregate([self._vac_day("A", 1, contract=8)], cfg)[0]
        self.assertEqual(t.vacation_minutes, 8 * 60)
        self.assertEqual(t.total_minutes, 0)


class BreakChoiceTest(unittest.TestCase):
    def test_none(self):
        self.assertEqual(break_config_for_choice("Žádná přestávka").mode, "none")

    def test_fixed(self):
        cfg = break_config_for_choice("30 min")
        self.assertEqual(cfg.mode, "fixed")
        self.assertEqual(cfg.worked_minutes(8 * 60), 8 * 60 - 30)

    def test_fixed_15(self):
        self.assertEqual(break_config_for_choice("15 min").worked_minutes(8 * 60),
                         8 * 60 - 15)

    def test_auto(self):
        cfg = break_config_for_choice(BREAK_CHOICES[-1])  # automatická volba
        self.assertEqual(cfg.mode, "auto")
        # Dospělý: přestávka až u směny delší než 6 h.
        self.assertEqual(cfg.worked_minutes(8 * 60), 8 * 60 - 30)
        self.assertEqual(cfg.worked_minutes(6 * 60), 6 * 60)      # přesně 6 h → bez pauzy
        self.assertEqual(cfg.worked_minutes(5 * 60), 5 * 60)

    def test_auto_minor_stricter(self):
        cfg = break_config_for_choice(BREAK_CHOICES[-1])
        # Nezletilý: přestávka už u směny delší než 4,5 h.
        self.assertEqual(cfg.worked_minutes(5 * 60, is_minor=True), 5 * 60 - 30)
        self.assertEqual(cfg.worked_minutes(4 * 60, is_minor=True), 4 * 60)  # 4 h → bez pauzy
        # Stejná 5h směna dospělého zůstane bez odečtu.
        self.assertEqual(cfg.worked_minutes(5 * 60, is_minor=False), 5 * 60)


if __name__ == "__main__":
    unittest.main()
