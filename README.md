# Počítadlo odpracovaných hodin 

> ⚠️ **BETA verze** – aplikace je funkční, ale stále se vyvíjí. Výsledky si
> radši ověř a případné nesrovnalosti dej vědět. Vzhled aplikace je v beta testingu.



## Co umí

- Načte více PDF najednou (vyber soubory nebo celou složku).
- Z každého rozpisu přečte jména a časy směn (např. `Novák Jan  9:00 – 17:30`).
- Sečte hodiny za každého zaměstnance přes všechna nahraná PDF.
- Spočítá zvlášť **hodiny o víkendu** (sobota + neděle).
- Počítá zvlášť **dovolenou** a **nemocenskou** podle **denního úvazku**:
  `D(1d)`/`PN(1d)` = celý den = úvazek toho člověka (4/5/6/7,5 h),
  `D(4h.)`/`PN(7.5h.)` = na hodiny. Úvazek se načte z PDF a kde chybí (nebo
  ho chceš přepsat), **doplníš ho ručně** v „Úvazky…“ (uloží se).
- Umí označit, kdo je **nezletilý** – stav se zobrazí ve sloupci „Zletilost“
  a uloží se, takže ho nastavuješ jen jednou.
- **Volitelná přestávka** – vybereš si z rozbalovacího seznamu (žádná / 15 /
  30 / 45 / 60 min / automaticky dle zákona: 30 min nad 6 h, nezletilí nad 4,5 h). Přestávka je globálně na všechny zaměstnance. 
- zvládá **noční směny přes půlnoc** (např. `22:00 – 6:00` = 8 h). Oddělí kolik hodin noční se dělalo přes víkend a týden.
- Export do **Excelu (.xlsx)** a **CSV**.

---

## Jak to spustit


### A) Sestavení aplikace 

1. Stáhni tento projekt přes code a vyber download ZIP a extrahuj .ZIP file a potom otevři **`build_exe.bat`**.
   Skript doinstaluje knihovny a **zkompiluje aplikaci Nuitkou** do složky
   `build_nuitka\main.dist\` se souborem `PocitadloHodin.exe`. (Nuitka si
   může poprvé stáhnout C kompilátor – potvrď stažení.) To znamená, že se aplikace "nainstaluje" :D

### B) Stažení Releases

  1. Zatím nefunkční.
---      



---

## Struktura projektu

```
mcdonalds/
├─ main.py                  # spouštěč – otevře okno aplikace
├─ build_exe.bat            # vytvoření .exe na Windows (Nuitka)
├─ requirements.txt         # potřebné knihovny
├─ hours_tracker/           # jádro aplikace
│  ├─ parser.py             #   čtení směn z PDF (zde se ladí formát)
│  ├─ aggregator.py         #   sčítání hodin po zaměstnancích
│  ├─ config.py             #   pravidla a volby pro přestávky
│  ├─ exporter.py           #   export do Excelu / CSV
│  ├─ store.py              #   uložení nastavení (nezletilí) mezi spuštěními
│  ├─ models.py             #   datové struktury
│  └─ gui.py                #   grafické okno (tkinter)
├─ tools/make_sample_pdfs.py# generátor ukázkových PDF
├─ sample_pdfs/             # ukázkové rozpisy (fiktivní jména)
└─ tests/                   # automatické testy (python -m unittest)
```

## Chyby

- Zatím žádné nenalezeny.
- Počítaní dovolené si nejsem jistý, prosím o kontrolu.
- Excel není přehledný.
- Chyby hlaste přes [GitHub Issues](https://github.com/Kulisekmatej/MCD/issues).
  
