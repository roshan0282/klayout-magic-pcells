# klayout-magic-pcells

KLayout PCell libraries whose cells are drawn by Magic's own device
generators, one library per PDK:

| PDK | KLayout library | PCells | Magic's generator code |
|---|---|---|---|
| sky130A | `sky130_magic` | 73: 60 devices, 13 box-paint generators | `sky130A.tcl`, namespace `sky130` |
| gf180mcuD | `gf180mcu_magic` | 59: 53 devices, 6 box-paint generators | `gf180mcuD.tcl`, namespace `gf180mcu` |
| ihp-sg13g2 | `sg13g2_magic` | 53: 39 devices, 14 box-paint generators | `ihp-sg13g2.tcl` and the `ihp-sg13g2-*.tcl` files it sources, namespace `sg13g2` |
| ihp-sg13cmos5l | `sg13cmos5l_magic` | 41: 31 devices, 10 box-paint generators | `ihp-sg13cmos5l.tcl` and its `ihp-sg13cmos5l-*.tcl` files, namespace `sg13cmos5l` |

Each PCell asks the PDK's generator in Magic to draw the device, then copies
the GDS that Magic writes into the PCell cell. A device placed in KLayout
therefore has the same polygons and labels as the same device generated in
Magic. The values a device PCell stores are the ones Magic's own parameter
dialog shows after you type yours and press its Create button, and the cell
is the one Create makes. When you edit the instance later, the PCell does
what Magic's "Edit device" dialog does with the change, and the cell is the
one its Apply button makes (see [Values as Magic's dialog shows
them](#values-as-magics-dialog-shows-them)). The box-paint generators are
the via, contact, substrate-contact, guard-ring and well commands of
Magic's "Devices" menus; their PCells take the box size (see [Box-paint
generators](#box-paint-generators)).

Status: version 0.5.0. The repository is on GitHub as
vproHacks/klayout-magic-pcells. The parity harness (see
[Tests](#tests)) passes on every PDK; the results of the last full run are
under [Last full run](#last-full-run). The libraries load under
`klayout -b -rm`, from the Salt autorun under `klayout -zz`, and in the full
KLayout GUI under Xvfb. [guide.md](guide.md) walks through installing and
using them, with screenshots of that GUI, including the warning icons that
the parameter form shows when Magic corrects a value.

The design is in [docs/design.md](docs/design.md). It was written for
sky130A alone. Where this README and the design disagree, the README
describes the code as it is; the differences are listed under
[Changes from the design](#changes-from-the-design).

## Why Magic is the backend

The PDKs' own KLayout PCells (sky130A's `skywater130`, gf180mcuD's
`gf180mcu`, IHP's `SG13_dev`) draw each device with their own Python code,
so their geometry is independent of Magic's. Several steps that decide
Magic's final geometry happen only when Magic writes GDS, through the
`gdsii` output style of the PDK's Magic tech file:

- contact cuts: the `.mag` of an nfet holds contact areas, and the GDS gets
  the individual cut squares (0.17 µm licon and mcon on sky130A, 0.22 µm
  contacts on gf180mcuD);
- resistor slots on the sky130A high-poly resistors, and the via cut arrays
  of the MIM capacitors;
- label moves from the drawn layer to the contact layer (the sky130A MIM
  cap's C2 is drawn on metal3 and written on 71/5);
- the boundary box made from the `FIXED_BBOX` property (235/4 on sky130A,
  0/0 on gf180mcuD, 189/4 on the IHP PDKs);
- the fixed-layout devices, whose bytes Magic copies from the vendor GDS in
  `libs.ref` (sky130A, gf180mcuD) or draws from layout scripts in
  `libs.tech/magic` (the IHP PDKs).

This library doesn't reproduce those steps in Python. It takes the GDS that
Magic writes as the device, except for its GDS NODE elements: KLayout's GDS
reader drops them, and the vendor GDS of five sky130A fixed devices holds
them (18 to 156 each, on 67/20, 68/20, 69/20 and 70/20). They carry no mask
geometry, and the PCells don't have them. The harness counts them (see
[Tests](#tests)).

## Parity definition

Parity here means: for a given set of typed values, the PCell stores the
values that Magic's own parameter dialog shows after those values are typed
into it (with Return) and its Create button is pressed, and the PCell cell,
flattened, has the same polygons on every GDS layer/datatype, the same
number of shapes on each layer, and the same label texts (string, position,
rotation, mirror, size, justification and font) as the GDS of the cell that
Create makes. For an edit of an existing instance, the same holds for the
values typed into the "Edit device" dialog that Magic reopens on it and the
cell its Apply button makes. For a box-paint
generator, which has no dialog, the reference is the GDS that Magic writes
when the generator is called with no arguments on a box of that size, the
way Magic's menu entries call these generators. The comparison is
an XOR per layer at a common database unit, with no tolerance and no
alignment. KLayout's GDS reader doesn't keep a text's font, so the harness
reads the fonts from the raw GDS records of both files. Cell names,
hierarchy, GDS properties and timestamps are not compared. Versions 0.4 and
earlier compared a device with `magic::gencell` given the typed values; the
harness keeps that as a second reference where it applies (see
[Tests](#tests)).

## Requirements

- KLayout 0.30.5 or later, with Python. Only 0.30.11 has been tested.
- Magic with Tcl. Tested with 8.3.681.
- At least one of the PDKs, as the iic-osic-tools image installs them under
  `/foss/pdks`. Tested: sky130A and gf180mcuD from open_pdks 026824c7,
  ihp-sg13g2 at commit 7e53c777 (tech version 1.0.1), ihp-sg13cmos5l at
  commit ff32f48c (tech version 1.0.0). Other gf180mcu variants (A, B, C, E,
  F) and sky130B are not supported.
- Linux. Windows and macOS are out of scope.
- For use from plain `python3`, the `klayout` pip module (0.30.11 tested).

The image `hpretl/iic-osic-tools@sha256:3c371645b19c6f6564dc8c7b21e39ad1c1833d274fe5b85639afe1ba9d7987e7`
has all of these. The IHP rcfiles in that image end with
`source /foss/tools/osic-multitool/iic-magic-bindkeys`, a file of the image.
In a test of version 0.3 with that line pointing at a file that doesn't
exist, as it would with the IHP PDKs installed elsewhere, the library
registered and generated devices as usual. The stamp digest changed,
because the rcfile is one of the `libs.tech/magic` files it covers (see
[Stamps and audit](#stamps-and-audit)).

## Installing

The repository is a KLayout Salt package (it has a `grain.xml`). Clone it
and link it into the `salt` folder of your KLayout home:

```sh
git clone https://github.com/vproHacks/klayout-magic-pcells.git /path/to/klayout-magic-pcells
mkdir -p ~/.klayout/salt
ln -s /path/to/klayout-magic-pcells ~/.klayout/salt/klayout-magic-pcells
```

In the iic-osic-tools image the folder is `/headless/.klayout/salt/`. The
next time KLayout starts, it runs `pymacros/klayout_magic_pcells.lym`, which
registers a library for every installed PDK. Installing through the Salt
manager or `klayout -y` has not been tried.

Check the setup:

```sh
PYTHONPATH=/path/to/klayout-magic-pcells/python python3 -m klayout_magic_pcells doctor
```

`doctor` prints every setting and where it came from, then, for each
selected PDK, starts Magic, compares the running Magic's device defaults and
box-paint generators with the shipped manifest (the generator list built from
Magic, see [Devices](#devices)), and times one generation (about 20 ms on
sky130A in the image). A line starting `PROBLEM:` names what is missing.
Outside the image, Magic has to be on `PATH` and the PDKs under `PDK_ROOT`
(default `/foss/pdks`), or [Configuration](#configuration) has to say where
they are.

## Usage

**In the GUI**, the libraries are `sky130_magic`, `gf180mcu_magic`,
`sg13g2_magic` and `sg13cmos5l_magic`, and the PCells carry Magic's device
names, such as `sky130_fd_pr__nfet_01v8`, `nfet_03v3` or `sg13_lv_nmos`, and
the box-paint generators' names, such as `via1` or `subconn_guard`. The
libraries aren't bound to a technology, so each is listed under every
technology. [guide.md](guide.md) shows placing and editing devices step by
step.

**In batch**, `klayout -b` skips autorun macros, so name the macro:

```sh
klayout -b -rm /path/to/klayout-magic-pcells/pymacros/klayout_magic_pcells.lym -r my_script.py
```

**From plain Python** with the `klayout` pip module:

```python
import sys
sys.path.insert(0, "/path/to/klayout-magic-pcells/python")
import klayout.db as db
import klayout_magic_pcells as kmp

libs = kmp.register()         # {"sky130A": <library>, "gf180mcuD": <library>, ...}
lib = kmp.register("sky130A") # one PDK: its library, or None with one logged error
ly = db.Layout()
top = ly.create_cell("TOP")
m1 = ly.create_cell("sky130_fd_pr__nfet_01v8", "sky130_magic", {"w": 1.5, "l": 0.5, "nf": 3})
v1 = ly.create_cell("via1", "sky130_magic", {"w": 1.0, "h": 0.5})
top.insert(db.CellInstArray(m1.cell_index(), db.Trans()))
top.insert(db.CellInstArray(v1.cell_index(), db.Trans(db.Vector(3000, 0))))
ly.write("out.gds")
```

`register()` without an argument registers every PDK the configuration
selects (see [Configuration](#configuration)) and returns a dict from PDK to
library, with None for a PDK that couldn't register. Version 0.2's
`register()` returned the sky130A library itself; code that tested it
against None should call `register("sky130A")`.

`create_cell` stores the values it is given and draws what Magic's dialog
makes of them (see [Values as Magic's dialog shows
them](#values-as-magics-dialog-shows-them)). To store the corrected values
too, as the GUI does, pass them through `dialog_values`. To edit that
instance as Magic's "Edit device" dialog and Apply would, change some
values in the result and pass it through `dialog_values` again:

```python
v = kmp.dialog_values("sky130_fd_pr__res_high_po_0p69", {"w": 1.0})  # {"w": 0.69, "val": 1028.0, ..., "kmp_dialog": "..."}
r1 = ly.create_cell("sky130_fd_pr__res_high_po_0p69", "sky130_magic", v)
v2 = kmp.dialog_values("sky130_fd_pr__res_high_po_0p69", dict(v, l=2.0))  # Edit device, then Apply
r2 = ly.create_cell("sky130_fd_pr__res_high_po_0p69", "sky130_magic", v2)
```

`dialog_values(device, values, pdk=None)` needs `pdk` when several
registered libraries have the device.

The package also has a command line, run with `PYTHONPATH` set as for
`doctor` above:

```sh
python3 -m klayout_magic_pcells devices -v            # PCells and their parameters, per PDK
python3 -m klayout_magic_pcells check sky130_fd_pr__nfet_01v8 w=0.1 l=0.1
python3 -m klayout_magic_pcells generate sky130_fd_pr__cap_mim_m3_1 w=5 l=10 -o cap.gds
python3 -m klayout_magic_pcells check --pdk gf180mcuD rm1 w=0
```

A device is looked up in the selected PDKs' manifests; a name that more than
one PDK has (`rm1` to `rm5`, `via1`, `nwell`, ...) needs `--pdk`.

`check` types the values into the device's New device dialog, as the
PCell form does for a new instance, presses Create (see [Values as Magic's
dialog shows them](#values-as-magics-dialog-shows-them)), and shows what
the dialog then shows that differs from what you typed, in Magic's own
text:

```
$ python3 -m klayout_magic_pcells check sky130_fd_pr__nfet_01v8 w=0.1 l=0.1
sky130_fd_pr__nfet_01v8: Magic's dialog shows w=0.42 (entered 0.1)
sky130_fd_pr__nfet_01v8: Magic's dialog shows l=0.15 (entered 0.1)
  message: Mos width must be >= 0.42 um
  message: Mos length must be >= 0.15 um
$ python3 -m klayout_magic_pcells check sky130_fd_pr__res_high_po_0p69 w=1.0
sky130_fd_pr__res_high_po_0p69: Magic's dialog shows w=0.69 (entered 1.0)
sky130_fd_pr__res_high_po_0p69: Magic's dialog sets val=1.028k
  message: Resistor width must be <= 0.690 um
```

For a device with no `_check` proc (ihp-sg13g2's `rm6` and `rm7`) or whose
`_check` raises an error, `check` says so. Magic's `gencell_create` catches
the error and draws with the unchecked values, and so does the PCell. The
manifest probes found `_check` procs that raise "integer value too large to
represent" at `w = 0` on 17 sky130A resistors, on gf180mcuD's `npolyf_s`,
`ppolyf_s` and `rm1` to `rm5`, and on the IHP PDKs' `rsil`, `rppd`, `rhigh`
and `rm1` to `rm5`; IHP's `inductor3` raises at `turns 2.5`.

The dialog can hand `_draw` a value that `_draw` fails on. When Create
writes an empty cell, `check` says so, prints Magic's messages and exits
1:

```
$ python3 -m klayout_magic_pcells check sky130_fd_pr__res_high_po_0p35 val=10000 l=0
sky130_fd_pr__res_high_po_0p35: Magic's dialog shows val=1113.259 (entered 10000.0)
sky130_fd_pr__res_high_po_0p35: Magic's dialog shows l=1.218u (entered 0.0)
sky130_fd_pr__res_high_po_0p35: Magic draws nothing for these values
  message: can't use non-numeric string as operand of "+"
```

For a box-paint generator, `check` reports the box Magic uses after rounding
to its grid (`Magic paints a 0.265 x 1.0 um box (entered 0.263 x 1.0)`), or
`Magic paints nothing` with the generator's message when the box is below
its minimum. `check` exits 0 when Magic draws something, 1 when it draws
nothing or fails, and 2 for a value it refuses or can't parse (`turns=2.5`
for an int, `w=abc`).

Each time KLayout asks a PCell to draw a variant (the cell KLayout makes for
one set of parameter values), the PCell's `produce` call builds the request
for Magic, looks in an in-memory memo and then in the disk cache, and only
then asks Magic. One Magic process (`magic -dnull -noconsole`) runs per PDK
in each KLayout process, started when the library registers. `register()`
starts the processes of all PDKs before it waits for any; with all four PDKs
it took 0.63 s in the image, and one generation takes 15 to 20 ms. Each
Magic process is about 72 MB (measured on sky130A in version 0.2).

## Parameters

Every entry, checkbox and selectlist of Magic's dialogs is a PCell
parameter, with two exceptions: the device-type switch (below) and the "Add
top gate contact" and "Add bottom gate contact" checkboxes (`topc`, `botc`)
of the IHP PDKs' four RF FETs, whose names the devices' defaults lack (see
[Known limitations](#known-limitations)). The types come from the manifest,
a JSON file per PDK built from Magic (see [Devices](#devices)). A value you
change is typed into Magic's dialog as the text in the last column (for a
box-paint generator, given to its menu call as that text); what the PCell
then stores and draws is what the dialog makes of it (see [Values as Magic's
dialog shows them](#values-as-magics-dialog-shows-them)):

| In Magic's dialog | PCell type | Typed into Magic's dialog as |
|---|---|---|
| number entry | double | the 15 significant digits that KLayout saves, rounded to 12, written like a Python float (`0.35`, `31.0`); any zero as `0.0`; a value equal to Magic's default as Magic's default text (`0.420`) |
| `nf`, `ng`, `m`, `nx`, `ny`, `turns` | int | `3` |
| checkbox | boolean | `1` or `0` |
| the "[+/-](%)" coverage entries (`viasrc`, `viadrn`, `viagate`, `viagb`, `viagr`, `viagl`, `viagt`, `ccov`) | string | the text as typed, whitespace included, if it is a number; anything else is refused (see below) |
| a selectlist other than the device switch (gf180mcuD `guard_type`; IHP `via` `metalbot`, `metaltop`, `orient`, `pattern`; IHP `bondpad` `shape`; sg13cmos5l `cap_cmomf` `mmin`, `mmax`) | string with Magic's choices | the choice; anything else is refused |
| IHP `via` `nxcuts` and `nycuts` | string | the text as typed if every word is a number (`2`, or `1 2` for one value per via layer); anything else is refused |

The IHP `_check` procs test counts with `string is int`, so `2.0` fingers
draw one finger with the message `NG must be an integer!`; `ng` and `turns`
are therefore ints. The selectlists change geometry: on gf180mcuD,
`ppolyf_u` with `guard_type nwell` replaces its 204/0 (LVPWELL) ring with
21/0 and 32/0. The device-type selectlist `gencell`, which switches Magic's
dialog to another device, is not a parameter; each device is its own PCell.

The coverage entries are strings because Magic reads their first character as
an anchor: `+50`, `-50` and `50` are three different layouts, and a KLayout
double has no way to hold `+50`. Whitespace counts too: ` -50` starts with a
space, so it has no anchor and draws like `50`. Keys that Magic's dialog
doesn't show (`lmin`, `wmin`, `class`, `rho` and so on) are not PCell
parameters; Magic uses its own values for them.

The generator code evaluates the coverage strings with an unbraced
`expr abs($viagb)` (sky130A.tcl and the IHP FET code), and IHP's `via_check`
does the same to each word of `nxcuts`. Tcl substitutes any `[command]` or
`$variable` inside such a value, so a file whose instance held
`viagb = [exec ...]` would run that command as soon as it was opened. The
PCell therefore sends a coverage string only if it is a decimal number with
an optional `+` or `-` in front and optional spaces or tabs around it, such
as `+50`, `-50`, `50.5`, ` -50` or `1e2`, a number list only if every word is
a decimal number, and a choice only if it is one of Magic's. For anything
else (`abc`, an empty string, `0x32`, `[exec ...]`) it draws the error marker
described under [If Magic is missing or fails](#if-magic-is-missing-or-fails),
and Magic never sees the value. In the GUI form that parameter should get an
error icon (written from KLayout's source, not seen on screen), and the CLI
`check` exits 2. Magic itself would have reset some of these values (on a
MOSFET `abc` becomes 0, with a message) and drawn nothing for others, so for
text that is not a number the PCell differs from Magic on purpose. The Magic
server also answers with an error for any value that contains `[`, `]`, `$`
or a backslash, whoever sends it.

Floats are rounded because KLayout 0.30.11 doesn't keep doubles exactly in a
saved file. It writes a double parameter with 15 significant digits and
parses that text back up to one ULP off: in a new process `0.35` reopens as
`0.35000000000000003`, and `4.257627156815` as `4.2576271568149995`. Without
rounding, the request, and with it the cache key, would change every time a
file is reopened; for a device, the reopened values would no longer match
the stored dialog form, and the dialog would run again. The PCell rounds the
15-digit text that KLayout saves, not the double, to 12 digits, so the value
and its reopened double give the same text. Version 0.3 rounded the double:
`4.257627156815` was sent as `4.25762715682`, and after a save and reopen as
`4.25762715681`. In a test of version 0.3, 22 of 300 values at or one ULP
from a 12-digit tie changed their request that way; none of the same 300
does with this version. KLayout saves -0.0 as 0, so any zero is sent as
`0.0`.

A value with 13 or more significant digits is therefore not the text Magic
gets: `0.4244999999999` is sent as `0.4245`. Magic's cell name and checked
values can then differ from Magic given the longer text, because Magic
rounds to three decimals for the name. Where this was tried, the geometry
was the same: sky130A `nfet_01v8` with `w` at 0.4225, 0.4275, 1.0045 and
5.005, each against the same value 1e-14 lower, drew the same polygons in
Magic. Floats always carry a decimal point because the generator code does
arithmetic with Tcl's `expr` and `/`, which divide two integer strings as
integers.

Apart from refusing values that the generator code would evaluate, the PCells
add no limits, no snapping and no choices of their own.

### Values as Magic's dialog shows them

A device PCell stores the values that Magic's own parameter dialog shows
after you type yours and press Create, and draws what Create makes. Every
later change to the instance is an edit in the dialog that Magic reopens on
the instance after Create ("Edit device"), followed by its Apply button.
Version 0.4 stored the values as typed and drew what `magic::gencell` made
of them. Box-paint generators have no dialog in Magic (their menu entry
paints into the box as it is), so their PCells keep the box as typed.

Magic's dialog (`toolkit.tcl`) works like this:

- When you press Return in an entry, leave it, click a checkbox or pick a
  choice, the widget's binding runs the device's `_check` and its
  dependency callback (`res_recalc` on a resistor's `val`, `l`, `w` and
  `nx`; `diode_recalc`; `cap_recalc`) on the whole form, two or three
  times, and writes the corrected values back into the form.
- Create runs `_check` once more, draws, stores that checked dict on the new
  cell, and reopens the dialog as "Edit device" on the new instance, which
  shows the checked values. A fixed device keeps no values on its cell: its
  dialog reopens with `nx` and `ny` from the array and `deltax` and
  `deltay` computed from the array's pitch, so a single copy shows
  `deltax 0.0` whatever was typed.
- Apply runs `_check` once and compares the device name plus Magic's hash
  of the result with the instance's cell name. When they are equal it
  leaves the instance as it is; otherwise `gencell_create` checks the
  values a second time and draws a new cell.

The PCell does the same through its Magic server. The values that differ
from what the dialog shows are typed into it one after another, in the
order of the dialog's rows, and each widget's binding runs once, as
pressing Return runs it. An instance's first edit then presses Create, and
every later one Apply. The PCell stores what the dialog shows when it
reopens on the instance. Magic computes every correction, check and cell
name; the plugin's Python code doesn't correct a value itself.
[docs/design.md](docs/design.md) section 4.5 has the details.

Some results on sky130A, which the parity harness also gets from the real
dialog:

| Typed | Stored: what Magic's dialog shows after Create |
|---|---|
| `nfet_01v8` `w 0.1 l 0.1` | `w 0.42`, `l 0.15` |
| `res_high_po_0p69`, nothing typed | `val 1028.0` (Magic's text `1.028k`); the New device dialog opens with `val 463.480` |
| `res_high_po_0p69` `w 1.0` | `w 0.69`, `val 1028.0` |
| `res_high_po_0p35` `val 10000` | `val 1570.0` (`1.57k`); the length stays 0.5 µm |
| `res_high_po_0p35` `l 0 val 10000` | `val 1113.259`, `l 1.218e-06` (`1.218u`): Magic draws nothing, because `_draw` fails on `1.218u` |
| `res_generic_po` `l 0` | `l 1.65`, with "Resistor length must be >= 1.650 um" |
| `diode_pd2nw_05v5` `w 0.225` | `w 0.45`, `area 0.2025` (`202.5m`) |
| `cap_mim_m3_1` `l 0 val 50` | `val 9.52`, `l 2.0`: `val` is the dialog's first row, so it is typed first; `magic::gencell` gives `l 11.242` |
| `npn_05v5_W1p00L1p00` `deltax 1.0` | `deltax 0.0`: one copy, so the reopened dialog computes 0 from the pitch; Create drew with 1.0, which a single copy doesn't use |

The state goes with the instance as the hidden parameter `kmp_dialog`: the
form that Create or Apply was pressed with, which is what the PCell sends
Magic, and the text of every widget of the dialog that reopens on the
instance. Both include widgets whose name the device's defaults lack: the
dialogs of the IHP PDKs' four RF FETs have "Add top gate contact" and "Add
bottom gate contact" checkboxes (`topc`, `botc`) that their defaults don't
have, so the dialog opens them empty and its Create gets `topc ""` and
`botc ""`. The PCell sends them too; they aren't PCell parameters (see
[Parameters](#parameters)). Compared with `magic::gencell` (and with
version 0.4), that changes Magic's cell name, and at the minimum width the
geometry. The state names its device. Two devices of a PDK often have
dialogs with the same widget names, and a state another device made is not
used: the values are typed into the device's own New device dialog, as
Magic's "Device type" switch does (on sky130A, `nfet_01v8`'s values given
to `nfet_g5v0d10v5` show `l 0.50`).

A value that the dialog shows in Magic's SPICE notation (`1.028k`,
`202.5m`, `1.218u`) shows in its field as the number `magic::spice2float`
gives for it. Every PDK's `magic::spice2float` maps the suffix `n` to
`* 1.0 e-9`, which isn't a number, so Magic reads none from `170.0n` (and
its `_draw` fails on it): `res_generic_l1` with `l 0` shows `170.0n` after
Create, gf180mcuD's `rm1` to `rm5` show `99.999n`, and the PCell field
keeps `0.0`, with a warning that names Magic's text.

**In the GUI** ([guide.md](guide.md) has the screenshots). "Seen" marks
what KLayout 0.30.11 showed under Xvfb; the rest comes from KLayout's
source and from the form's callback, driven in a backend test.

- When you change a field in the Instance tool's PCell tab and press Return
  (or leave the field), the field changes to what Magic's dialog shows after
  Create, with a warning icon and a tooltip (seen: `Magic's dialog shows
  0.15 (entered 0.1): Mos length must be >= 0.15 um`).
- A field that Magic's dialog shows in SPICE notation shows Magic's number,
  with a warning icon (seen: `res_high_po_0p69`'s `val` shows 1028, with
  `Magic's dialog shows 1.028k here, which this field can only show as
  1028.0`).
- The PCell tab doesn't give the PCell its stored dialog state, so each
  change there is typed into a New device dialog together with every value
  that differs from the defaults (seen: on `cap_mim_m3_1`, `l 5` and then
  `w 3` put a warning on `val`, `Magic's dialog shows 33.04 (entered
  22.66)`, though `val` wasn't typed).
- In the Properties dialog of a placed instance, a change is made when you
  leave the field, as Magic's Edit device dialog and Apply make it (seen;
  Return there presses the dialog's Ok button). That dialog showed no icon
  for a correction: `w 0.3` on an `nfet_01v8` came back as 0.42, and the
  warning was only in the Log Viewer.
- A field that the dialog changed as a consequence of another edit gets an
  information icon (`Magic's dialog sets this to ... (was ...)`), unless
  Magic shows it in SPICE notation. This icon hasn't been seen on screen.
- An edit that Apply doesn't take, because the values give the instance's
  own cell name (`w 0.1` on an `nfet_01v8` that Create made with the
  defaults), puts the fields back, with a warning that says so.
- When Magic draws nothing for the values, the fields the dialog corrected
  (or, if it corrected none, the first field) get a warning that says so,
  with Magic's message. On a box-paint generator, which has no dialog, the
  warning goes on the side that Magic's message names (seen:
  `Magic draws nothing: Via1 width must be at least 0.26um` on `w`).
- A refused value gets an error icon.

The callback makes the variant (Magic's Create or Apply), so the form asks
Magic on every edit, also with `KMP_LAZY=1`. The dialog's corrections and
Magic's messages also go to KLayout's log as warnings, in the GUI and
outside it.

**Reopening a file and refreshing a library** keep the values and the
drawing. Values that the stored dialog shows aren't typed into the dialog
again, although KLayout runs the PCell's coerce on every instance (when it
opens a file, before every produce, and in `Library.refresh()`, which keeps
what coerce returns). Typing them again would change some devices, because
`_check` isn't idempotent: on sky130A, `res_xhigh_po_5p73` with a typed
`val` shows `l 5.997`, and typing that `val` again would make it `l 5.994`,
another cell. The request,
the cache key and the cell name come from the stored state, so a reopened
variant is the one that was saved. A backend test saves such devices to GDS
and OASIS, reopens them in fresh processes with the disk cache off,
refreshes the library and saves and reopens again, and requires the same
parameters and geometry each time with no dialog run. The parity harness's
round trips check the same on part of each PDK's sweep.

**In batch**, `Layout.create_cell(device, library, values)` stores `values`
as given and draws what the dialog makes of them: KLayout keeps a PCell's
coerced values only in the GUI form and on a library refresh. The result is
the same after a reopen, because the correction depends on the stored values
alone; the disk cache keeps the dialog's results as well as the GDS, so a
reopened file needs no Magic call for variants that are cached.
`dialog_values()` returns the values the GUI would store (see
[Usage](#usage)), and given those values with some changed, it makes the
edit Magic's Edit device dialog and Apply make. `Library.refresh()` stores
the corrected values of every instance (run on `res_high_po_0p69` made
with `w 1.0`: `w 1.0` became `0.69`, `val 1028.0`, with the state in
`kmp_dialog`). The CLI's `generate` stores the corrected values.

**Where the PCell differs from Magic's dialog.** The model is "type each
changed value and press Return, then Create for an instance's first edit and
Apply for every later one". Magic's dialog can be used in other ways, and
where `_check` isn't idempotent or the order of the edits matters, they give
other values:

- A value typed and followed by Create (or Apply) with no Return or Tab
  runs no binding. Create then checks the form once, which is what
  `magic::gencell` does with the typed values. On the sweep's points with
  one typed value, on devices whose dialog has no widget beyond their
  parameters, the harness's path A (see [Tests](#tests)) is therefore this
  interaction. In the last full run it got other checked values than
  Return on 738 of those 4,293 points and other shapes on 22 (counts per
  PDK under [Last full run](#last-full-run)). For example,
  `res_generic_po` with `l 0` comes out as an empty cell, where Return
  shows `l 1.65` and Create draws it.
- Leaving a field (Tab, or a click into the next one) runs its binding
  again, and so do Return in an unchanged entry and Apply with no field
  changed. Review 3, a review of version 0.5's dialog model on
  2026-11-23, ran path D (see [Tests](#tests)) on the points with several
  typed values, with each entry's leave binding run before the next entry
  was typed;
  over the four PDKs, two points then drew another width, both on sky130A:
  `res_high_po_5p73` random:1 (`w 1.87`, where the PCell draws `5.730`)
  and `res_xhigh_po_5p73` random:5 (`w 5.325` against `5.730`). Both were
  reproduced for this version with the review's driver.
- A Magic user can type the values in any order.
- In KLayout's form each confirmed field is one edit, so two fields changed
  one after the other are Create and then Apply, where a Magic user may type
  both before Create. `dialog_values()` with several values types them into
  one dialog.
- Apply places a cell of the Magic session whose name the edit gives, when
  one exists (another instance with those values), instead of drawing one;
  the PCell always has Magic draw it.
- An instance with no stored state (made with `create_cell` and typed
  values, or saved by an earlier version) counts as not created yet: its
  next edit goes into the New device dialog.
- On sky130A's `res_high_po_5p73` and `res_xhigh_po_5p73` with `snake 1`
  and `l` below 5.73 µm, every one of these choices can decide the width:
  `res_check` sets `w` to 5.73 on one pass and back to `l` on the next (its
  `wmin` clamp and its "Snake resistor width must be < length" test each
  read the other's result), so `l 1.87` gives `w` 1.87, 5.730, 1.87, 5.730
  on four passes. This is a bug in the PDK's code; a backend test checks
  that Magic's `_check` still does this.

**Files saved by version 0.4 or earlier** hold the values as typed and no
`kmp_dialog`, and files saved by version 0.5 before review 3's fixes (never
released) hold another form of it (the form from before Create, `"v": 1`).
This version treats both like values given to `create_cell`: it types them
into the New device dialog and draws what Create makes. Where that differs
from what `magic::gencell` made of them, the device comes out differently
from how it was saved; `audit --regen` lists those cells. The harness's
comparison with `magic::gencell` shows how often that happens per PDK (see
[Last full run](#last-full-run)).

### Magic behaviour the PCells reproduce

Parity means these come out of the PCells exactly as Magic has them:

- MOSFET `w` is the width of one finger. `w 1.5 nf 3` is 4.5 µm of total
  width. The PCell form calls it "Finger width".
- Off-grid values are not snapped. The sky130A drawing rounds W and L to
  0.01 µm, so a requested `w 0.425` is drawn 0.43 µm wide, and two inputs
  that draw the same geometry are two different variants. Box-paint sizes
  are rounded to Magic's 5 nm internal grid (0.263 becomes 0.265).
- A negative box-paint size puts the box left of or below the origin, as
  Magic's `box values 0um 0um -1um 1um` does: sky130A `via1` with `w -1 h 1`
  is painted from x = -1 to 0 µm, with its metal reaching to x = -1.05 and
  0.05. A size of zero, `inf` or `nan`, or one too large for Magic's integer
  coordinates, comes out below the generator's minimum (Magic reads `inf`
  and `nan` as -2147483648 internal units), and Magic paints nothing.
- `_check` recalculates `val`, `area` and `peri`, from the size before its
  own clamp; the dialog's later passes compute them again from the clamped
  size. sky130A `diode_pd2nw_05v5` with `w 0.225` is drawn 0.45 × 0.45 µm;
  its dialog shows `area 202.5m`, where `magic::gencell`, with one
  `_check`, reports `area=101.25m peri=1.35`.
- Zero sizes give an empty cell on some devices, where the dialog leaves a
  SPICE string in the form (sky130A's diodes with `w 0` or `l 0` show
  `451.111m`) and `_draw` then fails on it, or the size stays 0 (the metal
  resistors), or `_check` itself fails. Magic writes a cell with no shapes; the PCell
  writes the same empty cell and logs a warning rather than drawing the
  error marker; `generate` and `check` exit 1 and `audit` reports
  `empty cell`. A `_draw` that fails for another reason, such as a PDK file
  edited so that it raises (a backend test does this on every PDK), ends the
  same way: `gencell_create` catches the Tcl error, prints it and leaves the cell
  empty, so the PCell can't tell the two apart. Whether an empty device
  should get the error marker instead is an open question for the project
  lead. The sweeps list every empty output per PDK.
- Some fixed devices are always empty: gf180mcuD's `eFuse` places the stub
  `eFuse_0.mag` (the real cell is `efuse_cell`), `npn_00p54x08p00` asks for
  `npn_npn_00p54x08p00_0` (a stub; the real `npn_00p54x08p00_0.mag` exists
  and isn't used), and `npn_00p54x10p00` places a stub, with no 10p00 GDS in
  `libs.ref`.
- gf180mcuD's two substrate-contact generators paint layer names that its
  tech file doesn't define (`subdiffc`, `mvsubdiffc`), so Magic prints
  "Unrecognized layer" and writes only a 204/0 (LVPWELL) box.
- Fixed devices (`nocell` in Magic) place the vendor or script-drawn cell
  with `nx` × `ny` copies at a pitch of `xstep + deltax` by
  `ystep + deltay`. `fixed_check` prints `NY must be >= 1` for `ny 0` but
  resets `nx` instead of `ny` (sky130A.tcl line 8070; the same code is in
  gf180mcuD and the IHP PDKs), so `ny 0` draws one device. The sky130A
  photodiode's own drawing loop runs zero times for `ny 0`: it draws a
  21.36 × 13.36 µm guard ring with no photodiode in it.
- Labels: sky130A writes texts on the `*/5` layers and no `*/16` pin shapes;
  `cap_var*` and the photodiode have no labels, the `g5v0d16v0` FETs have no
  D label, and the MIM cap's C2 is on 71/5. gf180mcuD's drawn devices carry
  no labels at all (its Tcl has no `label` command); its fixed devices carry
  vendor texts on 34/0. The IHP PDKs write texts on datatype 25, pin shapes
  on datatype 2 for some devices, and device-name texts on 63/0.
  `npn13g2l` and `npn13g2v` call `label E c +m2`, which Magic 8.3.681
  rejects (`Unknown layer: +m2`), so they have no emitter label; `npn13g2`
  loses its `+comment` text the same way.
- Coordinates finer than 5 nm: four sky130A fixed devices
  (`pnp_05v5_W0p68L0p68`, `rf_test_coil1` to `3`) have shapes on 83/44 off
  the 5 nm grid in the vendor GDS, and ihp-sg13g2 `npn13g2` has its E label
  at y = 0.007 µm. They are exact in a host layout with a database unit of
  1 nm or 0.5 nm and get rounded at 5 nm; `audit` reports it.
- `cap_cmomf` (sg13cmos5l) has its lower-left corner at the origin; every
  other drawn device is centred.
- A generator that places a child cell it creates once and reuses
  (ihp-sg13g2 `npn13g2` places `npn13g2_base`) gets the same child in later
  requests, as in one Magic session. The server keeps such cells instead of
  restarting Magic.

The library avoids these Magic behaviours instead of reproducing them:

- `mos_check` loops forever on sky130A and the IHP PDKs when a MOSFET or
  varactor has both `w` and `l` above 28 µm, whatever `nf` (`ng`) and `m`
  are: its tap-spacing loop sets `w` to 29 and then tests the same condition
  again, printing `Transistor width must be < 29 um` on every pass. Magic's
  own dialog hangs on these values too. The server counts the messages each
  request prints, and once one message has been printed 10,000 times it stops
  the request, which ends before anything is drawn. The PCell then draws the
  error marker, in about 0.1 s and without restarting Magic. gf180mcuD's
  loop ends (at `w` 37).
- Magic's cell name is the device name plus a hash of the values, rounded to
  three decimals and with a leading `+` dropped. `viasrc 50` and
  `viasrc +50` get the same Magic cell name and different geometry. In one
  Magic session, the second request paints into the cell that the first one
  made, so the cell ends up with both layouts painted over each other. The
  backend deletes each cell after writing it, and its cache key uses the text
  you entered.
- Generators that change Magic's session and don't change it back: a failed
  IHP `_draw` (at a zero size) leaves 122 layers locked instead of 36,
  because it runs its device code under `tech lock *`; in the same session
  IHP's `via` then draws different geometry on 8/0, 10/0 and 19/0, and the
  inductors lose their top-metal layers. The sky130A guard-ring
  and well commands run `tech revert`, which unlocks `fence`, `magnet` and
  `rotate`; `deep_nwell_draw` leaves an entry on Magic's box stack; the IHP
  substrate-contact and well commands set `units microns`, under which the
  IHP and sky130A via commands paint nothing. The server records the layer
  locks, units and box stack at start-up and puts back whatever a request
  changed of them, so the next request sees what a fresh Magic has there.
  Path A of the harness does the same after every point. A backend test
  checks per PDK that requests after such a change draw what a second, fresh
  Magic draws. Other session state that a generator might change is not
  tracked.
- `gencell_create` called with an empty parameter dict takes the dialog
  branch and fails in batch; the backend always passes the merged defaults.

## Box-paint generators

Magic's "Devices" menus have commands that paint into the cursor box instead
of opening a dialog: vias and contacts, substrate contacts, substrate guard
rings, n-wells with a guard ring, and deep n-wells. Their `_draw` procs have
no `_defaults` proc and take no arguments (sky130A's `mcon_draw` and IHP's
`via1_draw` have optional ones, which the menu doesn't pass); each reads the
box size and paints into the current cell. The manifest calls every such proc
a box-paint generator, and each gets a PCell with two parameters:

| Parameter | Magic's call |
|---|---|
| `w` (µm) | the box's width: `box values 0um 0um ${w}um ${h}um`, then `<ns>::<proc>_draw` with no arguments |
| `h` (µm) | the box's height |

The PCell's origin is the box's lower-left corner, or, for a negative width
or height, its right or top edge (see [Magic behaviour the PCells
reproduce](#magic-behaviour-the-pcells-reproduce)). The cut rules are
`squares-grid` without a grid argument, so a box drawn at the origin and
placed at any offset on the 5 nm grid equals Magic painting the box at that
offset; research for version 0.3 checked 17 offsets on sky130A, and a test
of that version 11 offsets of 4 sizes on each gf180mcuD box-paint generator
(264 cases). The
defaults are the smallest square box the generator paints into, found by the
manifest tool by bisection on the 5 nm grid. Below the minimum Magic prints
a message (`Via1 width must be at least 0.26um`) and paints nothing; the
PCell then writes the same empty cell, as for the zero-size devices. The
guard-ring and well generators treat the box as the centre lines of their
contact strips, so their shapes extend outside it.

Each PCell's GDS is one cell, as Magic would write it for a cell holding only
that paint. Magic's menu paints into the user's own cell instead, where a
via1 painted next to existing via1 paint merges with it and gets one cut
array over the merged area; two via1 PCells side by side are two cells with
an array each, as two Magic subcells would be (read in the source; not run).

| PDK | Generator | In Magic's menu as | Minimum box (µm) | GDS layers at the minimum |
|---|---|---|---|---|
| sky130A | `mcon` | Devices 1 / mcon | 0.17 | 67/20, 67/44, 68/20 |
| | `via1` | Devices 1 / via1 | 0.26 | 68/20, 68/44, 69/20 |
| | `via2` | Devices 1 / via2 | 0.28 | 69/20, 69/44, 70/20 |
| | `via3` | Devices 1 / via3 | 0.32 | 70/20, 70/44, 71/20 |
| | `via4` | Devices 1 / via4 | 1.18 | 71/20, 71/44, 72/20 |
| | `subconn` | Devices 1 / substrate contact (1.8V) | 0.17 | 65/44, 66/44, 67/20, 94/20 |
| | `mvsubconn` | Devices 1 / substrate contact (5.0V) | 0.17 | 65/44, 66/44, 67/20, 75/20, 94/20 |
| | `subconn_guard` | Devices 1 / substrate guard ring (1.8V) | 0.6 | 65/44, 66/44, 67/20, 94/20 |
| | `mvsubconn_guard` | Devices 1 / substrate guard ring (5.0V) | 0.6 | 65/44, 66/44, 67/20, 75/20, 94/20 |
| | `nwell` | Devices 1 / n-well region with guard ring (1.8V) | 0.6 | 64/20, 65/44, 66/44, 67/20, 93/44 |
| | `mvnwell` | Devices 1 / n-well region with guard ring (5.0V) | 0.6 | 64/20, 65/44, 66/44, 67/20, 75/20, 93/44 |
| | `deep_nwell` | Devices 1 / deep n-well region (1.8V) | 3.0 | 64/18, 64/20, 65/44, 66/44, 67/20, 93/44 |
| | `mvdeep_nwell` | Devices 1 / deep n-well region (5.0V) | 3.0 | 64/18, 64/20, 65/44, 66/44, 67/20, 75/20, 93/44 |
| gf180mcuD | `via1` | Devices 2 / via1 | 0.28 | 34/0, 35/0, 36/0 |
| | `via2` | Devices 2 / via2 | 0.28 | 36/0, 38/0, 42/0 |
| | `via3` | Devices 2 / via3 | 0.28 | 40/0, 42/0, 46/0 |
| | `via4` | Devices 2 / via4 | 0.28 | 41/0, 46/0, 81/0 |
| | `subcon_3p3` | Devices 2 / substrate contact (3.3V) | 0.23 | 204/0 only (see above) |
| | `subcon_06v0` | none: the "substrate contact (6.0V)" entry calls `subcon_6p0_draw`, which doesn't exist | 0.23 | 204/0 only |
| ihp-sg13g2 | `via1` to `via4` | none (commented out of the PDK's menu) | 0.2 | metal n, via n, metal n+1 (8/0, 10/0, 19/0 for via1) |
| | `via5` | none | 0.62 | 67/0, 125/0, 126/0 |
| | `via6` | none | 1.9 | 126/0, 133/0, 134/0 |
| | `subconn`, `hvsubconn` | Devices / substrate contact (1.8V), (5.0V) | 0.16 | 1/0, 6/0, 8/0, 14/0 (+ 44/0 for hv) |
| | `subconn_guard`, `hvsubconn_guard` | Devices / substrate guard ring (1.8V), (5.0V) | 0.6 | 1/0, 6/0, 8/0, 14/0 (+ 44/0) |
| | `nwell`, `hvnwell` | Devices / n-well region with guard ring (1.8V), (5.0V) | 0.62 | 1/0, 6/0, 8/0, 31/0 (+ 44/0) |
| | `deep_nwell`, `hvdeep_nwell` | Devices / deep n-well region (1.8V), (5.0V) | 3.0 | 1/0, 6/0, 8/0, 31/0, 32/0 (+ 44/0) |
| ihp-sg13cmos5l | `via1` to `via3` | none | 0.2 | as on ihp-sg13g2 |
| | `via4` | none | 0.62 | 50/0, 125/0, 126/0; its messages say "Via5" (the proc is a copy of sg13g2's `via5_draw`) |
| | `subconn`, `hvsubconn`, `subconn_guard`, `hvsubconn_guard`, `nwell`, `hvnwell` | Devices / as on ihp-sg13g2 | as on ihp-sg13g2 | as on ihp-sg13g2 |

Magic's own messages have mistakes the PCells copy: sky130A's `via4_draw`
prints `Via3 width must be at least 1.18um` for its own minimum, and IHP's
`hvnwell_draw` prints a 0.26 µm height minimum while it tests 0.62 (read in
the source).

## Configuration

A value comes from the environment if set, then from
`$XDG_CONFIG_HOME/klayout-magic-pcells/config.ini` (else
`~/.config/klayout-magic-pcells/config.ini`, section `[kmp]`, keys in lower
case without the `KMP_` prefix, for example `magic = /opt/magic/bin/magic`),
then from the default. The settings of one PDK go in a section `[kmp:<pdk>]`
(for example `[kmp:ihp-sg13g2]` with `magicrc = /opt/ihp/ihp-sg13g2.magicrc`),
or in the environment as `KMP_MAGICRC_<PDK>` and `KMP_MANIFEST_<PDK>`, with
the PDK name in upper case and `-` written as `_` (`KMP_MAGICRC_IHP_SG13G2`).
`klayoutrc` isn't used because KLayout doesn't save it under `-b`.

| Variable | Default | Meaning |
|---|---|---|
| `KMP_PDKS` | `auto`: every supported PDK whose rcfile exists under `PDK_ROOT` (or whose `KMP_MAGICRC_<PDK>` is set) | the PDKs to register, separated by commas or spaces, or `all` |
| `KMP_PDK` | `sky130A` | the PDK that the unqualified `KMP_MAGICRC` and `KMP_MANIFEST` apply to, and the default PDK of `tools/build_manifest.py` and `run_sweep.py`; when `KMP_PDKS` is unset and `KMP_PDK` is set, only that PDK registers, as in version 0.2 |
| `KMP_MAGIC` | `magic` on `PATH`, then `/foss/tools/bin/magic` | Magic executable |
| `PDK_ROOT` | `/foss/pdks` | directory that holds the PDKs; the rcfiles read it too |
| `KMP_MAGICRC_<PDK>` | `$PDK_ROOT/<pdk>/libs.tech/magic/<pdk>.magicrc` | that PDK's Magic rcfile |
| `KMP_MANIFEST_<PDK>` | the shipped `manifest-<pdk>.json` | path to a rebuilt manifest |
| `KMP_CACHE_DIR` | `$XDG_CACHE_HOME/klayout-magic-pcells`, else `~/.cache/klayout-magic-pcells` | cache root, shared by all PDKs |
| `KMP_CACHE` | `1` | `0` keeps nothing on disk between sessions |
| `KMP_BACKEND` | `server` | `server`, or `oneshot` (one Magic process per request, for debugging) |
| `KMP_TIMEOUT` | `30` | seconds per request |
| `KMP_LAZY` | `0` with `server`, `1` with `oneshot` | when 1, the GUI form shows an Update button instead of regenerating on every edit; a device's form still asks Magic on every edit, because the values it shows come from Create |
| `KMP_LOG` | unset | file that receives every request and reply line |

A PDK named in `KMP_PDKS` that isn't installed, or that this version doesn't
support, gets one logged error that names the variable to set, and no
library; the other PDKs still register. With the default `auto`, a PDK that
isn't installed is skipped without a message. Every registered PDK costs a
Magic process for the whole KLayout session, so a user of one PDK can set
`KMP_PDKS` to it.

The plugin reads `KMP_PDK` and `KMP_PDKS` and ignores `PDK`, because the
iic-osic-tools image sets `PDK=ihp-sg13g2` by default. A GUI started from a
desktop launcher may not get the login shell's `PATH`; set `magic` in
`config.ini` then.

## The cache

KLayout regenerates every PCell variant when it opens a file. The cache saves
a Magic call per variant on each later open, and if Magic fails during a
session, variants that are already in the cache still come from disk. An
entry is Magic's GDS exactly as Magic wrote it plus a JSON sidecar with the
request, Magic's checked values, its messages, its cell name and the SHA-256
of the GDS, under `<cache>/v1/<versions digest>/<device>/<key>.gds` and
`.json`.

A GDS whose bytes no longer match the digest in its sidecar (truncated,
overwritten, or another entry's file copied over it), or a sidecar written
for another device, counts as a miss: the entry is deleted and Magic
generates it again. If a GDS from the in-memory memo or the disk can't be
read anyway, produce logs a warning, drops the entry and asks Magic once.
`KMP_CACHE=0` keeps the session's entries in a temporary directory that is
deleted when the process exits. If the cache directory can't be written, the
library registers without the disk cache and logs a warning that names
`KMP_CACHE_DIR`. Each Magic process runs in its own empty directory under
`<cache>/run` (or the system temp directory without a usable cache), which
is deleted when Magic stops; Magic looks for cells in its working directory
first, so a stray `.mag` file there can't stand in for a vendor cell. Magic
writes into `<cache>/tmp`, and each versions directory names its PDK in a
`versions.json`.

If `cache clear` or `cache prune` runs in another shell, or the cache
directory is deleted, while KLayout has the libraries open, the session
makes its directories again when it next writes, and generates again any
variant it remembered whose file is gone. A backend test does each of
these under a running session.

The key is a SHA-256 over the PDK, the device, the request text, the Magic
version, the PDK's commit (open_pdks' from `SOURCES` for sky130A and
gf180mcuD, the `COMMIT` file for the IHP PDKs), the tech file version, a
digest of the text of every proc loaded in the PDK's generator namespace and
in `::magic`, a digest of the tech file, a digest of every file in the
directory that holds it (`libs.tech/magic`: the IHP tech files include four
more tech files and the IHP fixed devices source layout scripts from there),
a digest of the vendor files that fixed devices copy (each vendor cell's
`.mag`, found on Magic's search path as `getcell` finds it, and the whole GDS
file it names, such as the 10.5 MB `sky130_fd_pr.gds`), and the cache format
(4 in this version: the sidecar also records what Magic's dialog shows when
it reopens on the instance, and a request may be an Apply). Editing a
generator file or a vendor GDS locally therefore starts new entries, and so
does a new Magic, PDK or cache format. For a device the request text is the
form of Magic's dialog that the instance's state stores (see [Values as
Magic's dialog shows them](#values-as-magics-dialog-shows-them)), with
`kmp_apply` set to `1` when Apply made the cell; for the defaults that is the
same text version 0.4 sent. What the dialog made of a form and a set of
edits is kept as well, as `<cache>/v1/<versions digest>/_dialog/<key>.json`,
under a key over the same versions fields, the device, the whole dialog
request (the form, the edits, and the widget order and dependencies the
manifest gives) and a digest of the server's Tcl files, which hold the
plugin's model of the dialog's bindings, so after a change to that model
the cache doesn't return entries that the old model wrote. To manage the
cache:

```sh
python3 -m klayout_magic_pcells cache prune    # delete the selected PDKs' old versions directories
python3 -m klayout_magic_pcells cache clear    # delete every entry of every PDK
python3 -m klayout_magic_pcells cache stats
```

`prune` works on the PDKs that `--pdk` or `KMP_PDKS` selects: it starts each
one's Magic to learn its current versions digest, deletes that PDK's other
versions directories and any directory with no entries, and keeps the
directories of every other PDK; it prints the name of each one it keeps.
A user who sets `KMP_PDKS` to one PDK therefore keeps the other PDKs'
entries; `KMP_PDKS=all` prunes every
installed PDK. Both commands leave Magic's files in `<cache>/tmp` unless they
are more than a day old.

## Stamps and audit

Every variant carries two stamps of the form
`kmp1;magic=8.3.681;tech=1.0.588-56-g026824c;pdk=sky130A;digest=<12 hex>`.
The digest is a SHA-256 over the PDK name, the Magic version, the PDK's
commit, the tech version, the proc text, the tech file, the files of
`libs.tech/magic` and the vendor files, the same inputs as the cache key, so
a locally edited generator file or vendor GDS gives a different stamp even
when the version strings are the same.

- *generated by*: a GDS property (attribute 100) on one shape, the boundary
  box where the device has one on 235/4 (sky130A), otherwise the shape on the
  lowest layer with the smallest corner (on gf180mcuD that is the 0/0
  boundary), with the first 16 hex digits of the cache key and the grid of
  this variant's Magic output added (`;key=<16 hex>;grid=5`: the coarsest
  grid, in nm, that all its coordinates lie on). It survives GDS and OASIS
  with or without the library.
- *created with*: the hidden PCell parameter `kmp_created`, stored in the
  file with the other parameters. When a file is reopened under a different
  Magic or PDK, or with edited generator code, produce logs a warning,
  because the regenerated geometry may differ from what the file was made
  with.

Version 0.3's digest covers more inputs than 0.2's, so a file made with
version 0.2 logs that warning once when it is reopened. Versions 0.4 and 0.5
have the same digest as 0.3, so they reopen 0.3's files without the warning
(for what 0.5 draws for an older file, see [Values as Magic's dialog shows
them](#values-as-magics-dialog-shows-them)). Version 0.5's cache format is
4, so its versions directory (`3341d4166cfc` for sky130A in the image) is
not 0.3's and 0.4's (`24feca9ae925`), and it doesn't read their cache;
`cache prune` deletes the old directories. Stamps written by version 0.1.0
have no digest; they are compared on Magic, tech and PDK alone.

`audit` reads a file without registering any library and reports the cells
of all four libraries: cells with an error marker, without a stamp, with no
shapes, or stamped by a different Magic, PDK or generator code than the
installed one, and a file database unit that doesn't divide 5 nm. A cell
belongs to a PDK by its library name, since several PDKs have a device
called `rm1`. It also reports a cell whose Magic output lies on a finer
grid than the file's database unit, from the grid in the cell's stamp: a
sky130A `mcon` with a 1.175 µm box lies on 5 nm, so a file at dbu 0.002 µm
rounds it, while the default `mcon` lies on 10 nm. A stamp written by
version 0.3 or earlier has no grid; audit then uses the grid of the device's
default output, which the manifest records, and says so in its message, and
a cell that a non-default size puts on a finer grid can go unreported.
`--regen` also registers the libraries the file uses, with every variant
generated by Magic as if the memo and the disk cache were empty, and compares
each cell's stored geometry with what the installed Magic generates now; a
difference, or a cell that regenerates as the error marker, is a problem. A disk-cache entry
that differs from what Magic generates now is reported too, and replaced.
`audit` exits 1 when any cell or the file has a problem.

```sh
python3 -m klayout_magic_pcells audit design.gds --regen
```

## If Magic is missing or fails

`register()` starts Magic before it registers a library. If Magic, a PDK's
rcfile or its manifest is missing, if Magic doesn't start, or if the running
Magic doesn't define every generator in the manifest (an rcfile that loads
no PDK or another PDK, or a generator file that fails to load), it logs one
error for that PDK, naming the variable to set, and registers no library for
it. The error carries Magic's exit status and its last messages on stderr,
such as
`Could not find file '/nonexistent/sky130A/libs.tech/magic/sky130A.tech'`
for a wrong `PDK_ROOT`. For an rcfile that loads no PDK, empty or broken, it
says the rcfile loaded no PDK and quotes Magic, for example
`Error parsing "/tmp/x.magicrc": missing close-brace`. Registering the devices that are present and leaving
out the missing ones is not supported. Cells in files opened while a library
isn't registered show as `<defunct>sky130_magic.…` (or the other library
names) and keep the geometry stored in the file; saving keeps that geometry.
Call `klayout_magic_pcells.register()` from the macro console once the
setting is fixed, and the open cells come back as live PCells.

If a generation fails while the library is registered (Magic failed twice in
a row, timed out, stopped in the endless `mos_check` loop, or wrote a GDS that
KLayout can't read), or a value is refused, produce doesn't raise. It draws a
1 × 1 µm box and a `KMP_ERROR <device>: <reason>` text on layer 255/0, which
none of the four PDKs' layer files lists. The reason includes what Magic
printed, for example
`Can't find GDS file "$PDKPATH/libs.ref/sky130_fd_pr/gds/sky130_fd_pr.gds"`
when the vendor GDS of a fixed device is missing. When a generator's error
is followed by `gencell_create`'s own (an IHP fixed device whose layout
script is missing), Magic's message comes first:
`KMP_ERROR diodevdd_2kv: diodevdd_2kv: couldn't read file ".../diodevdd_2kv.tcl": no such file or directory (then gencell_create: can't read "instname": no such variable)`.
KLayout saves that marker, `audit` reports it, and `generate` exits 1.

## Devices

Each library has a PCell for every `_draw` proc of its PDK that also has a
`_defaults` proc (a device Magic's `gencell` code can build) and for every
`_draw` proc that can be called with no arguments (a box-paint generator,
listed above). sky130A names below drop the `sky130_fd_pr__` prefix (and
`sky130_fd_bs_flash__` for the SONOS FET).

**sky130A** (`sky130_magic`):

| Family | Count | Devices |
|---|---|---|
| MOSFET | 12 | `special_sonosfet_star`, `nfet_01v8`, `nfet_01v8_lvt`, `nfet_03v3_nvt`, `nfet_05v0_nvt`, `nfet_g5v0d10v5`, `nfet_g5v0d16v0`, `pfet_01v8`, `pfet_01v8_hvt`, `pfet_01v8_lvt`, `pfet_g5v0d10v5`, `pfet_g5v0d16v0` |
| Varactor | 3 | `cap_var`, `cap_var_hvt`, `cap_var_lvt` |
| Resistor | 22 | `res_generic_l1`, `res_generic_m1` to `m5`, `res_generic_nd`, `res_generic_nd__hv`, `res_generic_pd`, `res_generic_pd__hv`, `res_generic_po`, `res_high_po_0p35`, `_0p69`, `_1p41`, `_2p85`, `_5p73`, `res_iso_pw`, `res_xhigh_po_0p35`, `_0p69`, `_1p41`, `_2p85`, `_5p73` |
| MIM capacitor | 2 | `cap_mim_m3_1`, `cap_mim_m3_2` |
| Diode | 8 | `diode_pd2nw_05v5`, `_05v5_hvt`, `_05v5_lvt`, `_11v0`, `diode_pw2nd_05v5`, `_05v5_lvt`, `_05v5_nvt`, `_11v0` |
| Photodiode | 1 | `photodiode` |
| Fixed layout | 12 | `cap_vpp_04p4x04p6_m1m2_shieldl1`, `cap_vpp_08p6x07p8_m1m2_shieldl1`, `cap_vpp_11p5x11p7_m1m2_noshield`, `cap_vpp_11p5x11p7_m1m2m3m4_shieldl1m5`, `npn_05v5_W1p00L1p00`, `npn_05v5_W1p00L2p00`, `npn_11v0_W1p00L1p00`, `pnp_05v5_W0p68L0p68`, `pnp_05v5_W3p40L3p40`, `rf_test_coil1`, `rf_test_coil2`, `rf_test_coil3` |
| Box paint | 13 | `mcon`, `via1` to `via4`, `subconn`, `mvsubconn`, `subconn_guard`, `mvsubconn_guard`, `nwell`, `mvnwell`, `deep_nwell`, `mvdeep_nwell` |

**gf180mcuD** (`gf180mcu_magic`):

| Family | Count | Devices |
|---|---|---|
| MOSFET | 13 | `nfet_03v3`, `nfet_03v3_dss`, `nfet_05v0`, `nfet_06v0`, `nfet_06v0_dss`, `nfet_06v0_nvt`, `nfet_10v0_asym`, `pfet_03v3`, `pfet_03v3_dss`, `pfet_05v0`, `pfet_06v0`, `pfet_06v0_dss`, `pfet_10v0_asym` |
| MOS capacitor | 4 | `nmoscap_3p3`, `nmoscap_6p0`, `pmoscap_3p3`, `pmoscap_6p0` |
| Varactor | 4 | `nvaractor_3p3`, `nvaractor_6p0`, `pvaractor_3p3`, `pvaractor_6p0` |
| Resistor | 16 | `nplus_u`, `nplus_u_6p0`, `pplus_u`, `pplus_u_6p0`, `npolyf_s`, `npolyf_u`, `ppolyf_s`, `ppolyf_u`, `ppolyf_u_1k`, `ppolyf_u_1k_6p0`, `nwell` (the n-well resistor), `rm1` to `rm5` |
| MIM capacitor | 1 | `cap_mim_2p0fF` |
| Diode | 4 | `diode_nd2ps_03v3`, `diode_nd2ps_06v0`, `diode_pd2nw_03v3`, `diode_pd2nw_06v0` |
| Fixed layout | 11 | `eFuse`, `npn_00p54x02p00`, `npn_00p54x04p00`, `npn_00p54x08p00`, `npn_00p54x10p00`, `npn_05p00x05p00`, `npn_10p00x10p00`, `pnp_05p00x00p42`, `pnp_05p00x05p00`, `pnp_10p00x00p42`, `pnp_10p00x10p00` |
| Box paint | 6 | `via1` to `via4`, `subcon_3p3`, `subcon_06v0` |

**ihp-sg13g2** (`sg13g2_magic`):

| Family | Count | Devices |
|---|---|---|
| MOSFET | 8 | `sg13_lv_nmos`, `sg13_lv_pmos`, `sg13_hv_nmos`, `sg13_hv_pmos`, `sg13_lv_rfnmos`, `sg13_lv_rfpmos`, `sg13_hv_rfnmos`, `sg13_hv_rfpmos` |
| Varactor | 1 | `SVaricap` |
| Resistor | 10 | `rsil`, `rppd`, `rhigh`, `rm1` to `rm7` |
| MIM capacitor | 2 | `cap_cmim`, `cap_rfcmim` |
| Diode | 2 | `dantenna`, `dpantenna` |
| Bipolar transistor | 4 | `npn13g2`, `npn13g2l`, `npn13g2v`, `pnpMPA` |
| Inductor | 2 | `inductor2`, `inductor3` |
| Bond pad | 1 | `bondpad` |
| Via stack | 1 | `via` |
| Fixed layout | 8 | `diodevdd_2kv`, `diodevdd_4kv`, `diodevss_2kv`, `diodevss_4kv`, `nmoscl_2`, `nmoscl_4`, `schottky`, `scr1` |
| Box paint | 14 | `via1` to `via6`, `subconn`, `hvsubconn`, `subconn_guard`, `hvsubconn_guard`, `nwell`, `hvnwell`, `deep_nwell`, `hvdeep_nwell` |

**ihp-sg13cmos5l** (`sg13cmos5l_magic`):

| Family | Count | Devices |
|---|---|---|
| MOSFET | 8 | as on ihp-sg13g2 |
| Varactor | 1 | `SVaricap` |
| Resistor | 8 | `rsil`, `rppd`, `rhigh`, `rm1` to `rm5` |
| Capacitor | 1 | `cap_cmomf` (finger MOM capacitor; no MIM) |
| Diode | 2 | `dantenna`, `dpantenna` |
| Bipolar transistor | 1 | `pnpMPA` |
| Inductor | 2 | `inductor2`, `inductor3` |
| Bond pad | 1 | `bondpad` |
| Via stack | 1 | `via` |
| Fixed layout | 6 | `diodevdd_2kv`, `diodevdd_4kv`, `diodevss_2kv`, `diodevss_4kv`, `nmoscl_2`, `nmoscl_4` |
| Box paint | 10 | `via1` to `via4`, `subconn`, `hvsubconn`, `subconn_guard`, `hvsubconn_guard`, `nwell`, `hvnwell` |

The fixed-layout devices and the sky130A photodiode take only `nx`, `ny`,
`deltax` and `deltay`.

### Exclusions

The other `_draw` procs need arguments: they are internal helpers that the
device `_draw` procs call, and Magic's menus don't offer them. They get no
PCell, and the manifest lists each with that reason:

| PDK | Helpers |
|---|---|
| sky130A | `cap`, `diode`, `fixed`, `guard_ring`, `mos`, `photodiode`, `res` |
| gf180mcuD | `cap`, `diode`, `fixed`, `mos`, `res` |
| ihp-sg13g2 | `cap`, `diode`, `fixed`, `guard_ring`, `mos`, `res`, `var` |
| ihp-sg13cmos5l | `diode`, `fixed`, `guard_ring`, `mos`, `res`, `var` |

`sky130A.tcl` defines `res_xhigh_po_0p35_draw` twice with the same body, which
is why it has 81 `_draw` definitions for 80 procs. The IHP files `sealring_*.tcl`
and `read_sram_gds.tcl`, and the isolbox and seal ring that `ihp-sg13g2.tcl`'s
header lists, have no `_draw` proc.

### Menu entries that call undefined generators

The manifest records menu entries whose command names a generator the PDK
doesn't define. In the image's PDKs there are two, both on gf180mcuD: "nwell
(3.3V) -1680 Ohm/sq" calls `gf180mcu::nwell_3p3` (the device is `nwell`), and
"substrate contact (6.0V)" calls `gf180mcu::subcon_6p0_draw` (the generator is
`subcon_06v0_draw`). Research for version 0.3 also found, by reading
`gf180mcuD.tcl`, that the "npolyf_s" entry calls `ppolyf_s`, that one npn
label appears twice so that the second makes `npn_00p54x04p00`, and that
`nfet_10v0_asym`, `pfet_10v0_asym`, `npolyf_s` and `nwell` can't be reached
from a working menu entry. The PCells offer all of them.

### The manifests

The PCell declarations come from
`python/klayout_magic_pcells/data/manifest-<pdk>.json`, built by querying
Magic in the pinned image. For each device the tool records its defaults,
its dialog widgets (by running `_dialog` against stub widget procs), what
`_check` does on the defaults and at 0, 10000 and 2.5 for each number, and
Magic's output for the defaults; for each box-paint generator, its minimum
box, its message one step below it and its output at the minimum.

```sh
scripts/manifest.sh                       # rebuild all four (python3 tools/build_manifest.py --all, in the image)
scripts/manifest.sh --check               # exit 1 if a committed manifest differs from the installed Magic
scripts/manifest.sh --pdk gf180mcuD       # one PDK
```

## Tests

Everything runs inside the pinned image, through `scripts/in_image.sh`, which
mounts the repository at `/repo` and uses a login shell (the image puts Magic
and KLayout on `PATH` only there).

```sh
scripts/test.sh                                       # unit tests, then the backend tests once per PDK
scripts/parity.sh                                     # every PDK in turn, full sweep
scripts/parity.sh --pdk gf180mcuD                     # one PDK
scripts/parity.sh --pdk all --quick                   # each generator's defaults, every PDK
scripts/parity.sh --pdk sky130A --devices 'sky130_fd_pr__res_*' --keep
scripts/parity.sh --pdk ihp-sg13g2 --update-baseline  # rewrite that PDK's baselines
```

Each PDK runs in its own container, with the image's `PDK` variable set to
it, and writes `out/parity/<pdk>/report.json` and `report.md`; without
`--pdk` (or with `--pdk all`) the four run one after another and
`out/parity/summary.json` and `summary.md` collect them. The script exits 0
when every check of every PDK passes, 1 when any check fails, and 2 when the
harness itself fails. For each PDK it runs, in one container:

1. the unit tests (`tests/unit`, 96 tests) and the backend tests for that
   PDK (`tests/backend`, 42 tests, each run with the PDK's own devices).
   The unit tests cover:
   - configuration, including the PDK selection and per-PDK settings;
   - the wire format;
   - the cache key and the cache files, including damaged and swapped
     entries, prune per PDK and a cache deleted under a session;
   - value formatting (including 6,000 doubles saved by KLayout and read
     back in a second process), and the checks of coverage strings, choices
     and number lists;
   - the GDS import, the coordinate grid of Magic's output and audit's use
     of it, and stamps and their digest;
   - the PCell declarations of all four manifests, and the manifests'
     counts, box-paint entries, exclusions and coordinate grids;
   - Magic's error text, the raw GDS font reader and `compare.py`'s command
     line;
   - the path A watchdog, driven by a fake Magic that crashes on one point
     and hangs on another and by one that dies with an X error at start-up;
   - the stored dialog state, against a fake Magic: when it is used and when
     the values are typed into the dialog again, the defaults shown as
     Create shows them, edits in the dialog's row order, a later edit typed
     into what the dialog shows and drawn by Apply, an Apply that keeps the
     instance, a fixed device's Apply drawn as Create, a value that Magic
     reads no number from kept in its field, another device's state with
     the same widget names not used, the widgets that the defaults lack sent
     with the form and no other widget that isn't a parameter, refused and
     damaged states never sent, every device's dialog order in the
     manifests, and the dialog cache key over the whole request and the
     server's code.

   The backend tests cover:
   - every generator generated twice in one Magic session with no restart;
   - the session state put back after requests that change it, compared
     with a fresh Magic;
   - the box that a box-paint check reports, and negative, zero, `inf` and
     `nan` boxes on every box-paint generator;
   - a brace in a value, a killed Magic restarted and the request retried,
     a timeout, an unknown device, `_check` messages, and the endless
     `mos_check` loop stopped (on gf180mcuD, whose loop ends, the device
     drawn);
   - a value holding a Tcl command, refused by the server and, after saving
     and reopening a file with an empty cache, never run;
   - damaged cache entries regenerated, the cache cleared, pruned and
     deleted under a running session, and a prune that leaves another PDK's
     entries;
   - start-up failures that name their cause, an empty and a broken rcfile
     refused with Magic's words, and an rcfile that loads another technology
     than the PDK's (a copy of its tech file under another name);
   - a missing vendor GDS or IHP layout script named in the error marker,
     and an unwritable cache directory;
   - `audit` after a local edit of the PDK's `via1_draw`, with a stale cache
     entry, and on files at dbu 0.002, 0.0025 and 0.001;
   - a generator edited to raise, reopened;
   - the values Magic's dialog shows, saved to GDS and OASIS and kept
     through three reopens in fresh processes, a library refresh and a
     second save, with the disk cache off and no dialog run on reopen (on
     sky130A, `res_high_po_0p69`, `cap_mim_m3_1`, `res_high_po_0p35` and
     `res_xhigh_po_5p73`, on which typing a stored value again would change
     the form);
   - a Tcl command put into a saved dialog form or into the saved dialog it
     shows, never run;
   - the form callback's icons, the CLI's exit codes and temporary
     directories, a manifest whose names collide, no Magic left running
     after the client exits normally or is killed, and registration from
     plain Python.

   Only these backend tests are PDK-specific: a device without `_check` or
   with one that raises (ihp-sg13g2, gf180mcuD), `audit` after an edit of
   sky130A's vendor GDS, Magic behaviour that the dialog model leaves out
   on sky130A (the snake resistor's `w` flipping on every `_check`, and
   `res_generic_po` at `l 0` drawing nothing with one `_check` and drawing
   with the dialog's), and, in the sky130A pass, all four libraries
   registered under `klayout -b -rm` and from the Salt autorun under
   `klayout -zz`;
2. `tools/build_manifest.py --pdk <pdk> --check`;
3. the sweep (`tests/parity/gen_sweep.py`): for each device the defaults,
   the minimum and maximum of each number, a value below each minimum that
   Magic enforces, each checkbox flipped, counts of 1 and 4, each other
   choice of a selectlist, `2` and `1 2` for a number list, `+50` and `-50`
   for each coverage string, ` -50` and a tab before `+30` on the first and
   last coverage string, W and L off the 0.01 µm grid, `w = 0` and `l = 0`
   on resistors and diodes, a MOSFET more than 30 µm wide, and 5 seeded
   random combinations; for each box-paint generator its minimum on each
   side, 5 nm below it on each side, squares, wide and tall boxes, an
   off-grid width, 20 × 20 µm, negative widths and heights, a negative zero
   and 5 random sizes. The numbers of those points have at most 6 decimals,
   so every generator also gets every float at 12 and at 15 significant
   digits, at a 12-digit rounding tie (13 digits ending in 5), and one ULP
   from such a tie. At most 64 points per device. Each device also gets
   edit points: the default device created and then edited to the values
   of up to 12 of its other points (random, zero, minimum, maximum and
   below-minimum points first), and each of its random points 1 to 4
   created and then edited to the next one's values.
   The text for Magic and the typed values for the PCell come from
   `tests/parity/magic_text.py`, which restates this README's formatting
   contract and imports nothing from the plugin; coverage strings are used
   exactly as typed;
4. path A, Magic alone: `tests/parity/magic_ref.tcl` calls `magic::gencell`
   for every device point but the edit points, and for a box-paint point
   sets the box and calls
   the generator with no arguments, all in one Magic process run in an empty
   directory, using none of this package's code. It takes the generator
   namespace from the PDK's own `PDKNAMESPACE`, puts back the layer locks,
   units and box stack after every point as the server does, and has its own
   copy of the endless-loop guard; `run_sweep.py` watches it: a point on
   which Magic crashes or makes no progress for 300 s is recorded as a Magic
   error, and Magic starts again on the next point;
5. path D, Magic's own dialog: `tests/parity/dialog_ref.tcl` under
   `xvfb-run magic -d XR`, using none of this package's code, does for every
   device point what a user of the "Devices" menu does: it opens the "New
   device" dialog with `magic::gencell <ns>::<device>`, types the point's
   values into their widgets in the dialog's row order (an entry gets the
   text and its `<Return>` binding runs, a checkbox is clicked, a choice is
   picked), reads the form back, presses Create, reads the dialog that
   Create reopens on the new instance ("Edit device"), and writes the cell
   Create made. On an edit point it then types the point's values into
   that dialog, each where the field shows another value (a number compared
   as the number `magic::spice2float` reads), presses Apply, reads the
   dialog reopened on the instance Apply left, and writes that instance's
   cell; where the dialog didn't reopen on the instance (gf180mcuD's three
   stub devices) it deletes the instance and presses Create again. It
   records each widget's binding on the device's first point. It
   restores the session state as path A does, except that it leaves fence,
   magnet and rotate unlocked as each Create leaves them and doesn't use
   `tech revert` (under the GUI each lock change takes longer than the one
   before); it starts a new Magic every 50 points, and has the same
   watchdog as path A, which also starts Magic again on the same point when
   it dies with an X error before its first point (up to 8 times in a row;
   see [CI](#ci));
6. path B, the PCell: `tests/parity/pcell_path.py` under `klayout -b -rm`
   with only that PDK's library registered, first with an empty cache and
   then again from the cache. For a device it passes the point's typed
   values through the PCell's coerce as the GUI form does
   (`dialog_values`), so the variant stores what the GUI stores, and it
   makes a second variant from the typed values as they are, which must
   draw the same shapes. An edit point's first values go through
   `dialog_values`, and then its stored values with the point's values
   changed in them;
7. per point, against path D for a device and against path A for a
   box-paint generator:
   - the request path B actually sent (read back through the stamp's key),
     which for a device must be the form Magic's Create or Apply got
     (marked `kmp_apply` for an Apply, and Create's form where Apply kept
     the instance);
   - for a device, the stored values against what Magic's dialog shows when
     it reopens on the instance (a value in SPICE notation against the
     number that path D's Magic reads from it, and where it reads none, the
     typed value), the stored `kmp_dialog` against that form's and that
     dialog's exact text, and the New device dialog as it opened against the
     manifest's defaults;
   - on an edit point, also the state after its first step against Create's
     form and the Edit device dialog that the edit started from;
   - XOR of every layer, the number of unmerged shapes on every layer, and
     every label with all its attributes, the font read from the raw GDS
     records of both files;
   - a census of the raw GDS records of the reference's file against
     `baseline/<pdk>/census.json`, for elements that KLayout has no shape
     for (the NODE elements above);
   - the bounding box (and, for each generator's defaults, the box in the
     manifest);
   - Magic's cell name, and Magic's checked values (for a box-paint point,
     the box Magic used);
   - the cached run against the first run, no error marker, and the stamp.

   Path A is the second reference for a device point that isn't an edit
   point: where its checked values equal those of the dialog's Create,
   `_draw` got the same values, and its geometry and cell name must be the
   same too; elsewhere the report counts the points where the two draw the
   same shapes. Each widget's binding in path D must run the same chain of
   passes as the server's `dialog` op;
8. for box-paint generators in the PDK's menu, the menu entry itself:
   `tests/parity/menu_ref.tcl` under `xvfb-run magic -d XR` invokes the entry
   on the box of each generator's default, wide and 20 × 20 µm points, and
   the result must equal path A's;
9. round trips on the default, minimum, maximum, below-minimum and zero
   points, the many-digit and tie points, the negative boxes and the
   random-to-random edit points, plus a 20 % sample of the other edit
   points and a 10 % sample of the rest:
   - reopen the GDS and OASIS files with the library and check for a live
     PCell, the stored values that path B saved and the request their state
     gives, the request that the reopened variant was drawn from (read back
     from the generator through its stamp's key), that Magic's dialog didn't
     run again, and geometry regenerated by Magic with the disk cache off
     and compared with the reference (the step fails if a variant comes from
     disk);
   - reopen them without the library: a `<defunct>` cell that keeps the
     stored geometry, and its stamp;
   - save again without the library and reopen with it;
   - refresh the library (`Library.refresh()`, which keeps what coerce
     returns) and check every reopened cell's parameters and geometry again;
   - place each default in host layouts with database units of 0.5 nm and
     5 nm;
10. DRC with both tools on both sides (the reference and the PCell), with
   each device's points on one sheet and each device's defaults also run
   alone, compared as sets of rule IDs, and the defaults compared with
   `baseline/<pdk>/drc-defaults.json`. KLayout
   runs the PDK's own deck: `sky130A_mr.drc` (feol, beol and offgrid on,
   floating_met and seal off), `gf180mcu.drc` (`decks=all,-density`,
   variant D) and the IHP PDKs' `run_drc.py` (`--no_density`, one process,
   one thread; with one thread per CPU, KLayout 0.30.11 crashed once with
   signal 11 on an `npn13g2v` sheet, which passed when run again; a DRC run
   that fails is tried once more). A point whose cell is longer than
   10 mm on a side gets no DRC and is listed in the report: Magic's dialog
   makes ihp-sg13g2's `rm6` and `rm7`, which have no `_check`, 0.9 m and
   1.8 m long at the sweep's largest `val`, and Magic's DRC crashed
   (signal 11) on a sheet that held the `rm7` one, on both sides. The density
   decks are left out: sky130A's divides by zero on a cell without a
   prBoundary, and the others weren't tried on lone devices. Magic runs
   `drc(full)` with the PDK's rcfile, on the cell and
   a 10 µm margin around it (without the margin Magic clips an error area
   that lies outside a lone device's bounding box: sky130A `via4` at its
   minimum loses `met5.1`);
11. Magic extraction of every MOSFET point but the edit points on both
    sides (edit points get no DRC either): the same devices on
    both sides, and the model, W, L and count (`nf × m`, or `ng × m`) matching
    Magic's checked values, except for the patterns recorded in
    `baseline/<pdk>/extract-known.json` (see [Known
    differences](#known-differences)).

Every generator of every PDK is in the sweep; the excluded helpers are listed
in each report with the reason.

### Last full run

2026-11-23, Magic 8.3.681, KLayout 0.30.11, in the image listed under
[Requirements](#requirements): `scripts/parity.sh`, all four PDKs one
after another, on version 0.5.0's code as it stood then, with this README
and `docs/design.md` the only files not yet final. Since that run, only
the documentation, the scripts that take guide.md's screenshots and one
message of the round-trip check have changed. The summary printed `PARITY
PASS over 4 PDKs` and the script exited 0: 10,399 points in 79 minutes of
harness time on 6 CPUs. Each PDK's run included its unit and backend tests
and its manifest check, and checked DRC and the GDS census against the
committed baselines, which this version doesn't change. The sweeps are
version 0.4's plus the edit points (2,873 over the four PDKs).

Two earlier full runs during this version's development found problems
that 0.5.0 fixes. The first, before review 3, found the IHP RF FETs'
`topc` and `botc` widgets, gf180mcuD's stub devices whose dialog doesn't
reopen, and Magic's DRC crashing on a 1.8 m long `rm7`. The second, after
review 3, failed 10 sky130A and 9 gf180mcuD points (`res_generic_l1`, `m1`
to `m4`, and `rm1` to `rm5` with `l 0`), where the dialog shows `170.0n`
or `99.999n`: the harness read the `n` suffix and Magic doesn't (see
[Values as Magic's dialog shows
them](#values-as-magics-dialog-shows-them)). That run was stopped after
gf180mcuD, and the check now uses the number Magic reads.

Path D, the real dialog under Xvfb, ran for 12.4, 7.2, 6.6 and 4.6 minutes
on the four PDKs, alongside paths A and B, and didn't have to start Magic
again after an X error. Path D agreed with the PCells on every device
point. Path A (`magic::gencell` with the typed values) applies to 4,991 of
the 6,537 device points that aren't edit points, the ones where it gets the
same checked values as the dialog's Create, and on all of them the PCells
matched it. On the other 1,546, the dialog's corrections, its order of
edits or its extra widgets give `_draw` other values; 1,492 of them still
draw the same shapes as `magic::gencell`, and the 54 that don't are listed
below per PDK. A file
that version 0.4 saved with the values of one of those 54 points comes
back with other shapes; with the values of one of the 1,492, it comes back
with the same shapes and other checked values. Every edit point passed,
the ones where Magic's Apply kept the instance among them. The round trips
covered 1,764 sky130A, 1,305 gf180mcuD, 1,123 ihp-sg13g2 and 904
ihp-sg13cmos5l points, all regenerated by Magic (no variant came from
disk), none with Magic's dialog run again on reopen, and every one
unchanged by the library refresh; the request each reopened variant was
drawn from, read back through its stamp, was the one path B sent, except
on 15 points of gf180mcuD's three stub devices (45 file reads: the GDS,
the OASIS and the file saved again without the library), which Magic draws
empty. There the cell has no stamp
and the generator got no request while the file was read, so none was
read back (why was not looked into).
Every point's fonts were the same in both files.

The notes under each table are points that pass but are listed in the
report. "Typed with no Return" counts the points with one typed value on
devices whose dialog has no widget beyond their parameters, where path A is
also Magic's dialog with the value typed and Create pressed without
Return.

**sky130A** (`sky130_magic`): `PARITY PASS 3718/3718` in 24 min; 96 unit and 41 backend tests passing (1 skipped as not for this PDK); manifest check passing; KLayout DRC: sky130A_mr.drc with beol=true, feol=true, floating_met=false, offgrid=true, seal=false, thr=1. 2,771 points as in version 0.4 and 947 edit points.

| Family | Points | Pass | Fail |
|---|---|---|---|
| MOSFET | 925 | 925 | 0 |
| Varactor | 233 | 233 | 0 |
| Resistor | 1261 | 1261 | 0 |
| MIM capacitor | 93 | 93 | 0 |
| Diode | 504 | 504 | 0 |
| Photodiode | 31 | 31 | 0 |
| Fixed layout | 372 | 372 | 0 |
| Box paint | 299 | 299 | 0 |

- 97 points where Magic writes an empty cell, which the PCell reproduces (box paint at a box 5 nm below the minimum: 26, box paint with a zero width typed as -0.0: 13, diode at a zero size: 10, resistor at a zero size: 16, edit points to a zero size: 32)
- 4 default points whose 5 nm host placement is n/a: Magic's GDS has coordinates off the 0.005 um grid on 83/44
- 10 MOSFET points that match a known extraction pattern (`sky130_fd_pr__nfet_g5v0d16v0` 5, `sky130_fd_pr__pfet_g5v0d16v0` 5)
- 39 box-paint points through Magic's menu entry under Xvfb: identical 39
- the widget bindings of all 60 devices' dialogs, recorded 128 times over path D's restarts, run the same passes as the server's `dialog` op
- 947 edit points, all passing; Magic's Apply kept the instance on 74
- `magic::gencell` with the typed values, on the 2472 device points that aren't edit points: it applies on 2035, all identical; of the other 437, 422 draw the same shapes and 15 differ
  - they differ on: `sky130_fd_pr__cap_mim_m3_1` random 2, `sky130_fd_pr__cap_mim_m3_2` random 2, `sky130_fd_pr__res_generic_m5` zero 1, `sky130_fd_pr__res_generic_po` zero 1, `sky130_fd_pr__res_high_po_5p73` random 1, `sky130_fd_pr__res_xhigh_po_0p35` zero 1, `sky130_fd_pr__res_xhigh_po_0p69` zero 1, `sky130_fd_pr__res_xhigh_po_1p41` zero 1, `sky130_fd_pr__res_xhigh_po_2p85` zero 1, `sky130_fd_pr__res_xhigh_po_5p73` random 3, `sky130_fd_pr__res_xhigh_po_5p73` zero 1
- typed with no Return: 1857 points; other checked values than with Return on 286, other shapes on 7
- 115 points where Create's own `_check` changes the dialog's form (40 of them not edit points)

**gf180mcuD** (`gf180mcu_magic`): `PARITY PASS 2590/2590` in 14 min; 96 unit and 37 backend tests passing (5 skipped as not for this PDK); manifest check passing; KLayout DRC: gf180mcu.drc with decks=all,-density, run_mode=deep, threads=1, variant=D. 1,753 points as in version 0.4 and 837 edit points.

| Family | Points | Pass | Fail |
|---|---|---|---|
| MOSFET | 689 | 689 | 0 |
| MOS capacitor | 220 | 220 | 0 |
| Varactor | 220 | 220 | 0 |
| Resistor | 745 | 745 | 0 |
| MIM capacitor | 41 | 41 | 0 |
| Diode | 196 | 196 | 0 |
| Fixed layout | 341 | 341 | 0 |
| Box paint | 138 | 138 | 0 |

- 146 points where Magic writes an empty cell, which the PCell reproduces (box paint at a box 5 nm below the minimum: 12, box paint with a zero width typed as -0.0: 6, diode at a zero size: 8, every point of `eFuse`: 16, every point of `npn_00p54x08p00`: 16, every point of `npn_00p54x10p00`: 16, resistor at a zero size: 9, edit points: 63, 18 of them to a zero size and 45 on those three devices)
- 74 MOSFET points that match a known extraction pattern (`nfet_10v0_asym` 37, `pfet_10v0_asym` 37)
- 15 box-paint points through Magic's menu entry under Xvfb: identical 15
- the widget bindings of all 53 devices' dialogs, recorded 102 times over path D's restarts, run the same passes as the server's `dialog` op
- 837 edit points, all passing; Magic's Apply kept the instance on 80; on the 45 of the three stub devices the dialog doesn't reopen on the instance, so the edit deleted it and pressed Create again
- `magic::gencell` with the typed values, on the 1615 device points that aren't edit points: it applies on 1326, all identical; of the other 289, 281 draw the same shapes and 8 differ
  - they differ on: `cap_mim_2p0fF` random 3, `npolyf_s` zero 1, `nwell` zero 1, `ppolyf_s` zero 1, `ppolyf_u_1k` zero 1, `ppolyf_u_1k_6p0` zero 1
- typed with no Return: 1064 points; other checked values than with Return on 210, other shapes on 5
- 89 points where Create's own `_check` changes the dialog's form (23 of them not edit points)

**ihp-sg13g2** (`sg13g2_magic`): `PARITY PASS 2249/2249` in 24 min; 96 unit and 37 backend tests passing (5 skipped as not for this PDK); manifest check passing; KLayout DRC: run_drc.py --no_density --mp=1 --density_thr=1. 1,643 points as in version 0.4 and 606 edit points.

| Family | Points | Pass | Fail |
|---|---|---|---|
| MOSFET | 620 | 620 | 0 |
| Varactor | 37 | 37 | 0 |
| Resistor | 503 | 503 | 0 |
| MIM capacitor | 102 | 102 | 0 |
| Diode | 124 | 124 | 0 |
| Bipolar transistor | 166 | 166 | 0 |
| Inductor | 55 | 55 | 0 |
| Bond pad | 37 | 37 | 0 |
| Via stack | 35 | 35 | 0 |
| Fixed layout | 248 | 248 | 0 |
| Box paint | 322 | 322 | 0 |

- 78 points where Magic writes an empty cell, which the PCell reproduces (box paint at a box 5 nm below the minimum: 28, box paint with a zero width typed as -0.0: 14, diode at a zero size: 4, resistor at a value below its minimum: 4, resistor at a zero size: 12, edit points to a zero size: 16)
- 1 default point whose 5 nm host placement is n/a: Magic's GDS has coordinates off the 0.005 um grid on 10/25
- 236 MOSFET points that match a known extraction pattern (`sg13_hv_rfnmos` 59, `sg13_hv_rfpmos` 59, `sg13_lv_rfnmos` 59, `sg13_lv_rfpmos` 59)
- 24 box-paint points through Magic's menu entry under Xvfb: identical 24
- the widget bindings of all 39 devices' dialogs, recorded 76 times over path D's restarts, run the same passes as the server's `dialog` op
- 606 edit points, all passing; Magic's Apply kept the instance on 38
- `magic::gencell` with the typed values, on the 1321 device points that aren't edit points: it applies on 899, all identical; of the other 422, 402 draw the same shapes and 20 differ
  - they differ on: `cap_cmim` random 2, `cap_rfcmim` random 3, `rhigh` zero 1, `rm6` max 1, `rm6` min 1, `rm7` max 1, `rm7` min 1, `rppd` zero 1, `rsil` zero 1, `sg13_hv_rfnmos` below 1, `sg13_hv_rfnmos` min 1, `sg13_hv_rfpmos` below 1, `sg13_hv_rfpmos` min 1, `sg13_lv_rfnmos` below 1, `sg13_lv_rfnmos` min 1, `sg13_lv_rfpmos` below 1, `sg13_lv_rfpmos` min 1
- typed with no Return: 743 points; other checked values than with Return on 126, other shapes on 7
- 2 points with no DRC because their cell is longer than 10 mm on a side (`rm6` and `rm7` at the maximum `val`)
- 45 points where Create's own `_check` changes the dialog's form (17 of them not edit points)

**ihp-sg13cmos5l** (`sg13cmos5l_magic`): `PARITY PASS 1842/1842` in 17 min; 96 unit and 36 backend tests passing (6 skipped as not for this PDK); manifest check passing; KLayout DRC: run_drc.py --no_density --mp=1 --density_thr=1. 1,359 points as in version 0.4 and 483 edit points.

| Family | Points | Pass | Fail |
|---|---|---|---|
| MOSFET | 620 | 620 | 0 |
| Varactor | 37 | 37 | 0 |
| Resistor | 417 | 417 | 0 |
| Capacitor | 42 | 42 | 0 |
| Diode | 124 | 124 | 0 |
| Bipolar transistor | 59 | 59 | 0 |
| Inductor | 55 | 55 | 0 |
| Bond pad | 36 | 36 | 0 |
| Via stack | 36 | 36 | 0 |
| Fixed layout | 186 | 186 | 0 |
| Box paint | 230 | 230 | 0 |

- 58 points where Magic writes an empty cell, which the PCell reproduces (box paint at a box 5 nm below the minimum: 20, box paint with a zero width typed as -0.0: 10, diode at a zero size: 4, resistor at a zero size: 10, edit points to a zero size: 14)
- 236 MOSFET points that match a known extraction pattern (`sg13_hv_rfnmos` 59, `sg13_hv_rfpmos` 59, `sg13_lv_rfnmos` 59, `sg13_lv_rfpmos` 59)
- 18 box-paint points through Magic's menu entry under Xvfb: identical 18
- the widget bindings of all 31 devices' dialogs, recorded 63 times over path D's restarts, run the same passes as the server's `dialog` op
- 483 edit points, all passing; Magic's Apply kept the instance on 31
- `magic::gencell` with the typed values, on the 1129 device points that aren't edit points: it applies on 731, all identical; of the other 398, 387 draw the same shapes and 11 differ
  - they differ on: `rhigh` zero 1, `rppd` zero 1, `rsil` zero 1, `sg13_hv_rfnmos` below 1, `sg13_hv_rfnmos` min 1, `sg13_hv_rfpmos` below 1, `sg13_hv_rfpmos` min 1, `sg13_lv_rfnmos` below 1, `sg13_lv_rfnmos` min 1, `sg13_lv_rfpmos` below 1, `sg13_lv_rfpmos` min 1
- typed with no Return: 629 points; other checked values than with Return on 116, other shapes on 3
- 39 points where Create's own `_check` changes the dialog's form (15 of them not edit points)


### Mutations the harness catches

Each line is a copy of the package with one change, run with
`run_sweep.py --pdk <pdk> --no-unit --no-drc --no-extract --devices ...` on
2026-11-22, on version 0.4. The control is the same run on the unchanged
package. Version 0.5's mutations of the dialog code follow the table.

| Change to the package | PDK and devices | Result |
|---|---|---|
| none (control) | sky130A: `nfet_01v8`, `res_generic_po`, `cap_mim_m3_1`, `via1` | PASS 164/164 |
| `format_float` writes `%.1g` | same | FAIL 53/164: request 53, checked 42, magic_cell 30, bbox 27, geometry 27, texts 19, roundtrip 10, stamp 2 |
| `format_float` writes `%.8g` | same | FAIL 16/164: request 16, checked 12 |
| `format_float` rounds the double instead of the 15-digit text (version 0.3) | same | FAIL 6/164: roundtrip 6, request 5, checked 3 |
| `format_float` drops the `.0` (`31` instead of `31.0`) | same | FAIL 24/164: request 24, checked 9 (no geometry changes) |
| the importer turns every label 90°, sets its size to 0 and right-justifies it | same | FAIL 138/164: texts 138, roundtrip 51 |
| the importer inserts every shape twice | same | FAIL 160/164: geometry 160, texts 138, roundtrip 51 (the merged XOR is unchanged; the shape and text counts differ) |
| the server refuses negative box sizes (version 0.3) | same | FAIL 3/164: each of request, geometry, texts, bbox, checked, magic_cell, cache, placeholder, stamp and roundtrip on the 3 negative `via1` boxes |
| none (control) | ihp-sg13g2: `sg13_lv_nmos`, `rsil`, `via1`, `subconn_guard` | PASS 162/162 |
| `format_float` writes `%.1g` | same | FAIL 62/162: request 62, checked 54, geometry 43, bbox 39, magic_cell 25, roundtrip 15, texts 6, stamp 4 |
| `format_float` writes `%.8g` | same | FAIL 16/162: request 16, checked 8 |
| none (control) | gf180mcuD: `nfet_03v3`, `ppolyf_u`, `via1` | PASS 94/94 |
| `format_float` writes `%.1g` | same | FAIL 39/94: request 39, checked 31, magic_cell 23, bbox 19, geometry 19, roundtrip 4, stamp 2 |
| `format_float` writes `%.8g` | same | FAIL 12/94: request 12, checked 8 |

Version 0.5's dialog code, the same way on 2026-11-23, with path D, on
sky130A's `nfet_01v8`, `res_high_po_0p69`, `res_xhigh_po_5p73`,
`cap_mim_m3_1`, `diode_pd2nw_05v5` and `via1`:

| Change to the package | Result |
|---|---|
| none (control) | PASS 260/260 |
| coerce ignores the stored form (types the stored values into the defaults again) | FAIL 166/260: roundtrip 126, request 70, checked 65, magic_cell 35, typed 2, geometry 2, texts 2, bbox 2, stamp 2 |
| the server's chain leaves out the dependency callbacks (`res_recalc`, ...) | FAIL 48/260: request 42, dialog 42, checked 42, magic_cell 7, bindings 7, geometry 4, texts 4, bbox 4, roundtrip 1, stamp 1 |
| the server's chain runs one pass with no callback instead of two | FAIL 11/260: bindings 9, dialog 2, request 2 |
| edits typed in the manifest's parameter order instead of the dialog's rows | FAIL 10/260: request 10, dialog 10, checked 10, magic_cell 10, geometry 3, texts 3, bbox 3 |
| produce sends the visible values' text instead of the stored form | FAIL 138/260: request 138, roundtrip 62, checked 45, geometry 2, texts 2, bbox 2, magic_cell 2, stamp 2 |

Those runs were on the code before review 3. After it, the model of later
edits (Edit device and Apply) and of what the dialog shows after Create was
checked the same way on 2026-11-23, on sky130A's `nfet_01v8`,
`res_high_po_0p69`, `res_high_po_5p73`, `res_xhigh_po_5p73`,
`res_generic_po`, `cap_mim_m3_1`, `diode_pd2nw_05v5`,
`npn_05v5_W1p00L1p00`, `photodiode` and `via1`: 531 points, 142 of them
edit points.

| Change to the package | Result |
|---|---|
| none (control) | PASS 531/531 |
| a later edit starts from the form from before Create and is drawn by Create (the model before review 3) | FAIL 130/531, all edit points: request 130, dialog 130, checked 21, magic_cell 11, geometry 7, texts 7, bbox 7, roundtrip 3 |
| the server draws an Apply as a Create (without its first `_check`) | FAIL 7/531, all edit points: geometry 7, texts 7, bbox 7, checked 7, magic_cell 7, dialog 7, roundtrip 3 |
| Apply always makes a new cell (no comparison of cell names) | FAIL 9/531, all edit points: request 9, dialog 9, checked 3 |
| what the dialog shows after Create taken from Create's checked dict instead of the reopened dialog | FAIL 22/531 (11 edit points): dialog 22, request 6, checked 6 |
| the stored values are the form from before Create (the model before review 3) | FAIL 107/531 (86 edit points): dialog 107, request 11, checked 11, magic_cell 4 |

In version 0.2 the sweep took its text from the plugin's own formatter, and
the `%.1g` mutation passed 99 of 99 points. In version 0.3 no sweep value had
more than 7 significant digits, and a `%.8g` mutation passed 144 of 144
points on the sky130A set above.

### CI

`.github/workflows/parity.yml` runs one job per PDK in the image, pulled by
digest: `scripts/parity.sh --pdk <pdk> --quick` on pull requests and the full
sweep on a weekly schedule and on manual runs. Each job uploads
`out/parity/<pdk>/`. GitHub lists 14 GB of disk for standard runners and
the image is 11.7 GB unpacked, so each job frees disk space first and
prints `df` before and after the pull.

GitHub has run the workflow once, on its weekly schedule on 2026-11-23
(run 45232459515), on version 0.3 (tag `v0.3.0`), which `main` held until
version 0.5.0. The disk-space step and the image pull succeeded on all
four jobs, and sky130A and ihp-sg13g2 passed. gf180mcuD failed with
`PARITY FAIL 15/1493 (menu 15)` and ihp-sg13cmos5l with `PARITY FAIL
18/1159 (menu 18)`: in both, Magic under Xvfb exited before the menu
check's first job with `X Error of failed request: BadAlloc (insufficient
resources for operation)`, `Major opcode 53 (X_CreatePixmap)`, serial
1266. Traced in the image (with `strace` on Magic's X connection), the
pixmap request at serial 1265 or 1266 is Magic's first drawing pixmap, 939
pixels wide, whose height changes from one start to the next: in seven
starts on gf180mcuD it was 718 three times, 734, 1407, 2494 and 4161 (the
window is 768 high). Every local start succeeded, and why GitHub's Xvfb
refused it on two PDKs and not on the other two is not known. Path D,
which version 0.5 added, starts Magic under Xvfb the same way once every
50 device points, so it would most likely have failed there too. Since
version 0.5.0 the harness starts Magic again when it dies with an X error
before its first point or job, up to 8 times in a row, records how often
in the report, and then stops with a harness error; Xvfb's own messages go
to `out/parity/<pdk>/xvfb_*.log`. Whether that is enough on GitHub's
runners is unknown until the workflow runs again, which needs a push.

## Known differences

Where the PCells don't reproduce Magic, or where Magic's tools disagree with
the drawn values:

- The NODE elements of five sky130A vendor cells (see [Why Magic is the
  backend](#why-magic-is-the-backend)).
- A label's font. KLayout 0.30.11's GDS reader keeps no font (every text
  reads back with font -1) and its writer writes font 0, so a font other
  than 0 in Magic's GDS could not reach the PCell. Magic wrote font 0 on
  every text of every swept point; the harness compares the fonts of both
  files from the raw records, so a change would show.
- A label's size in the GDS file, in its last bits: KLayout writes the
  8-byte real of a text's magnification from its own value, so on
  ihp-sg13g2 `schottky` Magic's `0x4059999999999998` (0.35) becomes
  `0x405999999999999c` in a file the PCell is saved in. KLayout reads both
  as the same size.
- A coverage string, choice or number list that would reach Tcl as code draws
  the error marker, where Magic would reset it or draw nothing (see
  [Parameters](#parameters)).
- The PCell types each changed value into Magic's dialog once, in the
  dialog's row order, with Return, then presses Create for an instance's
  first edit and Apply for every later one. A Magic user may type with no
  Return, type in another order, leave a field (which runs its binding
  again), press Return on an unchanged value, or type several fields
  before one Create, and each of these can give other values; on sky130A's
  snake resistors shorter than 5.73 µm they can give another width (see
  [Values as Magic's dialog shows
  them](#values-as-magics-dialog-shows-them)).
- Fixed devices are flat: Magic writes an array instance of the vendor cell,
  and the PCell holds every copy's shapes. A 60 × 60 sky130A
  `npn_05v5_W1p00L1p00` array is a 22 KB GDS from Magic and 1,170,000 shapes
  in the PCell (1.8 s to place, 156 MB peak memory in plain Python, measured
  in version 0.2). The flat geometry is the same, but Magic's DRC checks a
  hierarchical array differently: on `cap_vpp_11p5x11p7_m1m2_noshield` with
  `nx 2` and `deltax 0.0034`, where neighbouring copies overlap, Magic's
  `drc(full)` on Magic's own output reports "This layer can't abut or
  partially overlap between subcells", and on the PCell, or on Magic's
  output flattened, it reports nothing.
- Extraction patterns of Magic's own output, which both paths share and the
  harness records in `baseline/<pdk>/extract-known.json`: on sky130A, the
  `g5v0d16v0` FETs with `nf` of 2 or more extract every second finger as the
  `g5v0d10v5` model with a different length; on gf180mcuD, `nfet_10v0_asym`
  and `pfet_10v0_asym` extract as `nfet_05v0` and `pfet_05v0` with l = 0.44u;
  on the IHP PDKs, the four RF FETs extract as the FET model of the same
  voltage (`sg13_lv_rfnmos` as `sg13_lv_nmos`). gf180mcuD's MOS capacitors
  and varactors are not in the extraction check (they extract as
  `cap_nmos_03v3` and the like, and `pvaractor_6p0` extracts nothing, in
  research for version 0.3).

## Known limitations

- KLayout regenerates every variant from the installed Magic when it opens a
  file and doesn't ask first. The `kmp_created` warning, `audit --regen` and
  the versioned cache make a change visible; this version can't pin a Magic
  version.
- If Magic fails while a file is opening with the library registered, the
  failed variants get the error marker, and saving the file saves the marker
  in place of the device until the file is reopened with a working Magic.
- Every GUI, `-z` or `-zz` start pays about 0.6 s and one Magic process per
  registered PDK, even in sessions that never place one of these devices.
  `KMP_PDKS` limits the PDKs.
- Opening a large design runs Magic once per variant that isn't cached, about
  20 ms each.
- KLayout LVS of circuits built from these devices hasn't been tried. sky130A
  and gf180mcuD devices have no pin shapes, because Magic writes labels only.
- A design saved as OASIS without the library keeps the labels' strings and
  positions but not their size or justification, and keeps one of two
  identical labels at one position (the vendor texts of gf180mcuD's npn
  devices): KLayout 0.30.11's OASIS files don't hold them. The harness's OASIS
  round trips compare labels that way.
- The child Magic is told to die with the KLayout thread that started it
  (`PR_SET_PDEATHSIG`); KLayout calls produce on its main thread. Linux only.
- A host layout whose database unit doesn't divide 5 nm rounds Magic's
  coordinates, and one of 5 nm or 2.5 nm rounds 1 nm coordinates: those of
  the vendor cells listed above, and those of a device whose sizes are typed
  to 1 nm (IHP's `bondpad` and inductors, in a test of version 0.3).
  `audit` reports each such cell, from the grid in its stamp.
- Another package that registers a library under one of these four names
  would replace it. The PDKs' own libraries have other names (`skywater130`;
  `gf180mcu`, `gf180mcu_klayoutapi`, `gf180mcu_sealring`; `SG13_dev`,
  `SG13_native_pcell_lib`, `sg13g2_stdcell_hv`, `sg13cmos5l_stdcell_hv`); the
  IHP libraries use device names such as `rsil` and `inductor2` too, so a
  layout that holds both gets cell names that KLayout makes unique. Loading
  them together with these libraries has not been tried, and neither has the
  IHP PDKs' autorun, which imports every module on `sys.path` whose name
  starts with `sg13` (this package's doesn't).
- Widgets of Magic's dialog whose name the device's defaults lack (the IHP
  RF FETs' `topc` and `botc` checkboxes) aren't PCell parameters: the PCell
  sends them as the dialog opens them, empty, and can't set them. Review 3
  set them in 16 combinations with `w` and `ng` per RF FET on ihp-sg13g2
  and saw only Magic's cell name change, because `mos_device` turns both on
  for devices that keep `gate_ring 1`, as the RF FETs do (not rerun for
  this version). A unit test fails if another widget that isn't a
  parameter appears in a manifest.
- Not tried: installing through the Salt manager (guide.md shows it
  listing the linked package), KLayout's `.mag` reader, `ext2spice merge`,
  the PDKs' own LVS decks, and KLayout DRC with the density decks.

## Changes from the design

- Four PDKs instead of sky130A alone, with one library, Magic process,
  manifest and baseline set per PDK, selected by `KMP_PDKS`. The design kept
  other PDKs out of scope.
- Box-paint generators are PCells (`w` and `h`). The design listed them as
  excluded.
- The server puts back the session state (layer locks, units, box stack)
  after each request, and keeps cells a generator places in its device
  rather than restarting Magic for them.
- The eight "[+/-](%)" coverage parameters are strings, not doubles (see
  [Parameters](#parameters)), and selectlists are choice parameters. The
  design typed the coverage values as floats and left selectlists out.
- Floats are sent as the 15-digit text KLayout saves, rounded to 12
  significant digits, rather than `repr()`, and a value equal to Magic's
  default is sent as Magic's default text. Without this, a reopened file
  changed its requests.
- Magic's checked values come from an execution trace on
  `magic::gencell_setparams`, which `gencell_create` calls with them; fixed
  devices have no `parameters` property to read them from. The trace changes
  no `::magic` proc, so the proc digest in the cache key covers only Magic's
  code.
- DRC sheets hold one device each. On a first sheet that mixed devices, Magic
  logged that it rescaled its units by 5 when it read the vendor cells with
  off-grid coordinates, and it reported no errors for `npn_11v0_W1p00L1p00`,
  which gets nine rule IDs when checked alone. Magic's DRC checks a 10 µm
  margin around the cell.
- An empty GDS from Magic is reproduced instead of being replaced by the
  error marker.
- Values the generator code would evaluate are refused before they reach
  Magic.
- The design said a cache entry is never checked again. The sidecar records
  the SHA-256 of the stored GDS, and an entry whose GDS doesn't match is
  deleted and regenerated. The cache key and the stamps cover more than the
  three version strings: the generator code, the PDK's files and the vendor
  GDS.
- `register()` also refuses a PDK whose running Magic lacks a generator of
  the manifest or loads another generator namespace, and an unwritable cache
  directory turns the disk cache off instead of stopping registration.
- The harness has more checks per point than the design listed (the request
  path B sent, Magic's cell name and checked values from both paths, the
  shape counts, every label attribute, the fonts from the raw GDS records,
  the GDS census, the menu check, round trips regenerated by Magic with the
  cache off), a known-extraction list per PDK, the manifest check, and a
  watchdog on path A. Path A's request text is independent of the plugin. The entry
  point is `scripts/parity.sh`, as in the design.
- `docs/design.md` section 4.2 gave the wrong reason for leaving out Magic's
  dialog callbacks, and has a correction note that says so.
- Since version 0.5 the PCells store the values Magic's parameter dialog
  shows after Create, with its dependency callbacks run, draw what its
  Create makes, and treat a later edit as one in the Edit device dialog
  followed by Apply; the design stored the typed values and followed
  `magic::gencell`. The design's section 4.5, added for this version,
  describes it. The harness's reference for devices is Magic's real dialog
  under Xvfb (path D), and `magic::gencell` (path A), which the design made
  the reference, is the second one.
- The project is licensed under Apache-2.0, which the design left open.

## Licence and credits

klayout-magic-pcells is licensed under the Apache License, Version 2.0: see
[LICENSE](LICENSE). [NOTICE](NOTICE) names the sources below; under
Apache-2.0, copies of the package that you distribute have to include it.

The package ships no code from Magic or from the PDKs. The four manifests in
`python/klayout_magic_pcells/data/` hold data that `tools/build_manifest.py`
reads out of each PDK's Magic generator code by running it in Magic: device
and parameter names, default values, the labels, order and callbacks of
Magic's parameter dialogs, what each `_check` proc does to some probe
values, and a summary of what Magic draws for the defaults. What each PDK's
installed files say about their licence, in the image listed under
[Requirements](#requirements):

| PDK | The manifest's data comes from | Licence the PDK states |
|---|---|---|
| sky130A | `sky130A.tcl`, installed by open_pdks 026824c7, by Tim Edwards | none in `sky130A.tcl`; the install has no licence file; its Magic tech file `sky130A.tech` says it "may be distributed under the terms of the Apache 2.0 license agreement" |
| gf180mcuD | `gf180mcuD.tcl`, installed by open_pdks 026824c7, by Tim Edwards | none: neither the Tcl file, nor the tech file (which says "Copyright (c) 2022 Efabless, Inc."), nor a licence file in the install |
| ihp-sg13g2 | `ihp-sg13g2.tcl` and the `ihp-sg13g2-*.tcl` files it sources | Apache-2.0: every Tcl file but `read_sram_gds.tcl` carries the header "Copyright 2025 IHP PDK Authors, Licensed under the Apache License, Version 2.0"; the install has no top-level licence file |
| ihp-sg13cmos5l | `ihp-sg13cmos5l.tcl` and its `ihp-sg13cmos5l-*.tcl` files | Apache-2.0: the same header with "Copyright 2026 IHP PDK Authors" (again not on `read_sram_gds.tcl`), and the Apache-2.0 text as `LICENSE` at the top of the install |

open_pdks' own licence and those of the sky130 and gf180mcu source
repositories are not in the image and weren't checked. Whether data read
out of a file that states no licence may ship under Apache-2.0 is a
question for the project lead.

The harness runs the PDKs' KLayout DRC decks from the PDK install and
doesn't copy them (`sky130A_mr.drc` says GPLv3 in its header, the IHP deck
Apache-2.0; gf180mcu's wasn't checked).

The devices themselves are Magic's: the generators in the PDKs' Tcl files
and Magic's `toolkit.tcl`, from open_pdks, the IHP PDKs and Magic.

Two earlier projects were read for their structure and licences, and no code
was copied from either:

- [efabless/sky130_klayout_pdk](https://github.com/efabless/sky130_klayout_pdk),
  Apache-2.0, with Python PCells by Mabrains LLC and Efabless; the same PCell
  code ships in the PDK as the `skywater130` library.
- [laurentc2/SKY130_for_KLayout](https://github.com/laurentc2/SKY130_for_KLayout),
  BSD-2-Clause, a technology, DRC and LVS setup with no PCells.
