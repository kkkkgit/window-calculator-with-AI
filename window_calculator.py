#!/usr/bin/env python3
"""
Akna Tootmise Kalkulaator / Window Production Calculator
=========================================================
Reads production rules from a CSV file and calculates all cut dimensions
for window frames, glass, sash parts, frame parts, and glazing beads.

CSV structure (paired rows):
  - Data row:  A/U, product type, L, K, qty, hand, frame_L, frame_H, frame_tk, glass_L, glass_H, glass_tk, ...
  - Formula row: (below each data row) contains formulas like L-86, K-96, (L-80)/2, etc.

The app parses formulas dynamically, so adding new product types to the CSV
is automatically picked up on reload.
"""

import csv
import re
import sys
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from dataclasses import dataclass, field
from typing import Optional


# ─── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class ComponentSpec:
    """A single component with a formula for its dimension and a piece count formula."""
    name: str
    dim_formula: str
    count_formula: str

@dataclass
class ProductType:
    """A product type extracted from the CSV with all its formulas."""
    category: str          # A or TA
    product_type: str      # e.g. 40STAND60x63
    example_L: int
    example_K: int
    example_qty: int
    example_hand: str

    # Formulas (strings like "L-86", "(L-80)/2", etc.)
    frame_L_formula: str = ""
    frame_H_formula: str = ""
    frame_tk_formula: str = ""

    glass_L_formula: str = ""
    glass_H_formula: str = ""
    glass_tk_formula: str = ""

    # Sash (leng) components: ÜH, AH, VERT
    sash_components: list = field(default_factory=list)

    # Frame (raam) components: ÜH, AH, VERT
    frame_components: list = field(default_factory=list)

    # Glazing beads (klaasiliistud): HOR, VERT
    bead_components: list = field(default_factory=list)


# ─── CSV Parser ────────────────────────────────────────────────────────────────

def clean_cell(cell: str) -> str:
    """Strip whitespace and BOM characters."""
    return cell.strip().strip('\ufeff').strip()


def parse_csv(filepath: str) -> list[ProductType]:
    """
    Parse the production rules CSV.
    The CSV has paired rows: a data row followed by a formula row.
    """
    products = []

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = list(csv.reader(f))

    # Find paired rows: data row has a non-empty first cell (A or TA)
    i = 0
    while i < len(reader) - 1:
        row = [clean_cell(c) for c in reader[i]]
        # Skip empty rows, header rows, legend rows
        if len(row) < 6 or row[0] not in ('A', 'TA'):
            i += 1
            continue

        data_row = row
        formula_row = [clean_cell(c) for c in reader[i + 1]] if i + 1 < len(reader) else []

        # Pad rows to expected length (28 columns)
        while len(data_row) < 28:
            data_row.append('')
        while len(formula_row) < 28:
            formula_row.append('')

        try:
            pt = ProductType(
                category=data_row[0],
                product_type=data_row[1],
                example_L=int(data_row[2]) if data_row[2] else 0,
                example_K=int(data_row[3]) if data_row[3] else 0,
                example_qty=int(data_row[4]) if data_row[4] else 0,
                example_hand=data_row[5],
            )

            # Frame formulas (columns 6, 7, 8)
            pt.frame_L_formula = formula_row[6] if formula_row[6] else "L-86"
            pt.frame_H_formula = formula_row[7] if formula_row[7] else "K-96"
            pt.frame_tk_formula = formula_row[8] if formula_row[8] else "tk"

            # Glass formulas (columns 9, 10, 11)
            pt.glass_L_formula = formula_row[9] if formula_row[9] else ""
            pt.glass_H_formula = formula_row[10] if formula_row[10] else ""
            pt.glass_tk_formula = formula_row[11] if formula_row[11] else ""

            # Sash (lengi detailid) — columns 12-17: ÜH, tk, AH, tk, VERT, tk
            sash_names = ["Leng ÜH", "Leng AH", "Leng VERT"]
            sash_cols = [(12, 13), (14, 15), (16, 17)]
            for name, (dim_col, tk_col) in zip(sash_names, sash_cols):
                dim_f = formula_row[dim_col]
                tk_f = formula_row[tk_col]
                if dim_f:
                    pt.sash_components.append(ComponentSpec(name, dim_f, tk_f))

            # Frame (raami detailid) — columns 18-23: ÜH, tk, AH, tk, VERT, tk
            frame_names = ["Raam ÜH", "Raam AH", "Raam VERT"]
            frame_cols = [(18, 19), (20, 21), (22, 23)]
            for name, (dim_col, tk_col) in zip(frame_names, frame_cols):
                dim_f = formula_row[dim_col]
                tk_f = formula_row[tk_col]
                if dim_f:
                    pt.frame_components.append(ComponentSpec(name, dim_f, tk_f))

            # Glazing beads — columns 24-27: HOR, tk, VERT, tk
            bead_names = ["Klaasiliist HOR", "Klaasiliist VERT"]
            bead_cols = [(24, 25), (26, 27)]
            for name, (dim_col, tk_col) in zip(bead_names, bead_cols):
                dim_f = formula_row[dim_col]
                tk_f = formula_row[tk_col]
                if dim_f:
                    pt.bead_components.append(ComponentSpec(name, dim_f, tk_f))

            products.append(pt)
        except (ValueError, IndexError) as e:
            print(f"Warning: skipping row {i}: {e}")

        i += 2  # Skip the formula row

    return products


# ─── Formula Evaluator ─────────────────────────────────────────────────────────

def evaluate_formula(formula: str, L: float, K: float, tk: int) -> Optional[float]:
    """
    Safely evaluate a dimension formula.
    Supports: L, K, tk, basic arithmetic (+, -, *, /), parentheses.
    """
    if not formula or formula in ('tk', 'L', 'K'):
        if formula == 'tk':
            return tk
        if formula == 'L':
            return L
        if formula == 'K':
            return K
        return None

    # Replace variable names with values
    expr = formula.replace(' ', '')

    # Validate: only allow digits, L, K, t, k, arithmetic, parens
    if not re.match(r'^[\dLKtk+\-*/().]+$', expr):
        return None

    expr = re.sub(r'(?<![a-zA-Z])L(?![a-zA-Z])', str(L), expr)
    expr = re.sub(r'(?<![a-zA-Z])K(?![a-zA-Z])', str(K), expr)
    expr = re.sub(r'(?<![a-zA-Z])tk(?![a-zA-Z])', str(tk), expr)

    try:
        result = eval(expr)  # Safe because we validated input chars
        return round(result, 1)
    except Exception:
        return None


def parse_count_formula(formula: str, base_tk: int) -> int:
    """
    Parse a piece count formula like 'tk', 'tkx2', 'tkx4'.
    Returns the total number of pieces.
    """
    if not formula:
        return base_tk

    formula = formula.strip()
    if formula == 'tk':
        return base_tk
    match = re.match(r'tkx(\d+)', formula)
    if match:
        return base_tk * int(match.group(1))
    try:
        return int(formula)
    except ValueError:
        return base_tk


# ─── Calculation Engine ────────────────────────────────────────────────────────

def calculate_cut_list(product: ProductType, L: float, K: float, qty: int, hand: str) -> dict:
    """Calculate all component dimensions for given window parameters."""
    results = {
        'product': product,
        'input': {'L': L, 'K': K, 'qty': qty, 'hand': hand},
        'frame': {},
        'glass': {},
        'sash': [],
        'frame_parts': [],
        'beads': [],
    }

    # Frame
    frame_L = evaluate_formula(product.frame_L_formula, L, K, qty)
    frame_H = evaluate_formula(product.frame_H_formula, L, K, qty)
    frame_tk = parse_count_formula(product.frame_tk_formula, qty)
    results['frame'] = {
        'L': frame_L, 'H': frame_H, 'tk': frame_tk,
        'L_formula': product.frame_L_formula,
        'H_formula': product.frame_H_formula,
    }

    # Glass
    glass_L = evaluate_formula(product.glass_L_formula, L, K, qty)
    glass_H = evaluate_formula(product.glass_H_formula, L, K, qty)
    glass_tk = parse_count_formula(product.glass_tk_formula, qty)
    results['glass'] = {
        'L': glass_L, 'H': glass_H, 'tk': glass_tk,
        'L_formula': product.glass_L_formula,
        'H_formula': product.glass_H_formula,
    }

    # Sash components
    for comp in product.sash_components:
        dim = evaluate_formula(comp.dim_formula, L, K, qty)
        count = parse_count_formula(comp.count_formula, qty)
        results['sash'].append({
            'name': comp.name,
            'dim': dim,
            'tk': count,
            'formula': comp.dim_formula,
        })

    # Frame components
    for comp in product.frame_components:
        dim = evaluate_formula(comp.dim_formula, L, K, qty)
        count = parse_count_formula(comp.count_formula, qty)
        results['frame_parts'].append({
            'name': comp.name,
            'dim': dim,
            'tk': count,
            'formula': comp.dim_formula,
        })

    # Glazing beads
    for comp in product.bead_components:
        dim = evaluate_formula(comp.dim_formula, L, K, qty)
        count = parse_count_formula(comp.count_formula, qty)
        results['beads'].append({
            'name': comp.name,
            'dim': dim,
            'tk': count,
            'formula': comp.dim_formula,
        })

    return results


# ─── GUI Application ──────────────────────────────────────────────────────────

class WindowCalculatorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Akna Tootmise Kalkulaator")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)

        # Colors — industrial dark theme
        self.BG = "#1a1a2e"
        self.BG2 = "#16213e"
        self.FG = "#e0e0e0"
        self.ACCENT = "#e94560"
        self.ACCENT2 = "#0f3460"
        self.TABLE_BG = "#0f3460"
        self.TABLE_FG = "#e0e0e0"
        self.HEADER_BG = "#e94560"
        self.ENTRY_BG = "#16213e"
        self.ENTRY_FG = "#e0e0e0"

        self.root.configure(bg=self.BG)

        self.products: list[ProductType] = []
        self.csv_path: str = ""

        self._build_ui()

    def _build_ui(self):
        # ── Top bar: file loader ──
        top = tk.Frame(self.root, bg=self.BG, padx=10, pady=8)
        top.pack(fill=tk.X)

        tk.Label(top, text="AKNA TOOTMISE KALKULAATOR", font=("Consolas", 16, "bold"),
                 bg=self.BG, fg=self.ACCENT).pack(side=tk.LEFT)

        btn_load = tk.Button(top, text="📂 Lae CSV / Load CSV", font=("Consolas", 10),
                             bg=self.ACCENT2, fg=self.FG, relief=tk.FLAT, padx=12, pady=4,
                             command=self._load_csv, cursor="hand2")
        btn_load.pack(side=tk.RIGHT, padx=5)

        self.lbl_file = tk.Label(top, text="CSV: (pole laetud / not loaded)", font=("Consolas", 9),
                                 bg=self.BG, fg="#888")
        self.lbl_file.pack(side=tk.RIGHT, padx=10)

        # Separator
        tk.Frame(self.root, bg=self.ACCENT, height=2).pack(fill=tk.X)

        # ── Main content ──
        main = tk.Frame(self.root, bg=self.BG)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        # Left panel: inputs
        left = tk.Frame(main, bg=self.BG2, width=320, padx=15, pady=15)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        left.pack_propagate(False)

        tk.Label(left, text="SISEND / INPUT", font=("Consolas", 12, "bold"),
                 bg=self.BG2, fg=self.ACCENT).pack(anchor=tk.W, pady=(0, 10))

        # Product type selector
        tk.Label(left, text="Toote tüüp / Product type:", font=("Consolas", 9),
                 bg=self.BG2, fg=self.FG).pack(anchor=tk.W, pady=(5, 2))
        self.combo_product = ttk.Combobox(left, state="readonly", width=35, font=("Consolas", 10))
        self.combo_product.pack(anchor=tk.W)
        self.combo_product.bind("<<ComboboxSelected>>", self._on_product_select)

        # Dimensions
        input_fields = [
            ("Laius / Width (L) mm:", "entry_L"),
            ("Kõrgus / Height (K) mm:", "entry_K"),
            ("Kogus / Quantity:", "entry_qty"),
        ]
        for label_text, attr_name in input_fields:
            tk.Label(left, text=label_text, font=("Consolas", 9),
                     bg=self.BG2, fg=self.FG).pack(anchor=tk.W, pady=(10, 2))
            entry = tk.Entry(left, font=("Consolas", 12), bg=self.ENTRY_BG, fg=self.ENTRY_FG,
                             insertbackground=self.FG, relief=tk.FLAT, width=20,
                             highlightthickness=1, highlightcolor=self.ACCENT)
            entry.pack(anchor=tk.W, ipady=4)
            setattr(self, attr_name, entry)

        # Hand selector
        tk.Label(left, text="Käsi / Hinge side:", font=("Consolas", 9),
                 bg=self.BG2, fg=self.FG).pack(anchor=tk.W, pady=(10, 2))
        hand_frame = tk.Frame(left, bg=self.BG2)
        hand_frame.pack(anchor=tk.W)
        self.hand_var = tk.StringVar(value="P")
        for text, val in [("P (parem/right)", "P"), ("V (vasak/left)", "V")]:
            tk.Radiobutton(hand_frame, text=text, variable=self.hand_var, value=val,
                           font=("Consolas", 9), bg=self.BG2, fg=self.FG,
                           selectcolor=self.BG, activebackground=self.BG2,
                           activeforeground=self.ACCENT).pack(anchor=tk.W)

        # Calculate button
        tk.Button(left, text="⚙  ARVUTA / CALCULATE", font=("Consolas", 11, "bold"),
                  bg=self.ACCENT, fg="white", relief=tk.FLAT, padx=15, pady=8,
                  command=self._calculate, cursor="hand2").pack(anchor=tk.W, pady=(20, 5))

        # Reload CSV button
        tk.Button(left, text="🔄 Uuenda CSV / Reload CSV", font=("Consolas", 9),
                  bg=self.ACCENT2, fg=self.FG, relief=tk.FLAT, padx=10, pady=4,
                  command=self._reload_csv, cursor="hand2").pack(anchor=tk.W, pady=(5, 0))

        # Info label
        self.lbl_info = tk.Label(left, text="", font=("Consolas", 8), bg=self.BG2, fg="#888",
                                 wraplength=280, justify=tk.LEFT)
        self.lbl_info.pack(anchor=tk.W, pady=(15, 0))

        # Right panel: results
        right = tk.Frame(main, bg=self.BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(right, text="LÕIKENIMEKIRI / CUT LIST", font=("Consolas", 12, "bold"),
                 bg=self.BG, fg=self.ACCENT).pack(anchor=tk.W, pady=(0, 5))

        # Results tree
        tree_frame = tk.Frame(right, bg=self.BG)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("component", "formula", "dimension_mm", "pieces")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=25)

        self.tree.heading("component", text="Komponent / Component")
        self.tree.heading("formula", text="Valem / Formula")
        self.tree.heading("dimension_mm", text="Mõõt / Dim (mm)")
        self.tree.heading("pieces", text="Tk / Pcs")

        self.tree.column("component", width=200, minwidth=150)
        self.tree.column("formula", width=250, minwidth=150)
        self.tree.column("dimension_mm", width=120, minwidth=80, anchor=tk.CENTER)
        self.tree.column("pieces", width=80, minwidth=50, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Style the treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                         background=self.TABLE_BG,
                         foreground=self.TABLE_FG,
                         fieldbackground=self.TABLE_BG,
                         font=("Consolas", 10),
                         rowheight=26)
        style.configure("Treeview.Heading",
                         background=self.HEADER_BG,
                         foreground="white",
                         font=("Consolas", 10, "bold"))
        style.map("Treeview",
                   background=[("selected", self.ACCENT2)],
                   foreground=[("selected", "white")])
        style.configure("TCombobox", fieldbackground=self.ENTRY_BG, foreground=self.ENTRY_FG)

    def _load_csv(self):
        path = filedialog.askopenfilename(
            title="Vali tootmisreeglite CSV / Select production rules CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if path:
            self.csv_path = path
            self._parse_and_populate(path)

    def _reload_csv(self):
        if self.csv_path:
            self._parse_and_populate(self.csv_path)
            messagebox.showinfo("Uuendatud / Reloaded", f"CSV uuesti laetud: {len(self.products)} toodet leitud.\n"
                                f"CSV reloaded: {len(self.products)} products found.")
        else:
            messagebox.showwarning("Hoiatus / Warning", "CSV pole veel laetud.\nCSV not loaded yet.")

    def _parse_and_populate(self, path: str):
        try:
            self.products = parse_csv(path)
        except Exception as e:
            messagebox.showerror("Viga / Error", f"CSV lugemine ebaõnnestus:\n{e}")
            return

        filename = os.path.basename(path)
        self.lbl_file.config(text=f"CSV: {filename} ({len(self.products)} toodet)")

        # Build unique product type labels
        labels = []
        seen = set()
        for p in self.products:
            label = f"{p.category} | {p.product_type}"
            if label not in seen:
                labels.append(label)
                seen.add(label)

        self.combo_product['values'] = labels
        if labels:
            self.combo_product.current(0)
            self._on_product_select(None)

        self.lbl_info.config(text=f"Leitud {len(self.products)} tooterida.\n"
                                  f"Tüüpe: {len(labels)}\n\n"
                                  f"Lisa CSV-sse uusi ridu ja vajuta\n'Uuenda CSV' nende laadimiseks.")

    def _on_product_select(self, event):
        """Pre-fill example values when a product is selected."""
        idx = self.combo_product.current()
        if idx < 0 or idx >= len(self.products):
            return
        # Find the first product matching this label
        label = self.combo_product.get()
        for p in self.products:
            if f"{p.category} | {p.product_type}" == label:
                self.entry_L.delete(0, tk.END)
                self.entry_L.insert(0, str(p.example_L))
                self.entry_K.delete(0, tk.END)
                self.entry_K.insert(0, str(p.example_K))
                self.entry_qty.delete(0, tk.END)
                self.entry_qty.insert(0, str(p.example_qty))
                self.hand_var.set(p.example_hand)
                break

    def _get_selected_product(self) -> Optional[ProductType]:
        label = self.combo_product.get()
        for p in self.products:
            if f"{p.category} | {p.product_type}" == label:
                return p
        return None

    def _calculate(self):
        product = self._get_selected_product()
        if not product:
            messagebox.showwarning("Hoiatus / Warning", "Vali toote tüüp!\nSelect a product type!")
            return

        try:
            L = float(self.entry_L.get())
            K = float(self.entry_K.get())
            qty = int(self.entry_qty.get())
        except ValueError:
            messagebox.showwarning("Hoiatus / Warning", "Sisesta korrektsed numbrid!\nEnter valid numbers!")
            return

        hand = self.hand_var.get()
        results = calculate_cut_list(product, L, K, qty, hand)

        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        def add_section(title):
            self.tree.insert("", tk.END, values=(f"── {title} ──", "", "", ""), tags=("section",))

        def add_row(component, formula, dim, pcs):
            dim_str = f"{dim:.1f}" if dim is not None else "—"
            self.tree.insert("", tk.END, values=(component, formula, dim_str, pcs))

        # Frame
        add_section("RAAM / FRAME")
        f = results['frame']
        add_row("Raam L (laius)", f['L_formula'], f['L'], f['tk'])
        add_row("Raam H (kõrgus)", f['H_formula'], f['H'], f['tk'])

        # Glass
        add_section("KLAAS / GLASS")
        g = results['glass']
        add_row("Klaas L (laius)", g['L_formula'], g['L'], g['tk'])
        add_row("Klaas H (kõrgus)", g['H_formula'], g['H'], g['tk'])

        # Sash
        if results['sash']:
            add_section("LENGI DETAILID / SASH PARTS")
            for s in results['sash']:
                add_row(s['name'], s['formula'], s['dim'], s['tk'])

        # Frame parts
        if results['frame_parts']:
            add_section("RAAMI DETAILID / FRAME PARTS")
            for fp in results['frame_parts']:
                add_row(fp['name'], fp['formula'], fp['dim'], fp['tk'])

        # Beads
        if results['beads']:
            add_section("KLAASILIISTUD / GLAZING BEADS")
            for b in results['beads']:
                add_row(b['name'], b['formula'], b['dim'], b['tk'])

        # Style section headers
        self.tree.tag_configure("section", background="#e94560", foreground="white",
                                font=("Consolas", 10, "bold"))


def main():
    # If a CSV path is passed as argument, auto-load it
    root = tk.Tk()
    app = WindowCalculatorApp(root)

    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        app.csv_path = sys.argv[1]
        app._parse_and_populate(sys.argv[1])

    root.mainloop()


if __name__ == "__main__":
    main()
