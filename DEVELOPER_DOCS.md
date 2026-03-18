# Akna Tootmise Kalkulaator — Developer Documentation

> Window Production Calculator — a desktop GUI tool that reads cut-list formulas from a CSV and calculates all component dimensions for window manufacturing.

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Requirements](#requirements)
4. [Architecture](#architecture)
5. [CSV Format Specification](#csv-format-specification)
6. [Formula Engine](#formula-engine)
7. [Data Model](#data-model)
8. [Module Reference](#module-reference)
9. [Adding New Product Types](#adding-new-product-types)
10. [Known Limitations & Future Work](#known-limitations--future-work)
11. [Glossary](#glossary)

---

## Overview

This application is used at the point of client order intake. A salesperson or production planner selects a window product type, enters the overall dimensions (width × height), quantity, and hinge side — the app then computes every component cut dimension using formulas defined in an external CSV file.

The key design decision is that **all production logic lives in the CSV, not in the code**. The Python app is a generic formula parser and GUI — it knows nothing about specific window profiles. This means production engineers can add, modify, or remove product types without touching any code.

### File Structure

```
├── window_calculator.py          # Main application (single file)
└── Tootmisreeglid_-_Sheet1.csv   # Production rules data (CSV)
```

---

## Quick Start

```bash
# Run with file picker dialog
python3 window_calculator.py

# Run with CSV auto-loaded
python3 window_calculator.py Tootmisreeglid_-_Sheet1.csv
```

---

## Requirements

- **Python 3.10+** (uses `list[X]` type hints and dataclasses)
- **tkinter** — ships with Python on Windows/macOS. On Debian/Ubuntu:
  ```bash
  sudo apt install python3-tk
  ```
- No third-party packages needed. Everything uses the standard library.

---

## Architecture

The app is structured in four layers, all in a single file:

```
┌──────────────────────────────────┐
│        GUI (tkinter)             │  WindowCalculatorApp class
│  Input panel ←→ Results tree     │
├──────────────────────────────────┤
│      Calculation Engine          │  calculate_cut_list()
│  Orchestrates formula evaluation │
├──────────────────────────────────┤
│       Formula Evaluator          │  evaluate_formula()
│  Parses "L-86", "(L-80)/2" etc  │  parse_count_formula()
├──────────────────────────────────┤
│         CSV Parser               │  parse_csv()
│  Reads paired data+formula rows  │
└──────────────────────────────────┘
```

**Data flow:**

1. `parse_csv()` reads the CSV → returns `list[ProductType]`
2. User selects a product, enters L / K / qty / hand
3. `calculate_cut_list()` calls `evaluate_formula()` for each component
4. GUI renders results into a `ttk.Treeview` table

---

## CSV Format Specification

The CSV uses a **paired-row pattern**. Every product entry consists of two consecutive rows:

### Row 1 — Data Row (concrete example values)

| Col | Field              | Example       | Description                           |
|-----|--------------------|---------------|---------------------------------------|
| 0   | A/U                | `A` or `TA`   | Category: A=aken (window), TA=topeltaken (double window) |
| 1   | toote tyyp         | `40STAND60x63` | Profile system identifier            |
| 2   | laius              | `900`         | Example width (L) in mm               |
| 3   | kõrgus             | `900`         | Example height (K) in mm              |
| 4   | tk tyyptellimusel  | `3`           | Example quantity                      |
| 5   | käsi               | `P`           | Hinge side: P=parem (right), V=vasak (left) |
| 6   | raam L             | `814`         | Computed frame width (for verification) |
| 7   | raam H             | `804`         | Computed frame height                 |
| 8   | raam tk            | `3`           | Frame piece count                     |
| 9   | klaas L            | `714`         | Computed glass width                  |
| 10  | klaas H            | `704`         | Computed glass height                 |
| 11  | klaas tk           | (empty)       | Glass piece count                     |
| 12–17 | lengi detailid   |               | Sash component values (ÜH, AH, VERT with counts) |
| 18–23 | raami detailid   |               | Frame part values (ÜH, AH, VERT with counts) |
| 24–27 | klaasiliistud    |               | Glazing bead values (HOR, VERT with counts) |

### Row 2 — Formula Row (calculation rules)

Same column layout, but instead of numbers, each cell contains a **formula string**:

| Col | Contains          | Example Formula     |
|-----|-------------------|---------------------|
| 6   | Frame L formula   | `L-86` or `(L-80)/2` |
| 7   | Frame H formula   | `K-96`              |
| 8   | Frame tk formula  | `tk` or `tkx2`      |
| 9   | Glass L formula   | `L-86-100` or `((L-80)/2)-100` |
| 10  | Glass H formula   | `K-96-100`          |
| 12  | Sash ÜH dim       | `L`                 |
| 13  | Sash ÜH count     | `tk`                |
| 14  | Sash AH dim       | `L-100`             |
| 15  | Sash AH count     | `tk`                |
| 16  | Sash VERT dim     | `K-50`              |
| 17  | Sash VERT count   | `tkx2`              |
| 18  | Frame ÜH dim      | `L-86`              |
| 19  | Frame ÜH count    | `tk`                |
| 20  | Frame AH dim      | `L-86`              |
| 21  | Frame AH count    | `tk`                |
| 22  | Frame VERT dim    | `K-96-96`           |
| 23  | Frame VERT count  | `tkx2`              |
| 24  | Bead HOR dim      | `L-86-100+4`        |
| 25  | Bead HOR count    | `tkx2`              |
| 26  | Bead VERT dim     | `K-96-100+4`        |
| 27  | Bead VERT count   | `tkx2`              |

### Header Rows

The CSV starts with two header rows (rows 0–1) which are skipped by the parser (they don't start with `A` or `TA`). Any empty rows or legend rows at the bottom (like `TA- topeltaken`) are also safely ignored.

---

## Formula Engine

### Dimension Formulas — `evaluate_formula()`

The formula evaluator accepts strings containing:

- **Variables:** `L` (width), `K` (height), `tk` (quantity)
- **Operators:** `+`, `-`, `*`, `/`
- **Parentheses:** for grouping
- **Integer literals**

Examples of valid formulas:

| Formula               | Meaning                              | With L=1250, K=956 |
|-----------------------|--------------------------------------|---------------------|
| `L-86`                | Width minus 86mm                     | 1164                |
| `K-96`                | Height minus 96mm                    | 860                 |
| `(L-80)/2`            | Half-width for double windows        | 585                 |
| `((L-80)/2)-100`      | Half-width minus glass inset         | 485                 |
| `K-96-96`             | Height minus top and bottom rails    | 764                 |
| `L-86-100+4`          | Glazing bead with 4mm clearance      | 1068                |

**Safety:** The evaluator validates the formula string against a whitelist regex (`[\dLKtk+\-*/().]+`) before calling `eval()`. Only arithmetic characters and the three variable names are permitted.

### Count Formulas — `parse_count_formula()`

Piece counts use a simpler pattern:

| Formula | Meaning                                      |
|---------|----------------------------------------------|
| `tk`    | Same as input quantity                        |
| `tkx2`  | Quantity × 2 (e.g., 2 vertical pieces per unit) |
| `tkx4`  | Quantity × 4 (double windows, 2 sashes × 2 verticals) |

---

## Data Model

### `ComponentSpec`

Represents one component type (e.g., "Leng ÜH" — upper horizontal sash piece):

```python
@dataclass
class ComponentSpec:
    name: str           # Display name, e.g. "Leng ÜH"
    dim_formula: str    # Dimension formula, e.g. "L-86"
    count_formula: str  # Piece count formula, e.g. "tkx2"
```

### `ProductType`

Represents one product entry from the CSV (one data+formula row pair):

```python
@dataclass
class ProductType:
    category: str           # "A" or "TA"
    product_type: str       # Profile identifier
    example_L: int          # Example width from CSV
    example_K: int          # Example height from CSV
    example_qty: int        # Example quantity
    example_hand: str       # Example hinge side

    frame_L_formula: str    # Frame width formula
    frame_H_formula: str    # Frame height formula
    frame_tk_formula: str   # Frame count formula

    glass_L_formula: str    # Glass width formula
    glass_H_formula: str    # Glass height formula
    glass_tk_formula: str   # Glass count formula

    sash_components: list[ComponentSpec]    # ÜH, AH, VERT
    frame_components: list[ComponentSpec]   # ÜH, AH, VERT
    bead_components: list[ComponentSpec]    # HOR, VERT
```

### `calculate_cut_list()` Return Value

Returns a `dict` with this structure:

```python
{
    'product': ProductType,
    'input': {'L': float, 'K': float, 'qty': int, 'hand': str},
    'frame': {'L': float, 'H': float, 'tk': int, 'L_formula': str, 'H_formula': str},
    'glass': {'L': float, 'H': float, 'tk': int, 'L_formula': str, 'H_formula': str},
    'sash': [{'name': str, 'dim': float, 'tk': int, 'formula': str}, ...],
    'frame_parts': [{'name': str, 'dim': float, 'tk': int, 'formula': str}, ...],
    'beads': [{'name': str, 'dim': float, 'tk': int, 'formula': str}, ...],
}
```

---

## Module Reference

Since everything is in one file, here's the function map:

| Function / Class           | Lines    | Purpose                                      |
|----------------------------|----------|----------------------------------------------|
| `clean_cell()`             | 66–68    | Strip whitespace and BOM from CSV cells       |
| `parse_csv()`              | 71–152   | Read CSV, extract paired rows into ProductType list |
| `evaluate_formula()`       | 157–186  | Evaluate a dimension formula with L, K, tk    |
| `parse_count_formula()`    | 189–206  | Parse count strings like `tk`, `tkx2`, `tkx4` |
| `calculate_cut_list()`     | 211–255  | Orchestrate all formula evaluations for one product |
| `WindowCalculatorApp`      | 260–566  | tkinter GUI application class                 |
| `WindowCalculatorApp._build_ui()` | 284–434 | Construct all GUI widgets               |
| `WindowCalculatorApp._load_csv()` | 436–443 | File picker dialog                      |
| `WindowCalculatorApp._reload_csv()` | 445–451 | Re-read current CSV file              |
| `WindowCalculatorApp._parse_and_populate()` | 453–479 | Parse CSV and fill the dropdown |
| `WindowCalculatorApp._on_product_select()` | 481–497 | Pre-fill example values from CSV |
| `WindowCalculatorApp._calculate()` | 506–566 | Run calculation and render results    |
| `main()`                   | 569–582  | Entry point, optional CLI arg for CSV path    |

---

## Adding New Product Types

This is the most important section for production engineers.

### Step-by-step

1. **Open** `Tootmisreeglid_-_Sheet1.csv` in Excel or Google Sheets
2. **Add two new rows** at the bottom (before any legend rows):

**Row 1 (data):**

| A/U | toote tyyp     | laius | kõrgus | tk | käsi | raam L | raam H | raam tk | klaas L | klaas H | klaas tk | ... |
|-----|----------------|-------|--------|----|------|--------|--------|---------|---------|---------|----------|-----|
| A   | 55STAND70x80   | 1000  | 1200   | 5  | P    | 914    | 1104   | 5       | 814     | 1004    |          | ... |

**Row 2 (formulas):**

| (empty) | (empty) | L | K | tk | (empty) | L-86 | K-96 | tk | L-86-100 | K-96-100 | tk | ... |

3. **Save** the CSV
4. In the app, click **"🔄 Uuenda CSV / Reload CSV"**
5. The new product type appears in the dropdown

### Rules

- Column 0 of the data row **must** be `A` or `TA` — this is how the parser identifies it
- The formula row **must** be directly below its data row (no blank rows between them)
- The data row values (raam L, raam H, etc.) are for **human verification only** — the app uses the formulas, not these values
- For double windows (TA), use `(L-80)/2` style formulas and `tkx2`/`tkx4` multipliers
- Empty formula cells are handled gracefully (component is skipped)

### Adding new component columns

If you need to add entirely new component types beyond the current 28 columns, you will need to modify the code:

1. Increase the padding target in `parse_csv()` (currently pads to 28)
2. Add new column index pairs in the appropriate section (sash/frame/beads)
3. Add new component names to the corresponding `_names` list

---

## Known Limitations & Future Work

### Current Limitations

- **No data export** — results are display-only; no PDF/Excel export of the cut list
- **No validation against min/max dimensions** — formulas will compute negative values for too-small inputs without warning
- **Single CSV structure assumed** — the parser expects exactly 28 columns in the paired-row format
- **`eval()` usage** — although input is regex-validated, a dedicated expression parser (e.g., using `ast.literal_eval` or a proper parser) would be more robust
- **No multi-language toggle** — labels are hardcoded bilingual (Estonian/English)
- **Product type dropdown shows duplicates** — if the same profile appears with different example dimensions, only the first match is used for pre-fill

### Suggested Improvements

- **Export to PDF/Excel** — generate a printable work order per client order
- **Dimension validation** — define min/max per product type in the CSV and warn the user
- **Batch mode** — import a list of orders (multiple windows) and generate a combined cut list
- **Visual window diagram** — render an SVG/canvas diagram showing the window with labeled dimensions
- **Database backend** — replace CSV with SQLite for multi-user environments
- **Replace `eval()`** — implement a proper arithmetic parser using `ast` module
- **Unit tests** — add pytest tests that verify formula outputs against the example values in the CSV

---

## Glossary

| Estonian Term       | English              | Code Reference            |
|---------------------|----------------------|---------------------------|
| Aken (A)            | Window               | `category = "A"`          |
| Topeltaken (TA)     | Double window        | `category = "TA"`         |
| Laius (L)           | Width                | Variable `L`              |
| Kõrgus (K)          | Height               | Variable `K`              |
| Raam                | Frame                | `frame_L_formula` etc.    |
| Klaas / KLP         | Glass / glazing unit | `glass_L_formula` etc.    |
| Leng                | Sash (opening part)  | `sash_components`         |
| ÜH                  | Upper horizontal     | Component name suffix     |
| AH                  | Lower horizontal     | Component name suffix     |
| VERT                | Vertical             | Component name suffix     |
| HOR                 | Horizontal           | Component name suffix     |
| Klaasiliist         | Glazing bead         | `bead_components`         |
| Käsi                | Hand / hinge side    | `P`=right, `V`=left       |
| tk                  | Pieces (tükk)        | Quantity variable         |
| Mõõt                | Dimension / measure  | Column header             |
| Valem               | Formula              | Column header             |
| Lõikenimekiri       | Cut list             | GUI section title         |
| Tootmisreeglid      | Production rules     | CSV filename              |
