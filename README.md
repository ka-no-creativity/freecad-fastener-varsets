# Fastener VarSets

A small FreeCAD workbench for designing printed parts around metal screws and
nuts or heat inserts. Select fasteners, give each item its own print allowances, and create
ordinary native VarSets. Projects hold independent snapshots. They remain
usable without this add-on or its central library.

![Fastener chooser with naming controls, signed allowances and insert dimensions](preview.png)

Includes M3, M4, M5, M6, and M8 in four families (20 items):

| Family | Base dimensions |
| --- | --- |
| Socket head cap screws | DIN 912 |
| Countersunk socket screws | DIN 7991, 90 degrees |
| Hex nuts | DIN 934 |
| Heat-set inserts | CNC Kitchen, standard lengths |

DIN 912 applies to socket head screws; countersunk screws and nuts use their
own DIN tables. This version uses coarse metric thread pitches.

## Install

Clone the project and install it locally (the installer supports the FreeCAD
Python module paths used by Arch Linux):

```sh
git clone https://github.com/ka-no-creativity/freecad-fastener-varsets.git
cd freecad-fastener-varsets
python install.py
```

The installer uses FreeCAD's actual `getUserAppDataDir()` and creates a workbench
link in `Mod/FastenerVarSets` and a launcher link in `Macro`. Keep this source
folder in place. It will not replace unrelated existing files.

For a portable installation, copy this whole folder into your FreeCAD user
`Mod/FastenerVarSets` folder instead. FreeCAD 1.0+ is required; tested on 1.1.4
with Qt 6. The code uses FreeCAD's PySide compatibility module.

Restart FreeCAD and choose **Fastener VarSets** from the workbench selector.
The five toolbar commands are also in the **Fastener VarSets** menu. The optional
macro opens the chooser without switching workbenches. Commands can be added
to other workbenches using FreeCAD's toolbar customization.

## Use

1. Open the part you are designing.
2. Click **Choose fasteners**.
3. Check the needed fasteners. Select each row to edit its separate allowances.
4. Choose **Short object names** and **Short dimension names** independently;
   both start checked. The preview shows the resulting expression names.
5. Click **Create checked VarSets**.
6. In a sketch constraint's expression editor, use e.g.
   `M4_Cap.HoleDia`, `M4_Nut.LooseAF`, or `M4_Heat.InsertDia`.

Every allowance is a **total addition to the displayed dimension**, not per
side. `M4 + 1 mm = 5 mm` through-hole diameter. Lengths are millimetres.
Each type/size remembers its own allowances for next time. Naming settings are
remembered too; **Save settings only** saves them without creating objects.

Short object names are `M3_Cap`, `M3_Csk`, `M3_Nut`, and `M3_Heat` (and the
equivalent names for other sizes). Unchecking object shortening gives
`M3_SocketCap`, `M3_Countersunk`, `M3_Nut`, and `M3_HeatInsert`.

| Full dimension name | Short dimension name |
| --- | --- |
| `HoleDiameter` | `HoleDia` |
| `HeadPocketDiameter` | `HeadDia` |
| `HeadPocketDepth` | `HeadDepth` |
| `TapHoleDiameter` | `TapDia` |
| `LooseFitAcrossFlats` / `PressFitAcrossFlats` | `LooseAF` / `PressAF` |
| `LooseFitDiameter` / `PressFitDiameter` | `LooseDia` / `PressDia` |
| `NutPocketDepth` | `NutDepth` |
| `InsertHoleDiameter` | `InsertDia` |
| `InsertPocketDepth` | `InsertDepth` |

New VarSets always prefix base dimensions, allowances and source metadata with
`__`: for example `__HeadDiameter`, `__HoleAllowance`, `__LibraryId`,
`__FastenerKind`, `__Standard`, `__ThreadSize`, `__Manufacturer` and `__Model`.
The nominal nut across-corners expression is internal too: `__NutAcrossCorners`.
The short cutout names retain full explanations in their tooltips. Library JSON
keys and allowance preference keys keep their canonical, unprefixed names.

To adjust existing items, select their VarSets in the project tree and click
**Adjust allowances**. This uses the base values saved in that project and
updates existing objects, keeping expression references intact. Existing projects
retain their names and properties, including legacy unprefixed properties. Naming
options affect new creation only; JSON imports retain exported names. You can also
edit the VarSet's **Allowances** properties directly. Calculated **Cutouts**
properties update through local expressions. Use the dialog to validate new
allowances: direct property edits can create physically invalid dimensions.

Repeated creation/import always makes new copies with unique internal names.
It never replaces an existing VarSet. Use Adjust allowances when you intend
to change an existing item. Creation, import, and adjustment support Undo.

## Dimensions and allowances

| Item | Original dimensions | Independent allowances | Resulting cutout dimensions |
| --- | --- | --- | --- |
| Socket screw | nominal diameter, pitch, head diameter/height, hex-key size, tap drill | hole diameter, head recess diameter, head recess depth, tap hole diameter | `HoleDia`, `HeadDia`, `HeadDepth`, `TapDia` |
| Countersunk screw | same, plus countersink angle | same four allowances | same four results, keeping cone geometry consistent |
| Hex nut | nominal diameter, pitch, across flats, height | hole diameter, loose fit across flats, press fit across flats, pocket depth | `HoleDia`, `LooseAF`, `PressAF`, `LooseDia`, `PressDia`, `NutDepth` |
| Heat insert | nominal thread diameter, pitch, insert length/outside diameter, recommended hole diameter/depth, minimum wall thickness | screw clearance diameter, installation-hole diameter, insert pocket depth | `HoleDia`, `InsertDia`, `InsertDepth` |

For nuts, `LooseDia` and `PressDia` are **across corners**, useful for a
circular pocket or a hexagon's circumscribed circle. For Sketcher polygon
**circumradius**, use `M4_Nut.LooseDia / 2` or
`M4_Nut.PressDia / 2`. Across-corners values use the ideal regular
hexagon relation `across flats × 2 / sqrt(3)`, rather than the catalog's minimum
corner dimension. The fit allowance is added **across flats**; the diameter
then follows from that hexagon.

For countersinks, `HeadDia` is the mouth diameter and
`HeadDepth = (HeadDia - HoleDia) / (2 × tan(__CountersinkAngle / 2))`.
The head diameter allowance widens the mouth directly. Extra depth also widens
the mouth by `2 × depth allowance × tan(angle / 2)`. This preserves the head
angle. `__HeadHeight` remains the original catalog dimension; it is not the full
cone depth down to the through-hole intersection.

`__TapDrillDiameter` is the usual **cutting-tap Kernloch** diameter: 2.5, 3.3,
4.2, 5.0, and 6.8 mm for M3, M4, M5, M6, and M8 respectively. `TapDia`
adds a separate printer allowance. It is not a forming-tap size or the
theoretical thread minor diameter. Calibrate it for your printed material
before cutting threads.

Initial allowances are editable starting examples: hole +0.5, head diameter
+0.5, head depth +0.2, tap hole +0.0, loose nut across flats +0.3, press nut
across flats -0.1, nut depth +0.2 mm. They are not guaranteed fits for a printer.
Every allowance accepts positive, zero and negative values, stored as signed
FreeCAD distance properties and retained in preferences, JSON and FCStd files.
The dialog rejects non-positive dimensions,
tap holes reaching the thread's nominal diameter, reversed loose/press fits,
and a head pocket no wider than its hole.

CNC Kitchen inserts use these published dimensions in millimetres:

| Size | Insert length | Outside diameter | Installation-hole diameter | Minimum wall thickness |
| --- | --- | --- | --- | --- |
| M3 | 5.7 | 4.6 | 4.0 | 1.6 |
| M4 | 8.1 | 6.3 | 5.7 | 2.1 |
| M5 | 9.5 | 7.1 | 6.5 | 2.6 |
| M6 | 12.7 | 8.7 | 8.1 | 3.3 |
| M8 | 12.7 | 10.2 | 9.7 | 4.5 |

`InsertDia = __RecommendedHoleDiameter + __InsertDiameterAllowance` and
`InsertDepth = __RecommendedHoleDepth + __InsertDepthAllowance`.
The base blind-hole depth is insert length + 1 mm. Both insert allowances start
at zero, independently of the screw clearance-hole allowance (initially +0.5 mm).
Negative insert allowances can reduce the recommended hole dimensions while
the installation-hole diameter stays strictly between the thread and insert
outside diameters and the depth stays at least the insert length.

## Central JSON and project snapshots

**Edit central library** opens an editable JSON dialog and validates on Save.
The library affects future creations; project dimensions remain independent.
With FreeCAD 1.1 on Linux, the files normally live under:

```text
~/.local/share/FreeCAD/v1-1/FastenerVarSets/library.json
~/.local/share/FreeCAD/v1-1/FastenerVarSets/allowances.json
```

`library.json` holds editable base dimensions and their sources.
`allowances.json` holds the per-item allowances, naming settings and checked selection. Both are
ordinary indented JSON. They are separate so editing a standard dimension
does not overwrite printer settings. A library entry looks like:

```json
{
  "id": "DIN912_M4",
  "label": "M4 Socket cap (DIN 912)",
  "kind": "socket_cap",
  "standard": "DIN 912",
  "size": "M4",
  "dimensions": {
    "NominalDiameter": 4,
    "Pitch": 0.7,
    "HeadDiameter": 7,
    "HeadHeight": 4,
    "SocketAcrossFlats": 3,
    "TapDrillDiameter": 3.3
  }
}
```

Existing user libraries receive missing CNC Kitchen entries and their source
once, preserving entries with matching IDs and all custom dimensions. The
`upgrades` list records `cnc-kitchen-standard-inserts-v1`; subsequent intentional
deletions stay deleted. This upgrade changes future choices in the library;
project snapshots retain their saved values.

To transfer project VarSets, select them and choose **Export VarSets to JSON**.
With none selected, all VarSets in the active project are exported. In the next
project choose **Import VarSets from JSON**, tick the objects you need, and import.
Generated fastener snapshots can then be adjusted with **Adjust allowances**.

The exported JSON stores property types, units, groups, tooltips, values, and
local expressions. Expressions referencing other objects/documents are saved
as evaluated values, so the imported copy is independent. Export reports those
flattened expressions. Common scalar properties, enumerations, vectors and
scalar lists are supported. Unsupported property types produce an error before
writing; they are never silently omitted. Only conservative local expressions
are preserved. Object links and binary/custom properties are not supported.

## Dimension sources

The bundled JSON records the sources, so replacements can be checked easily:

- [Schrauben-Jaeger DIN 912, page 86](https://www.awh.eu/de/downloads-456.html?file=files/Demosystem/Dokumente/DIN912.pdf)
- [Aspen Fasteners DIN 7991, page 1](https://www.aspenfasteners.com/content/pdf/Metric_DIN_7991_spec.pdf)
- [Trojan Special Fasteners DIN 934](https://www.trojansf.co.uk/standards/din-934)
- [Thuermer Tools cutting-tap drill table](https://www.thurmer.com/special-sizes-faq/)
- [CNC Kitchen insert dimensions and design guidelines, page 2](https://cnckitchen.com/s/CNCKitchen_Heat-Set-Insert-Dimensions-and-Design-Guidelines.pdf)

Nut heights use the DIN 934 values (e.g. M5: 4 mm, M8: 6.5 mm), not ISO 4032
heights. Measure your actual hardware when fit matters.

## Verification

```sh
python tests/test_freecad.py
python tests/test_gui.py
```

The [example project](examples/M4-example.FCStd) and
[readable JSON snapshot](examples/m4-varsets.json) contain the four M4 items,
using short names and internal `__` properties. The insert demonstrates negative
installation-hole and pocket-depth allowances.

The first test exercises actual FreeCAD VarSets, all four naming combinations,
expression agreement, signed allowances for every family, JSON round trips,
name collisions, invalid geometry/import rollback, library upgrades, legacy
references, Undo and FCStd save/reopen without scripted proxies. The second uses
the real FreeCAD GUI offscreen with isolated settings and exercises insert
controls, naming previews, remembered settings, legacy/full/short snapshot editing,
Undo and import selection. Both require the installed
FreeCAD Python modules; the paths match this Arch installation.

To remove the local installation, remove only the two symlinks the installer
created. Keep the `FastenerVarSets` data folder if you want to retain your
central library and remembered allowances. Existing project VarSets remain
native FreeCAD objects.
