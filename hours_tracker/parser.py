"""Čtení směn z PDF rozpisu.

Podporuje dva formáty:

1. **Mřížkový rozpis z mymcd.eu** (:func:`_parse_grid_page`) – tabulka, kde
   řádek = zaměstnanec a sloupce 1–14 jsou dny; v buňce je směna ve tvaru
   ``HHMM`` start nahoře a konec dole (např. ``1600`` / ``0000`` = 16:00–24:00).
   Datum dne se odvodí z období v titulku ("Rozpis směn 01.06.2026 - 14.06.2026").
2. **Jednoduchý řádkový formát** (:func:`parse_shifts_from_text`) – na řádku je
   jméno a za ním časový rozsah "od–do" (``Novák Jan 9:00 - 17:30``). Slouží
   jako záloha, když PDF není mřížka.

:func:`parse_pdf` zkusí nejdřív mřížku; když nic nenajde, použije řádkový parser.
"""

from __future__ import annotations

import os
import re
from datetime import date, timedelta
from typing import List, Optional, Tuple

from .models import Shift

# --- regulární výrazy -------------------------------------------------------

# Čas: 0–23 hodin, 00–59 minut; oddělovač ":" nebo ".".
_TIME = r"(?:[01]?\d|2[0-3])[:.][0-5]\d"

# Časový rozsah "od–do".
_RANGE_RE = re.compile(
    r"(" + _TIME + r")\s*(?:-|–|—|až|do)\s*(" + _TIME + r")",
    re.IGNORECASE,
)

# Datum dd.mm.yyyy nebo dd.mm. (rok nepovinný) – pro popis období.
_DATE_RE = re.compile(
    r"\b(3[01]|[12]\d|0?[1-9])\.\s*(1[0-2]|0?[1-9])\.\s*((?:19|20)\d{2})?"
)
# Datum ve tvaru ISO 2024-06-01 (typicky v názvu souboru).
# Bez \b – v názvu typu "rozpis_2026-06-01" je před rokem podtržítko (slovní znak).
_ISO_DATE_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})-(\d{2})-(\d{2})(?!\d)")

# Období mřížkového rozpisu: "01.06.2026 - 14.06.2026" -> začátek období.
_PERIOD_RE = re.compile(
    r"(\d{1,2})\.\s*(\d{1,2})\.\s*((?:19|20)\d{2})\s*[-–—]\s*"
    r"\d{1,2}\.\s*\d{1,2}\.\s*(?:19|20)\d{2}"
)

# Označení úvazku / sekcí, která nejsou součástí jména zaměstnance.
_CONTRACT_LABELS = {"HPP", "DPP", "DPČ", "DPC", "FT", "PT", "Mng"}
_SECTION_LABELS = {"Crew", "DOH", "TPPs", "Manager", "Maintenance"}

# Výchozí denní úvazek (h) pro 1 den dovolené/nemocenské, když úvazek není
# v PDF a uživatel ho ani ručně nedoplnil.
DEFAULT_CONTRACT_HOURS = 7.5
# Dovolená (D) i nemocenská (PN): D(1d)/PN(1d) = celé dny, D(4h.)/PN(7.5h.) = hodiny.
_LEAVE_RE = re.compile(r"(D|PN)\(\s*(\d+(?:[.,]\d+)?)\s*(d|h)", re.IGNORECASE)
# Číslo úvazku z tokenu typu FTz4 / FT4 / 4h / (7,5).
_CONTRACT_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")

# Slova, která neoznačují zaměstnance (hlavičky, souhrny, přestávky).
_STOPWORDS = {
    "jmeno", "jméno", "prijmeni", "příjmení", "jmenoaprijmeni",
    "pozice", "pozn", "poznamka", "poznámka", "datum", "den",
    "smena", "směna", "smeny", "směny", "rozpis", "celkem", "total",
    "soucet", "součet", "hodiny", "hod", "pauza", "přestávka", "prestavka",
    "break", "od", "do", "obsazeni", "obsazení",
}


def _to_minutes(token: str) -> int:
    """"9:00" / "9.00" -> minuty od půlnoci."""
    h, m = re.split(r"[:.]", token)
    return int(h) * 60 + int(m)


def _normalize_key(name: str) -> str:
    """Klíč pro slučování stejných lidí (bez ohledu na velikost písmen / mezery)."""
    return re.sub(r"\s+", " ", name).strip().lower()


def _looks_like_name(text: str) -> bool:
    """Heuristika: vypadá řetězec jako jméno zaměstnance?"""
    letters = re.findall(r"[^\W\d_]", text, re.UNICODE)
    if len(letters) < 3:
        return False
    compact = re.sub(r"[^\w]", "", text, flags=re.UNICODE).lower()
    if compact in _STOPWORDS:
        return False
    # Řádek tvořený jen jedním stopword slovem (např. "Celkem") přeskočíme.
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    if words and all(re.sub(r"[^\w]", "", w, flags=re.UNICODE).lower() in _STOPWORDS
                     for w in words):
        return False
    return True


def _clean_name(raw: str) -> str:
    """Očistí text před časem na pravděpodobné jméno."""
    name = raw.replace("|", " ").replace("\t", " ")
    # Pryč s vedoucím číslováním / odrážkami ("1.", "12)", "-", "•").
    name = re.sub(r"^[\s\d.)\-•·*]+", "", name)
    name = re.sub(r"\s+", " ", name).strip(" .,-–—|:;")
    return name


def parse_date_from_filename(filename: str) -> Optional[date]:
    """Zkusí získat datum z názvu souboru (ISO i dd.mm.yyyy)."""
    base = os.path.basename(filename)
    iso = _ISO_DATE_RE.search(base)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            pass
    m = _DATE_RE.search(base)
    if m and m.group(3):
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


def _find_date_in_line(line: str, default_year: Optional[int]) -> Optional[date]:
    iso = _ISO_DATE_RE.search(line)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            pass
    m = _DATE_RE.search(line)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        year_int = int(year) if year else default_year
        if year_int is None:
            return None
        try:
            return date(year_int, int(month), int(day))
        except ValueError:
            return None
    return None


def parse_shifts_from_text(
    text: str,
    source_file: Optional[str] = None,
    default_date: Optional[date] = None,
) -> List[Shift]:
    """Najde v textu řádky se jménem a časovým rozsahem a vrátí směny.

    Pokud je na řádku víc časových rozsahů, bere se rozpětí od nejdřívějšího
    začátku po nejpozdější konec (tj. celé časové okno směny).
    """
    shifts: List[Shift] = []
    current_date = default_date
    default_year = default_date.year if default_date else None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Aktualizuj aktuální datum, pokud řádek datum obsahuje (hlavička dne).
        found_date = _find_date_in_line(line, default_year)
        if found_date is not None:
            current_date = found_date

        ranges = list(_RANGE_RE.finditer(line))
        if not ranges:
            continue

        # Jméno = text před prvním časovým rozsahem na řádku.
        name = _clean_name(line[: ranges[0].start()])
        if not _looks_like_name(name):
            continue

        starts = [_to_minutes(r.group(1)) for r in ranges]
        ends = [_to_minutes(r.group(2)) for r in ranges]
        start_min = min(starts)
        end_min = max(ends)

        # Přes půlnoc (např. 22:00–6:00): k délce se přičte 24 h.
        span = end_min - start_min
        if span <= 0:
            span += 24 * 60

        shifts.append(
            Shift(
                employee=name,
                start_minutes=start_min,
                end_minutes=end_min if end_min > start_min else end_min + 24 * 60,
                span_minutes=span,
                day=current_date,
                source_file=source_file,
                raw_line=line,
            )
        )

    return shifts


# --- mřížkový formát (mymcd.eu) --------------------------------------------

def parse_period_start(text: str) -> Optional[date]:
    """Z textu "Rozpis směn 01.06.2026 - 14.06.2026" vrátí počáteční datum."""
    m = _PERIOD_RE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _hhmm_to_minutes(token: str) -> Optional[int]:
    """"1600" -> 960. Vrátí None pro neplatný čas."""
    h, m = int(token[:2]), int(token[2:])
    if h > 24 or m > 59:
        return None
    return h * 60 + m


def parse_cell_shift(cell: Optional[str]) -> Optional[Tuple[int, int, int]]:
    """Z buňky mřížky (``"1600\\n0000"``) vrátí (start, konec, délka) v minutách.

    Prázdná buňka, kód absence (``D(1d)``) apod. vrátí ``None``. Směny přes
    půlnoc (konec <= začátek, např. ``2200``/``0600`` nebo ``1600``/``0000``)
    se ošetří přičtením 24 h k délce.
    """
    if not cell:
        return None
    nums = re.findall(r"\d{4}", cell)
    if len(nums) != 2:
        return None
    start = _hhmm_to_minutes(nums[0])
    end = _hhmm_to_minutes(nums[1])
    if start is None or end is None:
        return None
    span = end - start
    if span <= 0:
        span += 24 * 60
    return start, end, span


def contract_hours_from_tokens(tokens: List[str]) -> Optional[float]:
    """Z tokenů jmenného sloupce vytáhne denní úvazek v hodinách.

    Rozpozná ``FTz4``/``FT4``/``4h`` = 4, ``FTz5`` = 5, ``FTz6`` = 6,
    ``(7,5)`` = 7,5. ``HPP`` (bez čísla) vrátí ``None`` (= doplní se ručně /
    výchozí). Jména číslice neobsahují, takže číselný token = úvazek.
    """
    for tk in tokens:
        m = _CONTRACT_NUM_RE.search(tk)
        if m:
            try:
                return float(m.group().replace(",", "."))
            except ValueError:
                continue
    return None


def parse_leave_cell(cell: Optional[str]) -> Optional[Tuple[str, float, float]]:
    """Z buňky volna vrátí ``(druh, dny, hodiny)``.

    ``druh`` je "vacation" (D) nebo "sick" (PN). Buď ``dny`` (D(1d)/PN(1d)),
    nebo ``hodiny`` (D(4h.)/PN(7.5h.)) – ten druhý je 0. Vrací ``None``, pokud
    buňka volno není.
    """
    if not cell:
        return None
    m = _LEAVE_RE.search(cell.replace("\n", ""))
    if not m:
        return None
    kind = "vacation" if m.group(1).upper() == "D" else "sick"
    value = float(m.group(2).replace(",", "."))
    unit = m.group(3).lower()
    if unit == "d":
        return kind, value, 0.0
    return kind, 0.0, value


def grid_name_from_tokens(tokens: List[str]) -> str:
    """Z textových tokenů jmenného sloupce poskládá jméno.

    Vynechá typy úvazku (``FTz4``, ``4h``, ``HPP`` …) a cokoli s číslicí.
    """
    out = []
    for tk in tokens:
        if any(ch.isdigit() for ch in tk):
            continue
        if tk in _CONTRACT_LABELS or tk.startswith("FTz"):
            continue
        out.append(tk)
    return " ".join(out).strip()


def _parse_grid_page(page, source_file: Optional[str]) -> List[Shift]:
    """Přečte směny z jedné stránky mřížkového rozpisu (mymcd.eu)."""
    text = page.extract_text() or ""
    tables = page.find_tables()
    if not tables:
        return []
    table = tables[0]
    # Bezpečnostní brzda: jako mřížku čti jen tento typ rozpisu (mymcd.eu).
    # Titulek "Rozpis směn …" je na každé stránce; u jiných PDF se vrátí []
    # a použije se záložní řádkový parser.
    if "Rozpis směn" not in text:
        return []
    header = table.rows[0].cells if table.rows else []
    if len(header) < 2 or not header[1]:
        return []
    name_x1 = header[1][0]  # levý okraj prvního denního sloupce
    start_date = parse_period_start(text)
    # x-rozsahy denních sloupců (pro rekonstrukci buněk ze slov – kvůli PN).
    col_ranges = {
        j: (header[j][0], header[j][2])
        for j in range(1, len(header))
        if header[j]
    }

    try:
        data = page.extract_table()
    except Exception:  # noqa: BLE001
        return []
    if not data or len(data) < 2:
        return []

    words = page.extract_words()
    shifts: List[Shift] = []
    n = min(len(data), len(table.rows))
    for ri in range(1, n):
        cells = data[ri]
        bbox = table.rows[ri].bbox
        top, bot = bbox[1], bbox[3]
        in_row = [w for w in words if top - 1 <= (w["top"] + w["bottom"]) / 2 <= bot + 1]
        tokens = [w["text"] for w in in_row if w["x0"] < name_x1]
        name = grid_name_from_tokens(tokens)
        if not name or name in _SECTION_LABELS:
            continue
        contract = contract_hours_from_tokens(tokens)

        def raw_cell(j: int) -> str:
            """Text buňky poskládaný přímo ze slov (spolehlivější pro PN)."""
            rng = col_ranges.get(j)
            if not rng:
                return ""
            x0, x1 = rng
            ws = [w for w in in_row
                  if w["x0"] >= name_x1 and x0 - 0.5 <= (w["x0"] + w["x1"]) / 2 < x1 + 0.5]
            ws.sort(key=lambda w: (w["top"], w["x0"]))
            return "".join(w["text"] for w in ws)

        for j in range(1, min(15, len(cells))):
            cell = cells[j]
            day = start_date + timedelta(days=j - 1) if start_date else None
            parsed = parse_cell_shift(cell)
            if parsed:
                start, end, span = parsed
                shifts.append(
                    Shift(
                        employee=name,
                        start_minutes=start,
                        end_minutes=end if end > start else end + 24 * 60,
                        span_minutes=span,
                        kind="work",
                        contract_hours=contract,
                        day=day,
                        source_file=source_file,
                        raw_line=(cell or "").replace("\n", "-"),
                    )
                )
                continue
            # Není směna – zkus volno (dovolená D / nemocenská PN) ze slov.
            leave = parse_leave_cell(raw_cell(j))
            if leave:
                kind, days, hours = leave
                shifts.append(
                    Shift(
                        employee=name,
                        start_minutes=0,
                        end_minutes=0,
                        span_minutes=int(round(hours * 60)),
                        kind=kind,
                        leave_days=days,
                        contract_hours=contract,
                        day=day,
                        source_file=source_file,
                        raw_line=raw_cell(j),
                    )
                )
    return shifts


# --- veřejné API -----------------------------------------------------------

def extract_text_from_pdf(path: str) -> str:
    """Vytáhne text ze všech stránek PDF. Vyžaduje knihovnu ``pdfplumber``."""
    import pdfplumber  # import uvnitř, ať jádro jde naimportovat i bez knihovny

    parts: List[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def parse_pdf(path: str) -> List[Shift]:
    """Přečte jeden PDF soubor a vrátí seznam směn.

    Nejdřív zkusí mřížkový formát (mymcd.eu); pokud nic nenajde, použije
    jednoduchý řádkový parser nad textem.
    """
    import pdfplumber

    shifts: List[Shift] = []
    texts: List[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            shifts.extend(_parse_grid_page(page, source_file=path))
            texts.append(page.extract_text() or "")
    if shifts:
        return shifts

    # Záloha: řádkový formát.
    return parse_shifts_from_text(
        "\n".join(texts), source_file=path, default_date=parse_date_from_filename(path)
    )


# Pomocné re-exporty pro testy a další moduly.
normalize_key = _normalize_key
