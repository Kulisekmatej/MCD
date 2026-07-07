"""Datové struktury používané napříč aplikací."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


def format_hm(total_minutes: int) -> str:
    """Naformátuje minuty jako ``h:mm`` (např. 450 -> "7:30")."""
    sign = "-" if total_minutes < 0 else ""
    total_minutes = abs(int(total_minutes))
    return f"{sign}{total_minutes // 60}:{total_minutes % 60:02d}"


def to_hours(total_minutes: int) -> float:
    """Převede minuty na desetinné hodiny zaokrouhlené na 2 místa (450 -> 7.5)."""
    return round(total_minutes / 60.0, 2)


@dataclass
class Shift:
    """Jedna směna jednoho zaměstnance přečtená z PDF.

    start_minutes / end_minutes jsou minuty od půlnoci. Pokud směna přechází
    přes půlnoc (konec <= začátek), je to ošetřeno už při vytváření (k délce
    se přičte 24 h), takže ``span_minutes`` je vždy korektní.
    """

    employee: str
    start_minutes: int
    end_minutes: int
    span_minutes: int
    kind: str = "work"   # "work" = směna, "vacation" = dovolená, "sick" = nemocenská
    leave_days: float = 0.0          # počet dní volna (D(1d)/PN(1d)); 0 = zadáno v hodinách
    contract_hours: Optional[float] = None  # denní úvazek z PDF (h), pokud uveden
    day: Optional[date] = None
    source_file: Optional[str] = None
    raw_line: str = ""

    @property
    def start_hm(self) -> str:
        return format_hm(self.start_minutes)

    @property
    def end_hm(self) -> str:
        return format_hm(self.end_minutes % (24 * 60))


@dataclass
class EmployeeTotal:
    """Souhrn za jednoho zaměstnance."""

    employee: str
    total_minutes: int
    shift_count: int
    day_count: int
    weekend_minutes: int = 0
    vacation_minutes: int = 0
    sick_minutes: int = 0
    night_minutes: int = 0           # práce v noční době (22:00–6:00)
    weekend_night_minutes: int = 0   # z toho připadající na víkend
    is_minor: bool = False
    contract_hours: Optional[float] = None   # použitý denní úvazek (h)

    @property
    def hours(self) -> float:
        return to_hours(self.total_minutes)

    @property
    def night_hm(self) -> str:
        return format_hm(self.night_minutes)

    @property
    def night_hours(self) -> float:
        return to_hours(self.night_minutes)

    @property
    def weekend_night_hm(self) -> str:
        return format_hm(self.weekend_night_minutes)

    @property
    def weekend_night_hours(self) -> float:
        return to_hours(self.weekend_night_minutes)

    @property
    def vacation_hours(self) -> float:
        return to_hours(self.vacation_minutes)

    @property
    def vacation_hm(self) -> str:
        return format_hm(self.vacation_minutes)

    @property
    def sick_hours(self) -> float:
        return to_hours(self.sick_minutes)

    @property
    def sick_hm(self) -> str:
        return format_hm(self.sick_minutes)

    @property
    def contract_label(self) -> str:
        if self.contract_hours is None:
            return "—"
        h = self.contract_hours
        return f"{h:g} h"

    @property
    def hm(self) -> str:
        return format_hm(self.total_minutes)

    @property
    def weekday_minutes(self) -> int:
        """Hodiny mimo víkend (po–pá)."""
        return self.total_minutes - self.weekend_minutes

    @property
    def weekend_hours(self) -> float:
        return to_hours(self.weekend_minutes)

    @property
    def weekend_hm(self) -> str:
        return format_hm(self.weekend_minutes)

    @property
    def weekday_hm(self) -> str:
        return format_hm(self.weekday_minutes)

    @property
    def status_label(self) -> str:
        return "Nezletilý" if self.is_minor else "Zletilý"
