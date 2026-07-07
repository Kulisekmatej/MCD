"""Ukládání nastavení aplikace mezi spuštěními.

Zatím se ukládá hlavně seznam zaměstnanců označených jako nezletilí, aby ho
uživatel nemusel nastavovat pokaždé znovu. Ukládá se do domovské složky
uživatele do ``~/.pocitadlo_hodin/settings.json`` (funguje i pro .exe).
"""

from __future__ import annotations

import json
import os
from typing import Dict

from .parser import normalize_key

_DIR = os.path.join(os.path.expanduser("~"), ".pocitadlo_hodin")
_PATH = os.path.join(_DIR, "settings.json")


def _load() -> dict:
    try:
        with open(_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    os.makedirs(_DIR, exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def load_minors() -> Dict[str, str]:
    """Vrátí slovník {normalizovaný_klíč: zobrazené_jméno} nezletilých."""
    data = _load()
    minors = data.get("minors", {})
    if not isinstance(minors, dict):
        return {}
    # Klíče pro jistotu znovu znormalizujeme.
    return {normalize_key(name): name for name in minors.values()}


def save_minors(minors: Dict[str, str]) -> None:
    """Uloží slovník {klíč: zobrazené_jméno} nezletilých."""
    data = _load()
    data["minors"] = {normalize_key(name): name for name in minors.values()}
    _save(data)


def load_contracts() -> Dict[str, float]:
    """Vrátí ruční úvazky {normalizovaný_klíč jména: hodiny/den}."""
    data = _load()
    raw = data.get("contracts", {})
    out: Dict[str, float] = {}
    if isinstance(raw, dict):
        for name, hours in raw.items():
            try:
                out[normalize_key(name)] = float(hours)
            except (TypeError, ValueError):
                continue
    return out


def save_contracts(contracts: Dict[str, float]) -> None:
    """Uloží ruční úvazky {jméno: hodiny/den}."""
    data = _load()
    data["contracts"] = {name: float(h) for name, h in contracts.items()}
    _save(data)


def settings_file() -> str:
    """Cesta k souboru s nastavením (pro zobrazení uživateli)."""
    return _PATH
