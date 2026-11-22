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
Magic. The box-paint generators are the via, contact, substrate-contact,
guard-ring and well commands of Magic's "Devices" menus; their PCells take
the box size (see [Box-paint generators](#box-paint-generators)).

Status: version 0.3.0. The repository is kept on GitHub as the private
repository vproHacks/klayout-magic-pcells. The parity harness (see
[Tests](#tests)) passes on every PDK; the results of the last full run are
under [Last full run](#last-full-run). The libraries load under
`klayout -b -rm`, from the Salt autorun under `klayout -zz`, and, in a check
of version 0.2 under Xvfb, in the full KLayout GUI. The warning icons in the
GUI's parameter form have not been seen on screen.

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
Magic writes as the device. One exception: KLayout's GDS reader drops GDS
NODE elements, and the vendor GDS of five sky130A fixed devices holds them
(18 to 156 each, on 67/20, 68/20, 69/20 and 70/20). They carry no mask
geometry, and the PCells don't have them. The harness counts them (see
[Tests](#tests)).

## Parity definition

Parity here means: for a given set of parameter values, the PCell cell,
flattened, has the same polygons on every GDS layer/datatype, the same number
of shapes on each layer, and the same label texts (string, position,
rotation, mirror, size, justification and font) as the GDS that Magic writes
when its generator is called once with those values: through
`magic::gencell` for a device, and through the generator's menu call on a
box for a box-paint generator. The comparison is an XOR per layer at a
common database unit, with no tolerance and no alignment. Cell names,
hierarchy, GDS properties and timestamps are not compared.

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
`source /foss/tools/osic-multitool/iic-magic-bindkeys`, a file of the image;
with the IHP PDKs installed elsewhere that line fails after the devices have
loaded (read in the rcfile, not tried).

## Installing

The repository is a KLayout Salt package (it has a `grain.xml`). Link it into
KLayout's `salt` folder:

```sh
ln -s /path/to/klayout-magic-pcells ~/.klayout/salt/klayout-magic-pcells
```

In the iic-osic-tools image the folder is `/headless/.klayout/salt/`. KLayout
then runs `pymacros/klayout_magic_pcells.lym` at start-up, which registers a
library for every installed PDK. Installing through the Salt manager or
`klayout -y` has not been tried.

Check the setup:

```sh
PYTHONPATH=/path/to/klayout-magic-pcells/python python3 -m klayout_magic_pcells doctor
```

`doctor` prints every setting and where it came from, then, for each
selected PDK, starts Magic, compares the running Magic's device defaults and
box-paint generators with the shipped manifest (the generator list built from
Magic, see [Devices](#devices)), and times one generation (about 20 ms on
sky130A in the image).

## Usage

**In the GUI**, the libraries are `sky130_magic`, `gf180mcu_magic`,
`sg13g2_magic` and `sg13cmos5l_magic`, and the PCells carry Magic's device
names, such as `sky130_fd_pr__nfet_01v8`, `nfet_03v3` or `sg13_lv_nmos`, and
the box-paint generators' names, such as `via1` or `subconn_guard`. The
libraries aren't bound to a technology, so each is listed under every
technology.

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

The package also has a command line:

```sh
python3 -m klayout_magic_pcells devices -v            # PCells and their parameters, per PDK
python3 -m klayout_magic_pcells check sky130_fd_pr__nfet_01v8 w=0.1 l=0.1
python3 -m klayout_magic_pcells generate sky130_fd_pr__cap_mim_m3_1 w=5 l=10 -o cap.gds
python3 -m klayout_magic_pcells check --pdk gf180mcuD rm1 w=0
```

A device is looked up in the selected PDKs' manifests; a name that more than
one PDK has (`rm1` to `rm5`, `via1`, `nwell`, ...) needs `--pdk`.

`check` runs the device's `_check` proc once (Magic's own validation, which
clamps bad values and prints a message) and shows what it changes:

```
sky130_fd_pr__nfet_01v8: Magic draws w=0.42 (entered 0.1)
sky130_fd_pr__nfet_01v8: Magic draws l=0.15 (entered 0.1)
  message: Mos length must be >= 0.15 um
  message: Mos width must be >= 0.42 um
```

For a device with no `_check` proc (ihp-sg13g2's `rm6` and `rm7`) or whose
`_check` raises an error, it says so: Magic's `gencell_create` catches the
error and draws with the unchecked values, and so does the PCell. The
manifest probes found `_check` procs that raise "integer value too large to
represent" at `w = 0` on 17 sky130A resistors, on gf180mcuD's `npolyf_s`,
`ppolyf_s` and `rm1` to `rm5`, and on the IHP PDKs' `rsil`, `rppd`, `rhigh`
and `rm1` to `rm5`; IHP's `inductor3` raises at `turns 2.5`. For a box-paint generator, `check` reports the box Magic
uses after rounding to its 5 nm grid, and the generator's message when the
box is below its minimum.

Each time KLayout asks a PCell to draw a variant (the cell KLayout makes for
one set of parameter values), the PCell's `produce` call builds the request
for Magic, looks in an in-memory memo and then in the disk cache, and only
then asks Magic. One Magic process (`magic -dnull -noconsole`) runs per PDK
in each KLayout process, started when the library registers. `register()`
starts the processes of all PDKs before it waits for any; with all four PDKs
it took 0.63 s in the image, and one generation takes 15 to 20 ms. Each
Magic process is about 72 MB (measured on sky130A in version 0.2).

## Parameters

Every parameter that Magic's own dialog lets you edit is a PCell parameter.
Their types come from the manifest, a JSON file per PDK built from Magic (see
[Devices](#devices)):

| In Magic's dialog | PCell type | Sent to Magic as |
|---|---|---|
| number entry | double | 12 significant digits, written like a Python float (`0.35`, `31.0`); a value equal to Magic's default is sent as Magic's default text (`0.420`) |
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

Floats are rounded to 12 digits because KLayout 0.30.11 doesn't store doubles
exactly in a saved file: `0.35` reads back as `0.35000000000000003` in a new
process, which would otherwise change the request, and with it the cache key,
every time a file is reopened. They always carry a decimal point because the
generator code does arithmetic with Tcl's `expr` and `/`, which divide two
integer strings as integers. A value with 13 or more significant digits is
therefore not the text Magic gets: `0.4244999999999` is sent as `0.4245`.
Magic's cell name and checked values can then differ from Magic given the
longer text, because Magic rounds to three decimals for the name. No geometry
difference has been found: sky130A `nfet_01v8` with `w` at 0.4225, 0.4275,
1.0045 and 5.005, each against the same value 1e-14 lower, drew the same
polygons in Magic.

Apart from refusing values that the generator code would evaluate, the PCells
add no limits, no snapping and no choices of their own. Magic's `_check` is
the only check of the values, and it runs once per generation, on the values
you entered. KLayout stores the values you entered, not the values Magic
corrected them to, so a file can hold `l = 0.1` for a device that Magic drew
with `l = 0.15`. In the GUI parameter form, a parameter that `_check` changed
should get a warning icon and a tooltip such as
`Magic draws 0.15 (entered 0.1): Mos length must be >= 0.15 um`; that comes
from KLayout's source and hasn't been seen on screen. Outside the GUI,
Magic's messages go to KLayout's log as warnings.

Magic's own dialog behaves differently: it runs `_check` on every field edit,
writes the corrected values back into the form, and checks again when you
press Create.
Running `_check` twice changes the result for some inputs (on sky130A, 60
of the sweep's `below:` points, all of them diode `area`/`peri` or resistor
`val` recalculations; each PDK's report lists its own), so a dialog user and
a `magic::gencell` caller can end up with different values and cell names. A
review of version 0.2 regenerated the 60 such sky130A points of its sweep
with the checked values as input and found the same geometry on all of them.
This library follows `magic::gencell`.

### A typed resistance (`val`)

Magic's resistor dialogs bind `res_recalc` to the `val`, `l`, `w` and `nx`
entries; `res_recalc` computes a length from a typed resistance. The PCell
doesn't call it, and a `val` you type changes no geometry: `_check` computes
`val` again from `w` and `l`. That is also what Magic's dialog does for a
`val` typed on its own, because its `<Return>` binding runs `_check` before
`res_recalc`, and `_check` with a nonzero `l` replaces the typed `val` ("L
and W specified - ignore Val if specified", sky130A.tcl line 5178). A run
of the real dialog under Xvfb on sky130A (research for this version, not a
harness check) gave:

| Typed in Magic's dialog | Form afterwards | Cell Magic creates |
|---|---|---|
| `res_high_po_0p35`: val=10000 | w 0.35, l 0.5, val 1.57k | the default length (the same cell as `magic::gencell ... val 10000`, which is what the PCell sends) |
| `res_high_po_0p35`: l=0, then val=10000 | after l=0: l 1.218u; after val: l 9.726, val 10.0k | l 9.726 |
| `res_generic_po`: val=10000 | w 0.33, l 1.65, val 241.0 | the default length |
| `res_generic_po`: l=0, then val=10000 | l clamped to 1.650 at the first step, then val 241.0 | the default length |
| `res_high_po_0p35`: w=1.0 | "Resistor width must be <= 0.350 um", w 0.35 | the default device |
| `res_high_po_0p35`: l=5 | l 5.0, val 5.681k | l 5.0 |

In these runs the dialog turned a typed `val` into a length only after `l`
was typed as 0, which `_check` turns into the SPICE string `1.218u` and reads
back as 0 µm on the next pass, and only on resistors whose `_check` doesn't
clamp the length first. A PCell `l` is a double and can't hold `1.218u`, and the same
two values through `magic::gencell` (`l 0 val 10000`) give an empty cell on
sky130A, because `_draw` fails on the SPICE string. Calling `res_recalc` from
the form would therefore do more than Magic's dialog does: on
`res_generic_po` (and, in a replay of the dialog's calls without Tk, on
`res_xhigh_po_0p35`) neither sequence of edits tried made the dialog turn
`val` into a length.
The same `res_recalc` and the same binding exist on the IHP PDKs (read in the
source); the dialog was driven only on sky130A.

### Magic behaviour the PCells reproduce

Parity means these come out of the PCells exactly as Magic has them:

- MOSFET `w` is the width of one finger. `w 1.5 nf 3` is 4.5 µm of total
  width. The PCell form calls it "Finger width".
- Off-grid values are not snapped. The sky130A drawing rounds W and L to
  0.01 µm, so a requested `w 0.425` is drawn 0.43 µm wide, and two inputs
  that draw the same geometry are two different variants. Box-paint sizes
  are rounded to Magic's 5 nm internal grid (0.263 becomes 0.265).
- `_check` recalculates `val`, `area` and `peri`. After a clamp, they are
  computed from the unclamped size: sky130A `diode_pd2nw_05v5` with
  `w 0.225` is drawn 0.45 × 0.45 µm and reports `area=101.25m peri=1.35`,
  where a second `_check` would report `202.5m` and `1.8`.
- Zero sizes give an empty cell on some devices, where `_check` replaces the
  size with a SPICE string (`1.0u`, `170.0n`) and `_draw` then fails on it,
  or `_check` itself fails. Magic writes a cell with no shapes; the PCell
  writes the same empty cell and logs a warning rather than drawing the
  error marker; `generate` exits 1 and `audit` reports `empty cell`. Whether
  an empty device should get the error marker instead is an open question
  for the project lead. The sweeps list every empty output per PDK.
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

The PCell's origin is the box's lower-left corner. The cut rules are
`squares-grid` without a grid argument, so a box drawn at the origin and
placed at any offset on the 5 nm grid equals Magic painting the box at that
offset; research for this version checked 17 offsets on sky130A. The
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
| `KMP_LAZY` | `0` with `server`, `1` with `oneshot` | when 1, the GUI form shows an Update button instead of regenerating on every edit |
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
first, so a stray `.mag` file there can't stand in for a vendor cell.

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
(3 in this version). Editing a generator file or a vendor GDS locally
therefore starts new entries, and so does a new Magic, PDK or cache format.
To manage them:

```sh
python3 -m klayout_magic_pcells cache prune    # delete every versions directory but each PDK's current one
python3 -m klayout_magic_pcells cache clear    # delete the cache
python3 -m klayout_magic_pcells cache stats
```

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
  boundary), with the first 16 hex digits of the cache key added. It
  survives GDS and OASIS with or without the library.
- *created with*: the hidden PCell parameter `kmp_created`, stored in the
  file with the other parameters. When a file is reopened under a different
  Magic or PDK, or with edited generator code, produce logs a warning,
  because the regenerated geometry may differ from what the file was made
  with.

Version 0.3's digest covers more inputs than 0.2's, so a file made with
version 0.2 logs that warning once when it is reopened. Stamps written by
version 0.1.0 have no digest; they are compared on Magic, tech and PDK
alone.

`audit` reads a file without registering any library and reports the cells
of all four libraries: cells with an error marker, without a stamp, with no
shapes, or stamped by a different Magic, PDK or generator code than the
installed one, and a file database unit that doesn't divide 5 nm. A cell
belongs to a PDK by its library name, since several PDKs have a device
called `rm1`. It also reports a device whose Magic output lies on a finer
grid than the file's database unit: the manifest records, for each device,
the coarsest grid that all coordinates of its default output lie on. `--regen`
also registers the libraries the file uses, with every variant generated by
Magic as if the memo and the disk cache were empty, and compares each cell's
stored geometry with what the installed Magic generates now; a difference, or
a cell that regenerates as the error marker, is a problem. A disk-cache entry
that differs from what Magic generates now is reported too, and replaced.
`audit` exits 1 when any cell or the file has a problem.

```sh
python3 -m klayout_magic_pcells audit design.gds --regen
```

## If Magic is missing or fails

`register()` starts Magic before it registers a library. If Magic, a PDK's
rcfile or its manifest is missing, if Magic doesn't start, or if the running
Magic doesn't define every generator in the manifest (an rcfile that loads no
PDK or another PDK, or a generator file that fails to load), it logs one
error for that PDK, naming the variable to set, and registers no library for
it. The error carries Magic's exit status and its last messages on stderr,
such as
`Could not find file '/nonexistent/sky130A/libs.tech/magic/sky130A.tech'`
for a wrong `PDK_ROOT`. Registering the devices that are present and leaving
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
when the vendor GDS of a fixed device is missing. KLayout saves that marker,
`audit` reports it, and `generate` exits 1.

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
`subcon_06v0_draw`). Research for this version also found, by reading
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

1. the unit tests (`tests/unit`, 64 tests: configuration including the PDK
   selection and per-PDK settings, the wire format, the cache key and cache
   files including damaged and swapped entries, value formatting and the
   checks of coverage strings, choices and number lists, the GDS import,
   stamps and their digest, the PCell declarations of all four manifests,
   the manifests' counts, box-paint entries, exclusions and coordinate grids,
   and the path A watchdog driven by a fake Magic that crashes on one point
   and hangs on another) and the backend tests for that PDK
   (`tests/backend`, 33 tests in all: every generator of the PDK generated
   twice in one Magic session with no restart; the session state put back
   after requests that change it, compared with a fresh Magic; the box a
   box-paint check reports; a device without `_check` or with one that
   raises; and, on sky130A only, a brace in a value, a killed Magic restarted
   and the request retried, a timeout, an unknown device, `_check` messages,
   the endless `mos_check` loop stopped, a coverage string holding a Tcl
   command refused by the server and, after saving and reopening a file with
   an empty cache, never run, damaged cache entries regenerated, start-up
   failures that name their cause, a missing vendor GDS named in the error
   marker, an rcfile without the PDK refused, an unwritable cache directory,
   `audit` after a local `sky130A.tcl` edit, after a vendor GDS edit and with
   a stale cache entry, `audit` on a file at dbu 0.005, the CLI's exit codes
   and temporary directories, a manifest whose names collide, no Magic left
   running after the client exits normally or is killed, registration from
   plain Python, and all four libraries registered under `klayout -b -rm`
   and from the Salt autorun under `klayout -zz`);
2. `tools/build_manifest.py --pdk <pdk> --check`;
3. the sweep (`tests/parity/gen_sweep.py`): for each device the defaults,
   the minimum and maximum of each number, a value below each minimum that
   Magic enforces, each checkbox flipped, counts of 1 and 4, each other
   choice of a selectlist, `2` and `1 2` for a number list, `+50` and `-50`
   for each coverage string, ` -50` and a tab before `+30` on the first and
   last coverage string, W and L off the 0.01 µm grid, `w = 0` and `l = 0`
   on resistors and diodes, a MOSFET more than 30 µm wide, and 5 seeded
   random combinations, at most 60 points per device; for each box-paint
   generator its minimum on each side, 5 nm below it on each side, squares,
   wide and tall boxes, an off-grid width, 20 × 20 µm and 5 random sizes.
   The text for Magic and the typed values for the PCell come from
   `tests/parity/magic_text.py`, which restates this README's formatting
   contract and imports nothing from the plugin; coverage strings are used
   exactly as typed;
4. path A, Magic alone: `tests/parity/magic_ref.tcl` calls `magic::gencell`
   for every device point, and for a box-paint point sets the box and calls
   the generator with no arguments, all in one Magic process run in an empty
   directory, using none of this package's code. It takes the generator
   namespace from the PDK's own `PDKNAMESPACE`, puts back the layer locks,
   units and box stack after every point as the server does, and has its own
   copy of the endless-loop guard; `run_sweep.py` watches it: a point on
   which Magic crashes or makes no progress for 300 s is recorded as a Magic
   error, and Magic starts again on the next point;
5. path B, the PCell: `tests/parity/pcell_path.py` under `klayout -b -rm`
   with only that PDK's library registered, first with an empty cache and
   then again from the cache;
6. per point: the request path B actually sent (read back through the
   stamp's key) against the text path A gave Magic; XOR of every layer, the
   number of unmerged shapes on every layer, and comparison of every label
   with all its attributes against path A; a census of the raw GDS records of
   path A's file against `baseline/<pdk>/census.json`, for elements that
   KLayout has no shape for (the NODE elements above); the bounding box (and,
   for each generator's defaults, the box in the manifest); Magic's cell name;
   Magic's checked values (for a box-paint point, the box Magic used); the
   cached run against the first run; no error marker; and the stamp;
7. for box-paint generators in the PDK's menu, the menu entry itself:
   `tests/parity/menu_ref.tcl` under `xvfb-run magic -d XR` invokes the entry
   on the box of each generator's default, wide and 20 × 20 µm points, and
   the result must equal path A's;
8. round trips on the default, minimum and maximum points plus a 10 % sample:
   reopen the GDS and OASIS files with the library (live PCell, stored values,
   regenerated geometry) and without it (a `<defunct>` cell that keeps the
   stored geometry, and its stamp), save again without the library and reopen
   with it, and place each default in host layouts with database units of
   0.5 nm and 5 nm;
9. DRC with both tools on both paths, with each device's points on one sheet
   and each device's defaults also run alone, compared as sets of rule IDs,
   and the defaults compared with `baseline/<pdk>/drc-defaults.json`. KLayout
   runs the PDK's own deck: `sky130A_mr.drc` (feol, beol and offgrid on,
   floating_met and seal off), `gf180mcu.drc` (`decks=all,-density`,
   variant D) and the IHP PDKs' `run_drc.py` (`--no_density`, one process,
   one thread; with one thread per CPU, KLayout 0.30.11 crashed once with
   signal 11 on an `npn13g2v` sheet, which passed when run again; a DRC run
   that fails is tried once more). The density
   decks are left out: sky130A's divides by zero on a cell without a
   prBoundary, and the others weren't tried on lone devices. Magic runs
   `drc(full)` with the PDK's rcfile, on the cell and
   a 10 µm margin around it (without the margin Magic clips an error area
   that lies outside a lone device's bounding box: sky130A `via4` at its
   minimum loses `met5.1`);
10. Magic extraction of every MOSFET point on both paths: the same devices on
    both sides, and the model, W, L and count (`nf × m`, or `ng × m`) matching
    Magic's checked values, except for the patterns recorded in
    `baseline/<pdk>/extract-known.json` (see [Known
    differences](#known-differences)).

Every generator of every PDK is in the sweep; the excluded helpers are listed
in each report with the reason.

### Last full run

2026-11-21, Magic 8.3.681, KLayout 0.30.11, in the image listed under
[Requirements](#requirements), at commit b74f174 (this README was the only
uncommitted file): `scripts/parity.sh`, all four PDKs one after another,
printed `PARITY PASS over 4 PDKs` and exited 0, 6,458 points in 40 minutes of
harness time on 6 CPUs. Each PDK's run included its unit and backend tests
and its manifest check, and checked DRC and the GDS census against the
committed baselines (written by an earlier full run with `--update-baseline`).

The sky130A sweep has 2,427 points, against 2,234 in version 0.2: the 195
box-paint points are new, and `res_iso_pw` lost its `max:l` and `max:val`
points, whose sweep caps (20 µm, 10 kΩ) were below its defaults (26.5 µm,
30.5 kΩ) and are no longer used.

The notes under each table are points that pass but are listed in the
report.

**sky130A** (`sky130_magic`): `PARITY PASS 2427/2427` in 10 min; 64 unit and 32 backend tests passing (1 skipped as not for this PDK); manifest check passing; KLayout DRC: sky130A_mr.drc with beol=true, feol=true, floating_met=false, offgrid=true, seal=false, thr=1.

| Family | Points | Pass | Fail |
|---|---|---|---|
| MOSFET | 685 | 685 | 0 |
| Varactor | 173 | 173 | 0 |
| Resistor | 821 | 821 | 0 |
| MIM capacitor | 53 | 53 | 0 |
| Diode | 344 | 344 | 0 |
| Photodiode | 12 | 12 | 0 |
| Fixed layout | 144 | 144 | 0 |
| Box paint | 195 | 195 | 0 |

- 59 points where Magic writes an empty cell, which the PCell reproduces (box paint at a box 5 nm below the minimum: 26, diode at a zero size: 10, resistor at a zero size: 23)
- 4 default points whose 5 nm host placement is n/a: Magic's GDS has coordinates off the 0.005 um grid on 83/44
- 10 MOSFET points that match a known extraction pattern (`nfet_g5v0d16v0` 5, `pfet_g5v0d16v0` 5)
- 39 box-paint points through Magic's menu entry under Xvfb: identical 39
- 60 `below:` points where a second `_check` would change Magic's checked values (recorded, not checked)

**gf180mcuD** (`gf180mcu_magic`): `PARITY PASS 1493/1493` in 5 min; 64 unit and 5 backend tests passing (28 skipped as not for this PDK); manifest check passing; KLayout DRC: gf180mcu.drc with decks=all,-density, run_mode=deep, threads=1, variant=D.

| Family | Points | Pass | Fail |
|---|---|---|---|
| MOSFET | 429 | 429 | 0 |
| MOS capacitor | 140 | 140 | 0 |
| Varactor | 140 | 140 | 0 |
| Resistor | 425 | 425 | 0 |
| MIM capacitor | 21 | 21 | 0 |
| Diode | 116 | 116 | 0 |
| Fixed layout | 132 | 132 | 0 |
| Box paint | 90 | 90 | 0 |

- 70 points where Magic writes an empty cell, which the PCell reproduces (box paint at a box 5 nm below the minimum: 12, diode at a zero size: 8, every point of `eFuse`: 12, every point of `npn_00p54x08p00`: 12, every point of `npn_00p54x10p00`: 12, resistor at a zero size: 14)
- 66 MOSFET points that match a known extraction pattern (`nfet_10v0_asym` 33, `pfet_10v0_asym` 33)
- 15 box-paint points through Magic's menu entry under Xvfb: identical 15
- 40 `below:` points where a second `_check` would change Magic's checked values (recorded, not checked)

**ihp-sg13g2** (`sg13g2_magic`): `PARITY PASS 1379/1379` in 13 min; 64 unit and 5 backend tests passing (28 skipped as not for this PDK); manifest check passing; KLayout DRC: run_drc.py --no_density --mp=1 --density_thr=1.

| Family | Points | Pass | Fail |
|---|---|---|---|
| MOSFET | 460 | 460 | 0 |
| Varactor | 17 | 17 | 0 |
| Resistor | 303 | 303 | 0 |
| MIM capacitor | 62 | 62 | 0 |
| Diode | 84 | 84 | 0 |
| Bipolar transistor | 86 | 86 | 0 |
| Inductor | 22 | 22 | 0 |
| Bond pad | 17 | 17 | 0 |
| Via stack | 22 | 22 | 0 |
| Fixed layout | 96 | 96 | 0 |
| Box paint | 210 | 210 | 0 |

- 51 points where Magic writes an empty cell, which the PCell reproduces (box paint at a box 5 nm below the minimum: 28, diode at a zero size: 4, resistor at a value below its minimum: 4, resistor at a zero size: 15)
- 1 default point whose 5 nm host placement is n/a: Magic's GDS has coordinates off the 0.005 um grid on 10/25
- 220 MOSFET points that match a known extraction pattern (`sg13_hv_rfnmos` 55, `sg13_hv_rfpmos` 55, `sg13_lv_rfnmos` 55, `sg13_lv_rfpmos` 55)
- 24 box-paint points through Magic's menu entry under Xvfb: identical 24
- 22 `below:` points where a second `_check` would change Magic's checked values (recorded, not checked)

**ihp-sg13cmos5l** (`sg13cmos5l_magic`): `PARITY PASS 1159/1159` in 12 min; 64 unit and 4 backend tests passing (29 skipped as not for this PDK); manifest check passing; KLayout DRC: run_drc.py --no_density --mp=1 --density_thr=1.

| Family | Points | Pass | Fail |
|---|---|---|---|
| MOSFET | 460 | 460 | 0 |
| Varactor | 17 | 17 | 0 |
| Resistor | 257 | 257 | 0 |
| Capacitor | 22 | 22 | 0 |
| Diode | 84 | 84 | 0 |
| Bipolar transistor | 39 | 39 | 0 |
| Inductor | 22 | 22 | 0 |
| Bond pad | 16 | 16 | 0 |
| Via stack | 20 | 20 | 0 |
| Fixed layout | 72 | 72 | 0 |
| Box paint | 150 | 150 | 0 |

- 37 points where Magic writes an empty cell, which the PCell reproduces (box paint at a box 5 nm below the minimum: 20, diode at a zero size: 4, resistor at a zero size: 13)
- 220 MOSFET points that match a known extraction pattern (`sg13_hv_rfnmos` 55, `sg13_hv_rfpmos` 55, `sg13_lv_rfnmos` 55, `sg13_lv_rfpmos` 55)
- 18 box-paint points through Magic's menu entry under Xvfb: identical 18
- 22 `below:` points where a second `_check` would change Magic's checked values (recorded, not checked)

### Mutations the harness catches

Each line is a copy of the package with one change, run with
`run_sweep.py --pdk <pdk> --no-unit --no-drc --no-extract --devices ...` on
2026-11-21. The control is the same run on the unchanged package.

| Change to the package | PDK and devices | Result |
|---|---|---|
| none (control) | sky130A: `nfet_01v8`, `res_generic_po`, `cap_mim_m3_1`, `via1` | PASS 144/144 |
| `format_float` writes `%.1g` | same | FAIL 37/144: request 37, checked 30, geometry 23, bbox 23, magic_cell 22, texts 15, roundtrip 6, stamp 2 |
| `format_float` drops the `.0` (`31` instead of `31.0`) | same | FAIL 25/144: request 25, checked 13 (no geometry changes) |
| the importer turns every label 90°, sets its size to 0 and right-justifies it | same | FAIL 126/144: texts 126, roundtrip 39 |
| the importer inserts every shape twice | same | FAIL 141/144: geometry 141 (the merged XOR is unchanged; the shape counts differ) |
| none (control) | ihp-sg13g2: `sg13_lv_nmos`, `rsil`, `via1`, `subconn_guard` | PASS 138/138 |
| `format_float` writes `%.1g` | same | FAIL 42/138: request 42, checked 38, geometry 32, bbox 32, magic_cell 17, texts 6, roundtrip 4, stamp 4 |
| none (control) | gf180mcuD: `nfet_03v3`, `ppolyf_u`, `via1` | PASS 78/78 |
| `format_float` writes `%.1g` | same | FAIL 27/78: request 27, checked 23, geometry 19, bbox 19, magic_cell 15, roundtrip 4, stamp 2 |

In version 0.2 the sweep took its text from the plugin's own formatter, and
the `%.1g` mutation passed 99 of 99 points.

### CI

`.github/workflows/parity.yml` runs one job per PDK in the image, pulled by
digest: `scripts/parity.sh --pdk <pdk> --quick` on pull requests and the full
sweep on a weekly schedule and on manual runs. Each job uploads
`out/parity/<pdk>/`. GitHub had not run the workflow as of 2026-11-21.
GitHub lists 14 GB of disk for standard runners and the image is 11.7 GB
unpacked, so each job frees disk space first and prints `df` before and
after the pull; whether that is enough is unknown.

## Known differences

Where the PCells don't reproduce Magic, or where Magic's tools disagree with
the drawn values:

- The NODE elements of five sky130A vendor cells (see [Why Magic is the
  backend](#why-magic-is-the-backend)).
- A coverage string, choice or number list that would reach Tcl as code draws
  the error marker, where Magic would reset it or draw nothing (see
  [Parameters](#parameters)).
- A typed resistor `val` changes nothing (see [A typed
  resistance](#a-typed-resistance-val)).
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
  research for this version).

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
  coordinates, and one of 5 nm rounds the 1 nm coordinates listed above.
  `audit` reports both.
- Another package that registers a library under one of these four names
  would replace it. The PDKs' own libraries have other names (`skywater130`;
  `gf180mcu`, `gf180mcu_klayoutapi`, `gf180mcu_sealring`; `SG13_dev`,
  `SG13_native_pcell_lib`, `sg13g2_stdcell_hv`, `sg13cmos5l_stdcell_hv`); the
  IHP libraries use device names such as `rsil` and `inductor2` too, so a
  layout that holds both gets cell names that KLayout makes unique. Loading
  them together with these libraries has not been tried, and neither has the
  IHP PDKs' autorun, which imports every module on `sys.path` whose name
  starts with `sg13` (this package's doesn't).
- Not tried: the GUI parameter form on screen, the Salt manager, KLayout's
  `.mag` reader, `ext2spice merge`, the PDKs' own LVS decks, and KLayout DRC
  with the density decks.

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
- Floats are sent as 12 significant digits rather than `repr()`, and a value
  equal to Magic's default is sent as Magic's default text. Without this, a
  reopened file changed its requests.
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
  shape counts, every label attribute, the GDS census, the menu check), a
  known-extraction list per PDK, the manifest check, and a watchdog on
  path A. Path A's request text is independent of the plugin. The entry
  point is `scripts/parity.sh`, as in the design.
- `docs/design.md` section 4.2 gave the wrong reason for leaving out Magic's
  dialog callbacks; it now says so.

## Licences and credits

The project's own licence hasn't been chosen yet, so there is no `LICENSE`
file. The shipped manifests are data extracted from the PDKs' Magic Tcl
files; nobody has checked whether open_pdks' and IHP's licences allow
shipping them under the project's licence. The harness runs the PDKs' KLayout
DRC decks from the PDK install and doesn't copy them (`sky130A_mr.drc`
says GPLv3 in its header, the IHP deck Apache-2.0; gf180mcu's wasn't
checked).

The devices themselves are Magic's: the generators in the PDKs' Tcl files
(sky130A.tcl by Tim Edwards, according to its header) and Magic's
`toolkit.tcl`, from open_pdks, the IHP PDKs and Magic.

Two earlier projects were read for their structure and licences, and no code
was copied from either:

- [efabless/sky130_klayout_pdk](https://github.com/efabless/sky130_klayout_pdk),
  Apache-2.0, with Python PCells by Mabrains LLC and Efabless; the same PCell
  code ships in the PDK as the `skywater130` library.
- [laurentc2/SKY130_for_KLayout](https://github.com/laurentc2/SKY130_for_KLayout),
  BSD-2-Clause, a technology, DRC and LVS setup with no PCells.
