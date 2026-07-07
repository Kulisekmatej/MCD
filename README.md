##Počítadlo odpracovaných hodin

⚠️ **Beta verze – aplikace funguje, ale pořád se na ní pracuje. Radši si výsledky překontroluj a když narazíš na nesrovnalosti, dej vědět.**

## Co to umí
Hromadné načítání PDF: Nahraješ víc souborů najednou (vybereš je z disku nebo rovnou celou složku).
Čtení směn: Z každého rozpisu vytáhne jména a časy (např. Novák Jan 9:00 – 17:30).
Sčítání: Sečte hodiny za každého zaměstnance přes všechna nahraná PDF.
Víkendy: Spočítá zvlášť, kolik kdo odpracoval o víkendu (so + ne).
Dovolená a nemocenská: Počítá se to podle úvazku. D(1d)/PN(1d) znamená celý den (odpovídá 4/5/6/7,5 h podle úvazku daného člověka), D(4h.)/PN(7.5h.) se spočítá přesně na hodiny. Úvazek se zkusí načíst z PDF. Kde to nejde (nebo ho chceš přepsat), nastavíš ho ručně v „Úvazky…“ a aplikace si ho zapamatuje.
Nezletilí: Označíš je jednou a stav se uloží. Ve výsledcích pak vidíš sloupec „Zletilost“.
Přestávky: Globální nastavení pro všechny – žádná / 15 / 30 / 45 / 60 min, nebo „automaticky dle zákona“ (30 min nad 6 h, nezletilí nad 4,5 h).
Noční směny: Zvládne i ty přes půlnoc (např. 22:00 – 6:00 = 8 h). Navíc je dokáže rozdělit, kolik z noční hodiny padlo přes víkend a kolik přes týden.
Export: Výsledky můžeš vyhodit do Excelu (.xlsx) nebo CSV.

## Jak to spustit
#A) Zbuildění aplikace (Windows)
Stáhni si zdrojáky (zelené tlačítko Code -> Download ZIP), rozbal a spusť build_exe.bat. Skript doinstaluje knihovny a přes Nuitku zkompiluje exečku do složky build_nuitka\main.dist\PocitadloHodin.exe.
(Poznámka: Nuitka si pri prvním spuštění může stáhnout C kompilátor, to jen potvrď.)

#B) Přes Releases
Zatím to tu ještě není.

##Struktura projektu

MCD/
├─ main.py                   # spouštěč – otevře okno aplikace
├─ build_exe.bat             # vytvoření .exe na Windows (Nuitka)
├─ requirements.txt          # potřebné knihovny
├─ hours_tracker/            # jádro aplikace
│  ├─ parser.py              # čtení směn z PDF (zde se ladí formát)
│  ├─ aggregator.py          # sčítání hodin po zaměstnancích
│  ├─ config.py              # pravidla a volby pro přestávky
│  ├─ exporter.py            # export do Excelu / CSV
│  ├─ store.py               # ukládání nastavení mezi spuštěními
│  ├─ models.py              # datové struktury
│  └─ gui.py                 # grafické okno (tkinter)
├─ tools/
│  └─ make_sample_pdfs.py    # generátor ukázkových PDF
├─ sample_pdfs/              # ukázkové rozpisy (fiktivní data)
└─ tests/                    # testy (spustíš přes python -m unittest)

##Známé problémy
V červenci 2026 jsem projel kód a opravil 9 chyb (detaily jsou v BUG_REPORT.md – šlo hlavně o pád dialogu „Nezletilí…“ a špatný počet nočních hodin přes víkend).
Logika pro výpočet dovolené a nemocenský je otestovaná a měla by být v pohodě (dny × úvazek, hodiny přímo, ruční úvazek má přednost).
Výstup do Excelu zatím není úplně hezky naformátovanej.
Pokud najdeš nějaký nový bug, hoď ho prosím do GitHub Issues.
