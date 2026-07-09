"""Grafické okno aplikace (tkinter).

Okno umožní přidat PDF soubory (nebo celou složku), spočítat odpracované
hodiny a výsledek vyexportovat do Excelu nebo CSV. Vlastní čtení PDF běží
ve vlákně na pozadí, aby okno během práce nezamrzlo.

Rozvržení: vlevo panel se soubory a nastavením (kroky 1–2–3), vpravo
tabulka výsledků s vyhledáváním, řazením podle sloupců a souhrnnými
kartami dole.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from . import __version__ as VERSION
from . import store, updater
from .aggregator import aggregate, date_range, grand_total_minutes
from .config import BREAK_CHOICES, BreakConfig, break_config_for_choice
from .models import EmployeeTotal, Shift, format_hm
from .parser import normalize_key, parse_pdf

# --- barvy a písma ----------------------------------------------------------
RED = "#C8102E"          # firemní červená (hlavička, hlavní tlačítko)
RED_DARK = "#A50D26"     # tmavší odstín pro hover
YELLOW = "#FFC72C"       # firemní žlutá (odznak BETA)
BG = "#F4F4F1"           # pozadí okna
CARD_BG = "#FFFFFF"      # pozadí panelů/karet
BORDER = "#DDDDD8"       # jemné ohraničení karet
TEXT = "#2B2B2B"         # základní text
MUTED = "#6E6E6E"        # popisky, méně důležitý text
STRIPE_BG = "#F7F7F4"    # zebra – sudé řádky tabulky
MINOR_BG = "#FFF3CD"     # zvýraznění řádků nezletilých
SELECT_BG = "#FBD8DE"    # vybraný řádek tabulky (světlá červená)
AUTHOR = "Matěj Kulísek"

FONT = "Segoe UI"        # na Windows nativní; jinde tkinter dosadí náhradu


def _apply_style(root: tk.Tk) -> ttk.Style:
    """Nastaví vzhled ttk prvků (téma, barvy, písma) pro celé okno."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass  # kdyby téma chybělo, zůstane výchozí

    style.configure(".", background=BG, foreground=TEXT, font=(FONT, 10))

    # Tlačítka: běžná světlá a hlavní červená.
    style.configure("TButton", padding=(10, 5))
    style.configure(
        "Primary.TButton", background=RED, foreground="white",
        font=(FONT, 11, "bold"), padding=(12, 9), borderwidth=0,
    )
    style.map(
        "Primary.TButton",
        background=[("pressed", RED_DARK), ("active", RED_DARK),
                    ("disabled", "#D98A96")],
        foreground=[("disabled", "#F5E4E7")],
    )

    # Panely (karty) s bílým pozadím.
    style.configure("Card.TFrame", background=CARD_BG)
    style.configure("Card.TLabel", background=CARD_BG)
    style.configure(
        "Section.TLabel", background=CARD_BG, foreground=RED,
        font=(FONT, 10, "bold"),
    )
    style.configure("Muted.TLabel", background=CARD_BG, foreground=MUTED,
                    font=(FONT, 9))
    style.configure("CardValue.TLabel", background=CARD_BG, foreground=TEXT,
                    font=(FONT, 14, "bold"))

    # Tabulka výsledků.
    style.configure(
        "Treeview", background=CARD_BG, fieldbackground=CARD_BG,
        foreground=TEXT, rowheight=26, font=(FONT, 10), borderwidth=0,
    )
    style.configure(
        "Treeview.Heading", background="#EBEBE6", foreground=TEXT,
        font=(FONT, 9, "bold"), padding=(6, 6), relief="flat",
    )
    style.map("Treeview.Heading", background=[("active", "#E0E0DA")])
    style.map(
        "Treeview",
        background=[("selected", SELECT_BG)],
        foreground=[("selected", TEXT)],
    )

    style.configure("TProgressbar", background=RED, troughcolor="#E7E7E2",
                    borderwidth=0, thickness=6)
    return style


class App(tk.Tk):
    # Sloupce tabulky: (id, nadpis, šířka, zarovnání).
    COLUMNS = [
        ("employee", "Zaměstnanec", 170, "w"),
        ("contract", "Úvazek", 60, "center"),
        ("status", "Zletilost", 70, "center"),
        ("hm", "Hodiny", 70, "center"),
        ("hours", "des.", 50, "center"),
        ("weekend", "Víkend", 64, "center"),
        ("night", "Noční", 60, "center"),
        ("weeknight", "Noční o vík.", 86, "center"),
        ("vacation", "Dovolená", 72, "center"),
        ("sick", "Nemocenská", 84, "center"),
        ("shifts", "Směn", 48, "center"),
        ("days", "Dní", 42, "center"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.title(f"McDonald's – Počítadlo odpracovaných hodin (BETA {VERSION})")
        self.geometry("1280x700")
        self.minsize(900, 540)
        self.configure(bg=BG)
        _apply_style(self)

        self.files: List[str] = []
        self.shifts: List[Shift] = []      # poslední přečtené směny (pro přepočet)
        self.totals: List[EmployeeTotal] = []
        self.period: str = ""
        # {normalizovaný_klíč: zobrazené_jméno} nezletilých – načteno z disku.
        self.minors: Dict[str, str] = store.load_minors()
        # {normalizovaný_klíč jména: ruční denní úvazek v h} – načteno z disku.
        self.contracts: Dict[str, float] = store.load_contracts()
        self._result_queue: "queue.Queue" = queue.Queue()

        # Stav zobrazení tabulky (řazení + filtr).
        self._sort_column: Optional[str] = None
        self._sort_reverse = False
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_table())

        self._build_ui()
        self._bind_shortcuts()

        # Ask GitHub for the latest release in the background; shows a dialog
        # only when a newer version exists (silent when offline).
        updater.start_update_check(self, self._on_update_available)

    # --- sestavení rozhraní ------------------------------------------------
    def _build_ui(self) -> None:
        self._build_header()

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_sidebar(body)
        self._build_results(body)

        # Patička s autorem a verzí + stavový řádek (vždy viditelné).
        tk.Label(self, text=f"Autor: {AUTHOR}  •  verze {VERSION}", anchor="e",
                 bg=BG, fg=MUTED, font=(FONT, 8)).pack(fill="x", side="bottom",
                                                       padx=12)
        status_bar = tk.Frame(self, bg="#EBEBE6")
        status_bar.pack(fill="x", side="bottom")
        self.status = tk.Label(
            status_bar, text="Přidej PDF rozpisy a klikni na „Spočítat hodiny“.",
            anchor="w", bg="#EBEBE6", fg=TEXT, font=(FONT, 9), padx=12, pady=5,
        )
        self.status.pack(side="left", fill="x", expand=True)

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=RED, height=58)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="🍟", bg=RED, font=(FONT, 18)).pack(
            side="left", padx=(16, 4))
        tk.Label(
            header, text="Počítadlo odpracovaných hodin",
            bg=RED, fg="white", font=(FONT, 16, "bold"),
        ).pack(side="left", padx=(0, 10))
        tk.Label(
            header, text="BETA", bg=YELLOW, fg=RED, font=(FONT, 9, "bold"),
            padx=7, pady=2,
        ).pack(side="left")
        # Období zpracovaných rozpisů (doplní se po výpočtu).
        self.period_label = tk.Label(header, text="", bg=RED, fg="#FFD9DF",
                                     font=(FONT, 10, "bold"))
        self.period_label.pack(side="right", padx=16)

    def _build_sidebar(self, parent: tk.Frame) -> None:
        sidebar = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER,
                           highlightthickness=1)
        sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        inner = tk.Frame(sidebar, bg=CARD_BG)
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        # Krok 1: soubory.
        ttk.Label(inner, text="1 · ROZPISY SMĚN (PDF)",
                  style="Section.TLabel").pack(anchor="w")
        files_frame = tk.Frame(inner, bg=CARD_BG)
        files_frame.pack(fill="both", expand=True, pady=(6, 4))
        self.files_list = tk.Listbox(
            files_frame, height=8, width=34, activestyle="none",
            selectmode="extended", relief="flat", bg=STRIPE_BG, fg=TEXT,
            highlightbackground=BORDER, highlightthickness=1,
            selectbackground=SELECT_BG, selectforeground=TEXT, font=(FONT, 9),
        )
        files_scroll = ttk.Scrollbar(files_frame, orient="vertical",
                                     command=self.files_list.yview)
        self.files_list.configure(yscrollcommand=files_scroll.set)
        self.files_list.pack(side="left", fill="both", expand=True)
        files_scroll.pack(side="right", fill="y")
        self.files_list.bind("<Delete>", lambda _e: self.remove_selected_files())

        self.files_count = ttk.Label(inner, text="Žádné soubory.",
                                     style="Muted.TLabel")
        self.files_count.pack(anchor="w")

        row1 = tk.Frame(inner, bg=CARD_BG)
        row1.pack(fill="x", pady=(6, 2))
        ttk.Button(row1, text="Přidat PDF…", command=self.add_files).pack(
            side="left", fill="x", expand=True)
        ttk.Button(row1, text="Přidat složku…", command=self.add_folder).pack(
            side="left", fill="x", expand=True, padx=(6, 0))
        row2 = tk.Frame(inner, bg=CARD_BG)
        row2.pack(fill="x", pady=(0, 4))
        ttk.Button(row2, text="Odebrat vybrané",
                   command=self.remove_selected_files).pack(
            side="left", fill="x", expand=True)
        ttk.Button(row2, text="Vymazat vše", command=self.clear_files).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

        ttk.Separator(inner).pack(fill="x", pady=10)

        # Krok 2: nastavení výpočtu.
        ttk.Label(inner, text="2 · NASTAVENÍ",
                  style="Section.TLabel").pack(anchor="w")
        ttk.Label(inner, text="Přestávka:", style="Card.TLabel").pack(
            anchor="w", pady=(6, 2))
        self.break_var = tk.StringVar(value=BREAK_CHOICES[0])
        self.break_box = ttk.Combobox(
            inner, textvariable=self.break_var, values=BREAK_CHOICES,
            state="readonly",
        )
        self.break_box.pack(fill="x")
        self.break_box.bind("<<ComboboxSelected>>", self._on_break_change)

        row3 = tk.Frame(inner, bg=CARD_BG)
        row3.pack(fill="x", pady=(8, 0))
        ttk.Button(row3, text="Nezletilí…", command=self.edit_minors).pack(
            side="left", fill="x", expand=True)
        ttk.Button(row3, text="Úvazky…", command=self.edit_contracts).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

        ttk.Separator(inner).pack(fill="x", pady=10)

        # Krok 3: výpočet.
        ttk.Label(inner, text="3 · VÝPOČET",
                  style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        self.compute_btn = ttk.Button(
            inner, text="▶  Spočítat hodiny", style="Primary.TButton",
            command=self.compute,
        )
        self.compute_btn.pack(fill="x")
        self.progress = ttk.Progressbar(inner, mode="indeterminate")
        # Progressbar se zobrazí jen během čtení PDF (viz compute/_poll_result).

    def _build_results(self, parent: tk.Frame) -> None:
        right = tk.Frame(parent, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        # Lišta nad tabulkou: hledání vlevo, export vpravo.
        toolbar = tk.Frame(right, bg=BG)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tk.Label(toolbar, text="🔍", bg=BG).pack(side="left")
        self.search_entry = ttk.Entry(toolbar, textvariable=self.search_var,
                                      width=28)
        self.search_entry.pack(side="left", padx=(4, 4))
        ttk.Button(toolbar, text="✕", width=3,
                   command=lambda: self.search_var.set("")).pack(side="left")
        ttk.Button(toolbar, text="Export do CSV…",
                   command=self.export_csv).pack(side="right")
        ttk.Button(toolbar, text="Export do Excelu…",
                   command=self.export_xlsx).pack(side="right", padx=(0, 6))

        # Tabulka výsledků (karta s ohraničením).
        table_card = tk.Frame(right, bg=CARD_BG, highlightbackground=BORDER,
                              highlightthickness=1)
        table_card.grid(row=1, column=0, sticky="nsew")
        table_card.columnconfigure(0, weight=1)
        table_card.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            table_card, columns=[c[0] for c in self.COLUMNS], show="headings")
        for col, title, width, anchor in self.COLUMNS:
            self.tree.heading(col, text=title,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=width, anchor=anchor,
                             stretch=(col == "employee"))
        self.tree.tag_configure("odd", background=CARD_BG)
        self.tree.tag_configure("even", background=STRIPE_BG)
        self.tree.tag_configure("minor", background=MINOR_BG)
        yscroll = ttk.Scrollbar(table_card, orient="vertical",
                                command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_card, orient="horizontal",
                                command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        # Souhrnné karty pod tabulkou.
        summary = tk.Frame(right, bg=BG)
        summary.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self._summary_values: Dict[str, ttk.Label] = {}
        cards = [
            ("employees", "Zaměstnanců"),
            ("total", "Celkem hodin"),
            ("weekend", "Víkend"),
            ("night", "Noční"),
            ("vacation", "Dovolená"),
            ("sick", "Nemocenská"),
        ]
        for i, (key, caption) in enumerate(cards):
            summary.columnconfigure(i, weight=1, uniform="cards")
            card = tk.Frame(summary, bg=CARD_BG, highlightbackground=BORDER,
                            highlightthickness=1)
            card.grid(row=0, column=i, sticky="ew",
                      padx=(0 if i == 0 else 8, 0))
            value = ttk.Label(card, text="—", style="CardValue.TLabel")
            value.pack(anchor="w", padx=10, pady=(7, 0))
            ttk.Label(card, text=caption, style="Muted.TLabel").pack(
                anchor="w", padx=10, pady=(0, 7))
            self._summary_values[key] = value

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-o>", lambda _e: self.add_files())
        self.bind("<F5>", lambda _e: self.compute())
        self.bind("<Control-e>", lambda _e: self.export_xlsx())
        self.bind("<Control-f>", lambda _e: self.search_entry.focus_set())

    # --- práce se soubory --------------------------------------------------
    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Vyber PDF rozpisy",
            filetypes=[("PDF soubory", "*.pdf"), ("Všechny soubory", "*.*")],
        )
        self._add_paths(paths)

    def add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Vyber složku s PDF rozpisy")
        if not folder:
            return
        paths = [
            os.path.join(folder, f)
            for f in sorted(os.listdir(folder))
            if f.lower().endswith(".pdf")
        ]
        if not paths:
            messagebox.showinfo("Žádná PDF", "Ve složce nejsou žádné PDF soubory.")
            return
        self._add_paths(paths)

    def _add_paths(self, paths) -> None:
        added = 0
        for p in paths:
            if p not in self.files:
                self.files.append(p)
                self.files_list.insert("end", f" {os.path.basename(p)}")
                added += 1
        self._update_files_count()
        self._set_status(f"Přidáno souborů: {added}. Celkem: {len(self.files)}.")

    def remove_selected_files(self) -> None:
        selection = list(self.files_list.curselection())
        if not selection:
            return
        for index in reversed(selection):
            self.files_list.delete(index)
            del self.files[index]
        self._update_files_count()
        self._set_status(f"Odebráno souborů: {len(selection)}. "
                         f"Zbývá: {len(self.files)}.")

    def clear_files(self) -> None:
        self.files.clear()
        self.shifts = []
        self.files_list.delete(0, "end")
        self._clear_results()
        self._update_files_count()
        self._set_status("Seznam souborů vymazán.")

    def _update_files_count(self) -> None:
        n = len(self.files)
        text = "Žádné soubory." if n == 0 else f"Souborů v seznamu: {n}"
        self.files_count.config(text=text)

    # --- výpočet -----------------------------------------------------------
    def _break_config(self) -> BreakConfig:
        return break_config_for_choice(self.break_var.get())

    def _on_update_available(self, info: updater.UpdateInfo) -> None:
        # Runs on the Tk main loop once the background check finds a release.
        if messagebox.askyesno(
            "Nová verze",
            f"Je k dispozici nová verze {info.version} "
            f"(používáš {VERSION}).\n\nOtevřít stránku se stažením?",
        ):
            webbrowser.open(info.url)

    def _on_break_change(self, _event=None) -> None:
        # Změna přestávky: přepočítej z už načtených směn (bez čtení PDF znovu).
        if self.shifts:
            self._recalculate()

    def compute(self) -> None:
        # Klávesová zkratka (F5) obchází zablokované tlačítko – během běžícího
        # čtení PDF nesmí odstartovat druhé vlákno.
        if "disabled" in self.compute_btn.state():
            return
        if not self.files:
            messagebox.showwarning("Žádné soubory", "Nejdřív přidej alespoň jedno PDF.")
            return
        self._set_status("Zpracovávám PDF…")
        self.compute_btn.state(["disabled"])
        self.progress.pack(fill="x", pady=(8, 0))
        self.progress.start(12)
        self.update_idletasks()
        files = list(self.files)
        thread = threading.Thread(target=self._worker, args=(files,), daemon=True)
        thread.start()
        self.after(100, self._poll_result)

    def _worker(self, files: List[str]) -> None:
        shifts: List[Shift] = []
        errors: List[str] = []
        for path in files:
            try:
                shifts.extend(parse_pdf(path))
            except Exception as exc:  # noqa: BLE001 – chybu reportujeme uživateli
                errors.append(f"{os.path.basename(path)}: {exc}")
        self._result_queue.put((shifts, errors))

    def _poll_result(self) -> None:
        try:
            shifts, errors = self._result_queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_result)
            return
        self.progress.stop()
        self.progress.pack_forget()
        self.compute_btn.state(["!disabled"])
        self.shifts = shifts
        start, end = date_range(shifts)
        self.period = ""
        if start and end:
            self.period = f"{start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')}"
        self.period_label.config(
            text=f"Období: {self.period}" if self.period else "")
        self._recalculate()
        if errors:
            messagebox.showwarning(
                "Některé soubory se nepodařilo přečíst",
                "\n".join(errors[:15]),
            )

    def _recalculate(self) -> None:
        """Znovu sečte hodiny z ``self.shifts`` (přestávka, nezletilí, úvazky)."""
        self.totals = aggregate(self.shifts, self._break_config(),
                                set(self.minors), self.contracts)
        self._refresh_table()
        self._refresh_summary()
        msg = f"Hotovo. Nalezeno směn: {len(self.shifts)}."
        if self.period:
            msg += f"  Období: {self.period}."
        if not self.shifts:
            msg += ("  Nenašel jsem žádné směny – možná má PDF jiný formát. "
                    "Pošli vzorek a parser doladíme.")
        self._set_status(msg)

    # --- tabulka: filtr + řazení -------------------------------------------
    # Podle čeho se řadí jednotlivé sloupce (čísla číselně, jména abecedně).
    _SORT_KEYS = {
        "employee": lambda t: normalize_key(t.employee),
        "contract": lambda t: t.contract_hours if t.contract_hours is not None else -1,
        "status": lambda t: t.is_minor,
        "hm": lambda t: t.total_minutes,
        "hours": lambda t: t.total_minutes,
        "weekend": lambda t: t.weekend_minutes,
        "night": lambda t: t.night_minutes,
        "weeknight": lambda t: t.weekend_night_minutes,
        "vacation": lambda t: t.vacation_minutes,
        "sick": lambda t: t.sick_minutes,
        "shifts": lambda t: t.shift_count,
        "days": lambda t: t.day_count,
    }

    def _sort_by(self, column: str) -> None:
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            # Jména vzestupně, hodiny/čísla rovnou od největších.
            self._sort_reverse = column not in ("employee", "status", "contract")
        self._refresh_table()

    def _visible_totals(self) -> List[EmployeeTotal]:
        """Souhrny po uplatnění filtru a řazení (pro zobrazení v tabulce)."""
        totals = self.totals
        needle = normalize_key(self.search_var.get().strip())
        if needle:
            totals = [t for t in totals if needle in normalize_key(t.employee)]
        if self._sort_column:
            totals = sorted(totals, key=self._SORT_KEYS[self._sort_column],
                            reverse=self._sort_reverse)
        return totals

    def _refresh_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        # Šipka u právě řazeného sloupce.
        for col, title, _w, _a in self.COLUMNS:
            arrow = ""
            if col == self._sort_column:
                arrow = "  ▼" if self._sort_reverse else "  ▲"
            self.tree.heading(col, text=title + arrow)
        for i, t in enumerate(self._visible_totals()):
            tags = ("minor",) if t.is_minor else (("even",) if i % 2 else ("odd",))
            self.tree.insert("", "end", tags=tags, values=(
                t.employee, t.contract_label, t.status_label, t.hm, t.hours,
                t.weekend_hm, t.night_hm, t.weekend_night_hm,
                t.vacation_hm, t.sick_hm, t.shift_count, t.day_count,
            ))

    def _refresh_summary(self) -> None:
        if not self.totals:
            for label in self._summary_values.values():
                label.config(text="—")
            return
        minor_count = sum(1 for t in self.totals if t.is_minor)
        employees = str(len(self.totals))
        if minor_count:
            employees += f" ({minor_count} nezl.)"
        values = {
            "employees": employees,
            "total": format_hm(grand_total_minutes(self.totals)),
            "weekend": format_hm(sum(t.weekend_minutes for t in self.totals)),
            "night": format_hm(sum(t.night_minutes for t in self.totals)),
            "vacation": format_hm(sum(t.vacation_minutes for t in self.totals)),
            "sick": format_hm(sum(t.sick_minutes for t in self.totals)),
        }
        for key, text in values.items():
            self._summary_values[key].config(text=text)

    def _clear_results(self) -> None:
        self.totals = []
        self._refresh_table()
        self._refresh_summary()
        self.period = ""
        self.period_label.config(text="")

    # --- nezletilí ---------------------------------------------------------
    def edit_minors(self) -> None:
        """Otevře dialog pro označení, kdo je nezletilý."""
        # Jména sjednoť podle normalizovaného klíče (jinak by se v dialogu
        # objevil tentýž člověk dvakrát a vkládání do stromu by spadlo);
        # při shodě má přednost tvar z aktuálních výsledků.
        by_key = {normalize_key(n): n for n in self.minors.values()}
        by_key.update({normalize_key(t.employee): t.employee for t in self.totals})
        names = sorted(by_key.values(), key=normalize_key)
        if not names:
            messagebox.showinfo(
                "Nejdřív spočítej hodiny",
                "Nejdřív přidej PDF a klikni na „Spočítat hodiny“, aby se "
                "načetla jména zaměstnanců. Pak u nich označíš nezletilé.",
            )
            return
        MinorsDialog(self, names, set(self.minors), self._save_minors)

    def _save_minors(self, minor_keys: set) -> None:
        # Z vybraných klíčů sestav slovník {klíč: zobrazené_jméno}.
        display_by_key = {normalize_key(n): n for n in self.minors.values()}
        display_by_key.update(
            {normalize_key(t.employee): t.employee for t in self.totals})
        new_minors: Dict[str, str] = {}
        for key in minor_keys:
            name = display_by_key.get(key, key)
            new_minors[normalize_key(name)] = name
        self.minors = new_minors
        store.save_minors(new_minors)
        if self.shifts:
            self._recalculate()
        self._set_status(f"Uloženo nezletilých: {len(new_minors)}.")

    # --- úvazky ------------------------------------------------------------
    def edit_contracts(self) -> None:
        """Otevře dialog pro doplnění/přepsání denního úvazku (h/den)."""
        if not self.totals:
            messagebox.showinfo(
                "Nejdřív spočítej hodiny",
                "Nejdřív přidej PDF a klikni na „Spočítat hodiny“, aby se "
                "načetli zaměstnanci. Pak u nich doplníš úvazek.",
            )
            return
        rows = [(t.employee, normalize_key(t.employee), t.contract_hours)
                for t in self.totals]
        ContractsDialog(self, rows, dict(self.contracts), self._save_contracts)

    def _save_contracts(self, contracts: Dict[str, float]) -> None:
        self.contracts = contracts                 # klíče = normalizovaná jména
        store.save_contracts(contracts)
        if self.shifts:
            self._recalculate()
        self._set_status(f"Uloženo ručních úvazků: {len(contracts)}.")

    # --- export ------------------------------------------------------------
    def export_xlsx(self) -> None:
        if not self.totals:
            messagebox.showwarning("Není co exportovat", "Nejdřív spočítej hodiny.")
            return
        path = filedialog.asksaveasfilename(
            title="Uložit do Excelu", defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")], initialfile="hodiny.xlsx",
        )
        if not path:
            return
        try:
            from .exporter import export_xlsx
            export_xlsx(self.totals, path, period=self.period or None)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Chyba exportu", str(exc))
            return
        self._set_status(f"Uloženo: {path}")

    def export_csv(self) -> None:
        if not self.totals:
            messagebox.showwarning("Není co exportovat", "Nejdřív spočítej hodiny.")
            return
        path = filedialog.asksaveasfilename(
            title="Uložit do CSV", defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], initialfile="hodiny.csv",
        )
        if not path:
            return
        try:
            from .exporter import export_csv
            export_csv(self.totals, path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Chyba exportu", str(exc))
            return
        self._set_status(f"Uloženo: {path}")

    def _set_status(self, text: str) -> None:
        self.status.config(text=text)


def _center_on_parent(window: tk.Toplevel, parent: tk.Misc) -> None:
    """Umístí dialog doprostřed rodičovského okna."""
    window.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - window.winfo_width()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - window.winfo_height()) // 2
    window.geometry(f"+{max(0, x)}+{max(0, y)}")


class MinorsDialog(tk.Toplevel):
    """Modální dialog pro označení nezletilých zaměstnanců (klikáním)."""

    CHECKED = "☑"
    UNCHECKED = "☐"

    def __init__(self, parent, names: List[str], selected_keys: set, on_save) -> None:
        super().__init__(parent)
        self.title("Nezletilí zaměstnanci")
        self.geometry("400x480")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self._names = names
        self._on_save = on_save
        self._checked = {normalize_key(n): (normalize_key(n) in selected_keys)
                         for n in names}

        ttk.Label(
            self, justify="left", wraplength=370, background=BG,
            text="Klikni na jméno – zaškrtnutí ☑ znamená, že je zaměstnanec "
                 "NEzletilý. Nastavení se ukládá.",
        ).pack(fill="x", padx=12, pady=(12, 6))

        # Vyhledávání jména.
        search_row = tk.Frame(self, bg=BG)
        search_row.pack(fill="x", padx=12, pady=(0, 6))
        tk.Label(search_row, text="🔍", bg=BG).pack(side="left")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh())
        ttk.Entry(search_row, textvariable=self._search_var).pack(
            side="left", fill="x", expand=True, padx=(4, 0))

        frame = tk.Frame(self, bg=BG)
        frame.pack(fill="both", expand=True, padx=12)
        self.tree = ttk.Treeview(frame, columns=("check", "name"),
                                 show="headings", selectmode="none")
        self.tree.heading("check", text="")
        self.tree.heading("name", text="Zaměstnanec")
        self.tree.column("check", width=36, anchor="center", stretch=False)
        self.tree.column("name", anchor="w")
        self.tree.tag_configure("minor", background=MINOR_BG)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self._on_click)
        self._refresh()

        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=12, pady=12)
        ttk.Button(btns, text="Uložit", style="Primary.TButton",
                   command=self._save).pack(side="right")
        ttk.Button(btns, text="Zrušit", command=self.destroy).pack(
            side="right", padx=6)
        _center_on_parent(self, parent)

    def _refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        needle = normalize_key(self._search_var.get().strip())
        for name in self._names:
            key = normalize_key(name)
            if needle and needle not in key:
                continue
            mark = self.CHECKED if self._checked[key] else self.UNCHECKED
            tags = ("minor",) if self._checked[key] else ()
            self.tree.insert("", "end", iid=key, tags=tags,
                             values=(mark, name))

    def _on_click(self, event) -> None:
        item = self.tree.identify_row(event.y)
        if not item:
            return
        self._checked[item] = not self._checked[item]
        mark = self.CHECKED if self._checked[item] else self.UNCHECKED
        self.tree.item(item, values=(mark, self.tree.set(item, "name")),
                       tags=(("minor",) if self._checked[item] else ()))

    def _save(self) -> None:
        keys = {key for key, checked in self._checked.items() if checked}
        self._on_save(keys)
        self.destroy()


class ContractsDialog(tk.Toplevel):
    """Dialog pro doplnění/přepsání denního úvazku (h/den) u zaměstnanců.

    Každý řádek ukazuje aktuální úvazek (z PDF / ručně) a umožní vybrat
    „auto“ (= z PDF, jinak výchozí) nebo pevně 4 / 5 / 6 / 7,5 h.
    """

    CHOICES = ["auto", "4", "5", "6", "7.5"]

    def __init__(self, parent, rows, contracts: Dict[str, float], on_save) -> None:
        super().__init__(parent)
        self.title("Úvazky zaměstnanců (h/den)")
        self.geometry("460x540")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self._on_save = on_save
        self._vars = []  # (key, StringVar)

        ttk.Label(
            self, justify="left", wraplength=430, background=BG,
            text="Vyber denní úvazek (hodin/den) pro výpočet dovolené a "
                 "nemocenské. „auto“ = vzít z PDF (a kde chybí, použít 7,5 h).",
        ).pack(fill="x", padx=12, pady=(12, 6))

        # Rolovatelný seznam řádků.
        outer = tk.Frame(self, bg=CARD_BG, highlightbackground=BORDER,
                         highlightthickness=1)
        outer.pack(fill="both", expand=True, padx=12)
        canvas = tk.Canvas(outer, highlightthickness=0, bg=CARD_BG)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=CARD_BG)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        # Rolování kolečkem myši (Windows/Mac: MouseWheel, Linux: Button-4/5).
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-e.delta // 120, "units"))
        canvas.bind_all("<Button-4>", lambda _e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda _e: canvas.yview_scroll(1, "units"))
        self.bind("<Destroy>", self._unbind_wheel, add="+")
        self._canvas = canvas

        for i, (display, key, detected) in enumerate(rows):
            row_bg = STRIPE_BG if i % 2 else CARD_BG
            row = tk.Frame(inner, bg=row_bg)
            row.pack(fill="x")
            det = f"{detected:g}" if detected is not None else "—"
            tk.Label(row, text=display, width=26, anchor="w", bg=row_bg,
                     fg=TEXT, font=(FONT, 10)).pack(side="left", padx=(6, 0),
                                                    pady=3)
            tk.Label(row, text=f"PDF: {det}", width=8, anchor="w", bg=row_bg,
                     fg=MUTED, font=(FONT, 9)).pack(side="left")
            var = tk.StringVar(value="auto")
            if key in contracts:
                # Hodnotu z přepisu sjednoť na tvar bez .0 (např. "5", "7.5").
                var.set(f"{contracts[key]:g}")
            ttk.Combobox(row, textvariable=var, values=self.CHOICES,
                         state="readonly", width=6).pack(side="left", padx=4)
            self._vars.append((key, var))

        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=12, pady=12)
        ttk.Button(btns, text="Uložit", style="Primary.TButton",
                   command=self._save).pack(side="right")
        ttk.Button(btns, text="Zrušit", command=self.destroy).pack(
            side="right", padx=6)
        _center_on_parent(self, parent)

    def _unbind_wheel(self, event) -> None:
        if event.widget is self:
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self._canvas.unbind_all(seq)

    def _save(self) -> None:
        contracts: Dict[str, float] = {}
        for key, var in self._vars:
            val = var.get()
            if val and val != "auto":
                try:
                    contracts[key] = float(val.replace(",", "."))
                except ValueError:
                    continue
        self._on_save(contracts)
        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
