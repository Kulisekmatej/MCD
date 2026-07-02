"""Konfigurace výpočtu – hlavně pravidla pro odečítání přestávek.

Časy ve směnách jsou v PDF obvykle uvedené jako "od–do" (např. 9:00–17:30).
Někdy je do nich přestávka započítaná, jindy ne. Proto je odečítání přestávek
volitelné a nastavitelné – uživatel ho v aplikaci zapíná zaškrtávátkem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class BreakConfig:
    """Pravidla pro odečítání přestávek z délky směny.

    mode:
        "none"  – nic se neodečítá, počítá se celá délka směny (výchozí).
        "fixed" – od každé směny (s nenulovou délkou) se odečte ``fixed_minutes``.
        "auto"  – odečte se přestávka podle délky směny dle pravidel níže.

    auto_rules / minor_auto_rules:
        Seznam dvojic (od_kolika_minut_směny, kolik_minut_odečíst). Aplikuje se
        poslední pravidlo, jehož hranici délka směny **překročí** (ostře >).
        Pro nezletilé se použijí ``minor_auto_rules`` (přísnější dle zákoníku
        práce – přestávka už po 4,5 h místo 6 h u dospělých). Kratší směny než
        hranice zůstanou bez odečtu (nemají nárok na přestávku).
    """

    mode: str = "none"
    fixed_minutes: int = 30
    # Dospělí: přestávka 30 min u směny delší než 6 h.
    auto_rules: List[Tuple[int, int]] = field(
        default_factory=lambda: [(6 * 60, 30)]
    )
    # Nezletilí: přestávka 30 min už u směny delší než 4,5 h.
    minor_auto_rules: List[Tuple[int, int]] = field(
        default_factory=lambda: [(int(4.5 * 60), 30)]
    )

    def break_minutes_for(self, span_minutes: int, is_minor: bool = False) -> int:
        """Kolik minut přestávky odečíst od směny dané délky (s ohledem na věk)."""
        if span_minutes <= 0:
            return 0
        if self.mode == "fixed":
            return min(self.fixed_minutes, span_minutes)
        if self.mode == "auto":
            rules = self.minor_auto_rules if is_minor else self.auto_rules
            applicable = 0
            for threshold, minutes in sorted(rules):
                if span_minutes > threshold:
                    applicable = minutes
            return min(applicable, span_minutes)
        return 0

    def worked_minutes(self, span_minutes: int, is_minor: bool = False) -> int:
        """Délka směny po odečtení přestávky (nikdy ne záporná)."""
        return max(0, span_minutes - self.break_minutes_for(span_minutes, is_minor))


# Volby přestávky nabízené v rozbalovacím seznamu v aplikaci.
BREAK_CHOICES = [
    "Žádná přestávka",
    "15 min",
    "30 min",
    "45 min",
    "60 min",
    "Automaticky dle zákona (6 h / nezletilí 4,5 h → 30 min)",
]


def break_config_for_choice(choice: str) -> "BreakConfig":
    """Převede volbu z rozbalovacího seznamu na :class:`BreakConfig`."""
    if choice.startswith("Automaticky"):
        return BreakConfig(mode="auto")  # výchozí pravidla: dospělí 6 h, nezletilí 4,5 h
    if choice and choice[0].isdigit():
        minutes = int(choice.split()[0])
        return BreakConfig(mode="fixed", fixed_minutes=minutes)
    return BreakConfig(mode="none")
