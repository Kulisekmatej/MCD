"""Sečtení směn na souhrn hodin za jednotlivé zaměstnance."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .config import BreakConfig
from .models import EmployeeTotal, Shift
from .parser import DEFAULT_CONTRACT_HOURS, normalize_key


def is_weekend(day) -> bool:
    """True, pokud datum připadá na sobotu nebo neděli."""
    return day is not None and day.weekday() >= 5


# Noční doba dle zákoníku práce: 22:00–6:00.
_NIGHT_WINDOWS = [(0, 6 * 60), (22 * 60, 24 * 60), (24 * 60, 30 * 60)]


def night_minutes(start_minutes: int, end_minutes: int) -> int:
    """Kolik minut směny [start, end] padne do noční doby (22:00–6:00).

    ``end_minutes`` může být > 1440 (směna přes půlnoc), proto se kontroluje
    i noční okno následujícího rána (24:00–30:00 = 0:00–6:00 dalšího dne).
    """
    total = 0
    for win_start, win_end in _NIGHT_WINDOWS:
        total += max(0, min(end_minutes, win_end) - max(start_minutes, win_start))
    return total


def _split_at_midnight(
    day: Optional[date], start_minutes: int, end_minutes: int
) -> List[Tuple[Optional[date], int, int]]:
    """Rozdělí interval směny na části před půlnocí a po ní (s jejich daty).

    Směna pátek 22:00–6:00 se tak rozpadne na pá 22:00–24:00 a so 0:00–6:00,
    aby se víkendové hodiny přiřadily správnému dni.
    """
    if end_minutes <= 24 * 60:
        return [(day, start_minutes, end_minutes)]
    next_day = day + timedelta(days=1) if day is not None else None
    return [(day, start_minutes, 24 * 60), (next_day, 24 * 60, end_minutes)]


def aggregate(
    shifts: Iterable[Shift],
    break_config: Optional[BreakConfig] = None,
    minors: Optional[Set[str]] = None,
    contracts: Optional[Dict[str, float]] = None,
    default_contract_hours: float = DEFAULT_CONTRACT_HOURS,
) -> List[EmployeeTotal]:
    """Sečte směny podle zaměstnance.

    Vrací seznam :class:`EmployeeTotal` seřazený abecedně podle jména.
    Jména se slučují bez ohledu na velikost písmen a přebytečné mezery.

    ``minors`` je množina normalizovaných klíčů nezletilých.
    ``contracts`` je ruční přepsání denního úvazku (klíč jména → hodiny);
    má přednost před úvazkem načteným z PDF. Den dovolené/nemocenské (D(1d)/
    PN(1d)) se počítá jako (úvazek × hodiny); ``default_contract_hours`` se
    použije, když úvazek není znám ani ručně, ani z PDF.
    """
    break_config = break_config or BreakConfig()
    minors = minors or set()
    contracts = contracts or {}

    totals: Dict[str, int] = {}
    weekend: Dict[str, int] = {}
    night: Dict[str, int] = {}
    weekend_night: Dict[str, int] = {}
    shift_counts: Dict[str, int] = {}
    days: Dict[str, set] = {}
    # Volno rozdělené na hodinové (přímo) a denní (× úvazek až nakonec).
    vac_hours_min: Dict[str, int] = {}
    vac_days: Dict[str, float] = {}
    sick_hours_min: Dict[str, int] = {}
    sick_days: Dict[str, float] = {}
    # Úvazek z PDF: {klíč: (datum směny, hodiny)} – při konfliktu mezi rozpisy
    # vyhrává úvazek z nejnovějšího data (bez data jen jako záloha).
    detected_contract: Dict[str, Tuple[Optional[date], float]] = {}
    name_variants: Dict[str, Dict[str, int]] = {}

    for shift in shifts:
        key = normalize_key(shift.employee)
        if not key:
            continue
        # Zaregistruj zaměstnance (ať se objeví i ten, kdo má jen volno).
        totals.setdefault(key, 0)
        days.setdefault(key, set())
        shift_counts.setdefault(key, 0)
        variants = name_variants.setdefault(key, {})
        variants[shift.employee] = variants.get(shift.employee, 0) + 1
        if shift.contract_hours is not None:
            prev = detected_contract.get(key)
            if prev is None or (
                shift.day is not None and (prev[0] is None or shift.day >= prev[0])
            ):
                detected_contract[key] = (shift.day, shift.contract_hours)

        if shift.kind in ("vacation", "sick"):
            hours_bucket = vac_hours_min if shift.kind == "vacation" else sick_hours_min
            days_bucket = vac_days if shift.kind == "vacation" else sick_days
            hours_bucket[key] = hours_bucket.get(key, 0) + shift.span_minutes
            days_bucket[key] = days_bucket.get(key, 0.0) + shift.leave_days
            continue

        # Nezletilí mají dle zákona přísnější nárok na přestávku (už od 4,5 h).
        worked = break_config.worked_minutes(shift.span_minutes, is_minor=key in minors)
        totals[key] += worked
        # Přestávka se poměrně rozpočítá i do noční/víkendové části, aby žádná
        # dílčí kategorie nemohla přesáhnout celkově odpracovaný čas.
        ratio = worked / shift.span_minutes if shift.span_minutes > 0 else 0.0
        nm = int(round(night_minutes(shift.start_minutes, shift.end_minutes) * ratio))
        if nm:
            night[key] = night.get(key, 0) + nm
        # Směna přes půlnoc se pro víkend rozdělí: každá část se přiřadí dni,
        # do kterého skutečně spadá (pá 22:00–so 6:00 → víkend jen sobotních 6 h).
        for part_day, seg_start, seg_end in _split_at_midnight(
            shift.day, shift.start_minutes, shift.end_minutes
        ):
            if not is_weekend(part_day):
                continue
            weekend[key] = weekend.get(key, 0) + int(round((seg_end - seg_start) * ratio))
            seg_night = night_minutes(seg_start, seg_end)
            if seg_night:
                weekend_night[key] = (
                    weekend_night.get(key, 0) + int(round(seg_night * ratio))
                )
        shift_counts[key] += 1
        if shift.day is not None:
            days[key].add(shift.day)

    result: List[EmployeeTotal] = []
    for key, minutes in totals.items():
        display = max(name_variants[key].items(), key=lambda kv: kv[1])[0]
        # Ruční úvazek má přednost; testuje se členstvím (ne přes "or"),
        # aby fungovala i hodnota 0.
        if key in contracts:
            contract = contracts[key]
        else:
            detected = detected_contract.get(key)
            contract = detected[1] if detected is not None else None
        eff = contract if contract is not None else default_contract_hours
        day_min = eff * 60
        vacation_min = vac_hours_min.get(key, 0) + int(round(vac_days.get(key, 0.0) * day_min))
        sick_min = sick_hours_min.get(key, 0) + int(round(sick_days.get(key, 0.0) * day_min))
        result.append(
            EmployeeTotal(
                employee=display,
                total_minutes=minutes,
                shift_count=shift_counts[key],
                day_count=len(days[key]),
                weekend_minutes=weekend.get(key, 0),
                vacation_minutes=vacation_min,
                sick_minutes=sick_min,
                night_minutes=night.get(key, 0),
                weekend_night_minutes=weekend_night.get(key, 0),
                is_minor=key in minors,
                contract_hours=contract,
            )
        )

    result.sort(key=lambda e: normalize_key(e.employee))
    return result


def grand_total_minutes(totals: Iterable[EmployeeTotal]) -> int:
    return sum(t.total_minutes for t in totals)


def date_range(shifts: Iterable[Shift]) -> Tuple[Optional[object], Optional[object]]:
    """Vrátí (nejstarší, nejnovější) datum směn, pokud jsou data dostupná."""
    dates = [s.day for s in shifts if s.day is not None]
    if not dates:
        return None, None
    return min(dates), max(dates)
