# klayout-magic-pcells

This is a KLayout library, `sky130_magic`, with 60 PCells for the sky130A
devices that Magic generates. Each PCell asks Magic's own generator in the PDK
(`libs.tech/magic/sky130A.tcl`) to draw the device, then copies the GDS that
Magic writes into the PCell cell. A device placed in KLayout therefore has
the same polygons and labels as the same device generated in Magic.

Status: version 0.2.0, a local repository with no remote. The parity harness
(see [Tests](#tests)) passes on all 2,234 parameter points of the full sweep,
run on 2026-11-21 in the iic-osic-tools image listed under
[Requirements](#requirements). The library loads under
`klayout -b -rm` and from the Salt autorun under `klayout -zz`. It has not
been tried in the KLayout GUI: the GUI-only parts (warning icons in the
parameter form, lazy evaluation) were written from KLayout's source code and
have not been seen on screen.

The design is in [docs/design.md](docs/design.md). Where this README and the
design disagree, the README describes the code as it is; the differences are
listed under [Changes from the design](#changes-from-the-design).

## Why Magic is the backend

The other sky130 PCells for KLayout (the PDK's `skywater130` library, whose
code is also in efabless/sky130_klayout_pdk) draw each device with their own
Python code, so their geometry is independent of Magic's. Several steps that
decide Magic's final geometry happen only when Magic writes GDS, through the
`gdsii` output style in `sky130A.tech`:

- contact cuts: the `.mag` of an nfet holds contact areas, and the GDS gets
  the individual 0.17 µm licon and mcon squares;
- resistor slots on the high-poly resistors, and the via3 cut array of the
  MIM capacitors;
- label moves from the drawn layer to the contact layer (the MIM cap's C2 is
  drawn on metal3 and written on 71/5);
- the 235/4 prBoundary box, made from the `FIXED_BBOX` property;
- the 12 fixed-layout devices, whose bytes are copied from the vendor
  `sky130_fd_pr.gds`.

This library doesn't reproduce those steps in Python. It takes the GDS that
Magic writes as the device.

## Parity definition

Parity here means: for a given set of parameter values, the PCell cell,
flattened, has the same polygons on every GDS layer/datatype and the same
label texts (string and position) as the GDS that Magic writes when
`magic::gencell` is called once with those values. The comparison is an XOR
per layer at a common database unit, with no tolerance and no alignment. Cell
names, hierarchy, GDS properties and timestamps are not compared.

## Requirements

- KLayout 0.30.5 or later, with Python. Only 0.30.11 has been tested.
- Magic with Tcl. Tested with 8.3.681.
- The sky130A PDK from open_pdks. Tested with commit 026824c7.
- Linux. Windows and macOS are out of scope.
- For use from plain `python3`, the `klayout` pip module (0.30.11 tested).

The image `hpretl/iic-osic-tools@sha256:3c371645b19c6f6564dc8c7b21e39ad1c1833d274fe5b85639afe1ba9d7987e7`
has all of these.

## Installing

The repository is a KLayout Salt package (it has a `grain.xml`). Link it into
KLayout's `salt` folder:

```sh
ln -s /path/to/klayout-magic-pcells ~/.klayout/salt/klayout-magic-pcells
```

In the iic-osic-tools image the folder is `/headless/.klayout/salt/`. KLayout
then runs `pymacros/klayout_magic_pcells.lym` at start-up, which registers the
library. Installing through the Salt manager or `klayout -y` has not been
tried.

Check the setup:

```sh
PYTHONPATH=/path/to/klayout-magic-pcells/python python3 -m klayout_magic_pcells doctor
```

`doctor` prints every setting and where it came from, starts Magic, compares
the running Magic's device defaults with the shipped manifest (the device
list built from Magic, see [Devices](#devices)), and times one
nfet generation (about 20 ms in the image).

## Usage

**In the GUI**, the library is `sky130_magic` and the PCells carry Magic's
full device names, such as `sky130_fd_pr__nfet_01v8`. The library isn't bound
to a technology, so it is listed under every technology.

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

lib = kmp.register()          # None, with one logged error, if Magic can't start
ly = db.Layout()
top = ly.create_cell("TOP")
m1 = ly.create_cell("sky130_fd_pr__nfet_01v8", "sky130_magic", {"w": 1.5, "l": 0.5, "nf": 3})
top.insert(db.CellInstArray(m1.cell_index(), db.Trans()))
ly.write("out.gds")
```

The package also has a command line:

```sh
python3 -m klayout_magic_pcells devices -v            # PCells and their parameters
python3 -m klayout_magic_pcells check sky130_fd_pr__nfet_01v8 w=0.1 l=0.1
python3 -m klayout_magic_pcells generate sky130_fd_pr__cap_mim_m3_1 w=5 l=10 -o cap.gds
```

`check` runs the device's `_check` proc from `sky130A.tcl` once (Magic's own
validation, which clamps bad values and prints a message) and shows what it
changes:

```
sky130_fd_pr__nfet_01v8: Magic draws w=0.42 (entered 0.1)
sky130_fd_pr__nfet_01v8: Magic draws l=0.15 (entered 0.1)
  message: Mos length must be >= 0.15 um
  message: Mos width must be >= 0.42 um
```

Each time KLayout asks a PCell to draw a variant (the cell KLayout makes for
one set of parameter values), the PCell's `produce` call builds the request
for Magic, looks in an in-memory memo and then in the disk cache, and only
then asks Magic. One Magic process
(`magic -dnull -noconsole`) runs per KLayout process, started when the
library registers. It takes about 0.23 s to start and 15 to 20 ms per device.

## Parameters

Every parameter that Magic's own dialog lets you edit is a PCell parameter,
49 names across the 60 devices. Their types come from the manifest, a JSON
file built from Magic (see [Devices](#devices)):

| In Magic's dialog | PCell type | Sent to Magic as |
|---|---|---|
| number entry | double | 12 significant digits, written like a Python float (`0.35`, `31.0`); a value equal to Magic's default is sent as Magic's default text (`0.420`) |
| `nf`, `m`, `nx`, `ny` | int | `3` |
| checkbox | boolean | `1` or `0` |
| the eight "[+/-](%)" coverage entries: `viasrc`, `viadrn`, `viagate`, `viagb`, `viagr`, `viagl`, `viagt`, `ccov` | string | the text as typed, whitespace included, if it is a number; anything else is refused (see below) |

The coverage entries are strings because Magic reads their first character as
an anchor: `+50`, `-50` and `50` are three different layouts, and a KLayout
double has no way to hold `+50`. Whitespace counts too: ` -50` starts with a
space, so it has no anchor and draws like `50`. Keys that Magic's dialog
doesn't show (`lmin`, `wmin`, `class`, `rho` and so on) are not PCell
parameters; Magic uses its own values for them.

sky130A.tcl checks the coverage strings with an unbraced `expr abs($viagb)`,
and Tcl substitutes any `[command]` or `$variable` inside such a value. A
file whose instance held `viagb = [exec ...]` would run that command as soon
as it was opened. The PCell therefore sends a coverage string only if it is
a decimal number with an optional `+` or `-` in front and optional spaces or
tabs around it, such as `+50`, `-50`, `50.5`, ` -50` or `1e2`. For anything
else (`abc`, an empty string, `0x32`, `[exec ...]`) it draws the error marker
described under [If Magic is missing or fails](#if-magic-is-missing-or-fails),
and Magic never sees the value. In the GUI form that parameter should get an
error icon (written from KLayout's source, not seen on screen), and the CLI
`check` exits 2. Magic itself would have reset some of these values (on a
MOSFET `abc` becomes 0, with a message) and drawn nothing for others (on a
diode), so for text that is not a number the PCell differs from Magic on
purpose. The Magic server also answers with an error for any value that
contains `[`, `]`, `$` or a backslash, whoever sends it.

Floats are rounded to 12 digits because KLayout 0.30.11 doesn't store doubles
exactly in a saved file: `0.35` reads back as `0.35000000000000003` in a new
process, which would otherwise change the request, and with it the cache key,
every time a file is reopened. They always carry a decimal point because
sky130A.tcl does arithmetic with Tcl's `expr` and `/`, which divide two
integer strings as integers. A value with 13 or more significant digits is
therefore not the text Magic gets: `0.4244999999999` is sent as `0.4245`.
Magic's cell name and checked values can then differ from Magic given the
longer text, because Magic rounds to three decimals for the name. No geometry
difference has been found: `nfet_01v8` with `w` at 0.4225, 0.4275, 1.0045 and
5.005, each against the same value 1e-14 lower, drew the same polygons in
Magic.

Apart from refusing coverage strings that are not numbers, the PCells add no
limits, no snapping and no choices of their own. Magic's `_check` is the
only check of the values, and it runs once per generation, on the values you
entered. KLayout stores the values you entered, not the values
Magic corrected them to, so a file can hold `l = 0.1` for a device that Magic
drew with `l = 0.15`. In the GUI parameter form, a parameter that `_check`
changed should get a warning icon and a tooltip such as
`Magic draws 0.15 (entered 0.1): Mos length must be >= 0.15 um`; that comes
from KLayout's source and hasn't been seen on screen. Outside the GUI,
Magic's messages go to KLayout's log as warnings.

Magic's own dialog behaves differently: it runs `_check` on every field edit,
writes the corrected values back into the form, and checks again when you
press Create.
Running `_check` twice changes the result for some inputs (in the full sweep,
60 of the 2,234 points, all of them diode `area`/`peri` or resistor `val`
recalculations), so a dialog user and a `magic::gencell` caller can end up
with different values and cell names. This library follows `magic::gencell`.
Which of the two it should follow is an open question for the project lead.

### Magic behaviour the PCells reproduce

Parity means these come out of the PCells exactly as Magic has them:

- MOSFET `w` is the width of one finger. `w 1.5 nf 3` is 4.5 µm of total
  width. The PCell form calls it "Finger width".
- Off-grid values are not snapped. The drawing rounds W and L to 0.01 µm, so a
  requested `w 0.425` is drawn 0.43 µm wide, and two inputs that draw the same
  geometry are two different variants.
- `_check` recalculates `val`, `area` and `peri`. After a clamp, `val` is
  computed from the unclamped width.
- Zero sizes give an empty cell on some devices. For `l = 0` on 17 of the 22
  resistors, `_check` replaces the length with the minimum as a SPICE string
  (`1.0u`, `170.0n`) and `_draw` then fails with
  `can't use non-numeric string as operand of "+"`. For `w = 0` on
  `res_generic_l1` and `res_generic_m1` to `m5`, `_draw` fails with
  `integer value too large to represent`. For `w = 0` or `l = 0` on five
  diodes (`diode_pd2nw_05v5`, `_05v5_hvt`, `_05v5_lvt`, `diode_pw2nd_05v5`,
  `_05v5_lvt`), `_draw` fails with
  `can't use non-numeric string as operand of "/"`. In each case Magic writes
  a cell with no shapes. The PCell writes the same empty cell and logs a
  warning rather than drawing the error marker described under
  [If Magic is missing or fails](#if-magic-is-missing-or-fails); `generate`
  exits 1 and `audit` reports `empty cell`. The other resistors and diodes
  clamp the size and draw normally. Whether an empty device should get the
  error marker instead is an open question for the project lead: drawing it
  would break parity with Magic's empty cell, and keeping the empty cell
  leaves a device with no shapes in a saved file.
- Fixed devices (`nocell` in Magic) place the vendor cell from `libs.ref` at
  the origin, with `nx` × `ny` copies at a pitch of `xstep + deltax` by
  `ystep + deltay`. `fixed_check` prints `NY must be >= 1` for `ny 0` but
  resets `nx` instead of `ny` (sky130A.tcl line 8070), so `ny 0` draws one
  device. The photodiode goes through the same `fixed_check`, but its own
  drawing loop then runs zero times: `ny 0` gives a 21.36 × 13.36 µm guard
  ring with no photodiode in it (no 81/81 layer).
- Labels appear only as texts on the `*/5` layers; there are no `*/16` pin
  shapes. `cap_var*` and the photodiode have no labels, the `g5v0d16v0` FETs
  have no D label, and the MIM cap's C2 is on 71/5.
- Four fixed devices (`pnp_05v5_W0p68L0p68`, `rf_test_coil1` to `3`) have
  shapes on 83/44 (`text.drawing`) whose coordinates are not on the 5 nm grid
  in the vendor GDS. They are exact in a host layout with a database unit of
  1 nm or 0.5 nm, and get rounded at 5 nm.

The library avoids three Magic behaviours instead of reproducing them:

- `sky130::mos_check` loops forever when a MOSFET or varactor has both `w`
  and `l` above 28 µm, whatever `nf` and `m` are: its tap-spacing loop sets
  `w` to 29 and then tests the same condition again, printing
  `Transistor width must be < 29 um` on every pass. Magic's own dialog hangs
  on these values too. The server counts the messages each request prints,
  and once one message has been printed 10,000 times it stops the request,
  which ends before anything is drawn. The PCell then draws the error marker,
  in about 0.1 s and without restarting Magic.
- Magic's cell name is the device name plus a hash of the values, rounded to
  three decimals and with a leading `+` dropped. `viasrc 50` and
  `viasrc +50` get the same Magic cell name and different geometry. In one
  Magic session, the second request paints into the cell that the first one
  made, so the cell ends up with both layouts painted over each other. The
  backend deletes each cell after writing it, and its cache key uses the text
  you entered.
- `gencell_create` called with an empty parameter dict takes the dialog
  branch and fails in batch; the backend always passes the merged defaults.

## Configuration

A value comes from the environment if set, then from
`$XDG_CONFIG_HOME/klayout-magic-pcells/config.ini` (else
`~/.config/klayout-magic-pcells/config.ini`, section `[kmp]`, keys in lower
case without the `KMP_` prefix, for example `magic = /opt/magic/bin/magic`),
then from the default. `klayoutrc` isn't used because KLayout doesn't save it
under `-b`.

| Variable | Default | Meaning |
|---|---|---|
| `KMP_MAGIC` | `magic` on `PATH`, then `/foss/tools/bin/magic` | Magic executable |
| `PDK_ROOT` | `/foss/pdks` | directory that holds `sky130A`; the sky130A rcfile reads it too |
| `KMP_PDK` | `sky130A` | PDK variant; this version accepts only `sky130A` |
| `KMP_MAGICRC` | `$PDK_ROOT/$KMP_PDK/libs.tech/magic/$KMP_PDK.magicrc` | Magic rcfile |
| `KMP_CACHE_DIR` | `$XDG_CACHE_HOME/klayout-magic-pcells`, else `~/.cache/klayout-magic-pcells` | cache root |
| `KMP_CACHE` | `1` | `0` keeps nothing on disk between sessions |
| `KMP_BACKEND` | `server` | `server`, or `oneshot` (one Magic process per request, for debugging) |
| `KMP_TIMEOUT` | `30` | seconds per request |
| `KMP_LAZY` | `0` with `server`, `1` with `oneshot` | when 1, the GUI form shows an Update button instead of regenerating on every edit |
| `KMP_MANIFEST` | the shipped manifest | path to a rebuilt manifest |
| `KMP_LOG` | unset | file that receives every request and reply line |

The plugin reads `KMP_PDK` and ignores `PDK`, because the iic-osic-tools
image sets `PDK=ihp-sg13g2` by default. A GUI started from a desktop launcher
may not get the login shell's `PATH`; set `magic` in `config.ini` then.

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
`KMP_CACHE_DIR`. Each Magic process runs in its own directory under
`<cache>/run` (or the system temp directory without a usable cache), which
is deleted when Magic stops.

The key is a SHA-256 over the device, the request text, the Magic version,
the open_pdks commit, the tech file version, a digest of the text of every
`::sky130` and `::magic` proc loaded in the running Magic, a digest of
`sky130A.tech`, and the cache format (2 in this version). Editing
`sky130A.tcl` locally therefore starts new entries. A new Magic, PDK or
cache format starts a new versions directory. To manage them:

```sh
python3 -m klayout_magic_pcells cache prune    # delete every versions directory but the current one
python3 -m klayout_magic_pcells cache clear    # delete the cache
python3 -m klayout_magic_pcells cache stats
```

## Stamps and audit

Every variant carries two stamps of the form
`kmp1;magic=8.3.681;tech=1.0.588-56-g026824c;pdk=sky130A;digest=<12 hex>`.
The digest is a SHA-256 over the PDK name, the Magic version, the open_pdks
commit, the tech version, the text of the loaded `::sky130` and `::magic`
procs and `sky130A.tech`, so a locally edited `sky130A.tcl` gives a
different stamp even when the version strings are the same.

- *generated by*: a GDS property (attribute 100) on one shape, the 235/4 box
  where the device has one, with the first 16 hex digits of the cache key
  added. It survives GDS and OASIS with or without the library.
- *created with*: the hidden PCell parameter `kmp_created`, stored in the
  file with the other parameters. When a file is reopened under a different
  Magic or PDK, or with edited generator code, produce logs a warning,
  because the regenerated geometry may differ from what the file was made
  with.

Stamps written by version 0.1.0 have no digest; they are compared on Magic,
tech and PDK alone.

`audit` reads a file without registering the library and reports cells with
an error marker, without a stamp, with no shapes, or stamped by a different
Magic, PDK or generator code than the installed one, and a file database
unit that doesn't divide 5 nm. It also reports a device whose Magic output
lies on a finer grid than the file's database unit: the manifest records,
for each device, the coarsest grid that all coordinates of its default
output lie on (5 nm for 56 devices, 1 nm for `pnp_05v5_W0p68L0p68` and
`rf_test_coil1` to `3`). `--regen` also registers the library and compares
each cell's stored geometry with what the installed Magic generates now; a
difference, or a cell that regenerates as the error marker, is a problem.
`audit` exits 1 when any cell or the file has a problem.

```sh
python3 -m klayout_magic_pcells audit design.gds --regen
```

## If Magic is missing or fails

`register()` starts Magic before it registers anything. If Magic, the rcfile
or the manifest is missing, if Magic doesn't start, or if the running Magic
doesn't define every device in the manifest (an rcfile that loads no PDK, or
a `sky130A.tcl` that fails to load), it logs one error naming the variable to
set and registers no library. The error carries Magic's exit status and its
last messages on stderr, such as
`Could not find file '/nonexistent/sky130A/libs.tech/magic/sky130A.tech'`
for a wrong `PDK_ROOT`. Registering the devices that are present and leaving
out the missing ones is not supported. Cells in files opened while the
library isn't registered show as
`<defunct>sky130_magic.…` and keep the geometry stored in the file; saving
keeps that geometry. Call `klayout_magic_pcells.register()` from the macro
console once the setting is fixed, and the open cells come back as live
PCells.

If a generation fails while the library is registered (Magic failed twice in
a row, timed out, stopped in the endless `mos_check` loop, or wrote a GDS that
KLayout can't read), or a coverage string isn't a number, produce doesn't
raise. It draws a 1 × 1 µm box and a `KMP_ERROR <device>: <reason>` text on layer
255/0, which `sky130A.lyp` doesn't list. The reason includes what Magic
printed, for example
`Can't find GDS file "$PDKPATH/libs.ref/sky130_fd_pr/gds/sky130_fd_pr.gds"`
when the vendor GDS of a fixed device is missing. KLayout saves that marker,
`audit` reports it, and `generate` exits 1.

## Devices

The library has a PCell for each of the 60 devices that `sky130A.tcl`
defines with both a `_defaults` and a `_draw` proc. Names below drop the `sky130_fd_pr__` prefix (and
`sky130_fd_bs_flash__` for the SONOS FET).

| Family | Count | Devices |
|---|---|---|
| MOSFET | 12 | `special_sonosfet_star`, `nfet_01v8`, `nfet_01v8_lvt`, `nfet_03v3_nvt`, `nfet_05v0_nvt`, `nfet_g5v0d10v5`, `nfet_g5v0d16v0`, `pfet_01v8`, `pfet_01v8_hvt`, `pfet_01v8_lvt`, `pfet_g5v0d10v5`, `pfet_g5v0d16v0` |
| Varactor | 3 | `cap_var`, `cap_var_hvt`, `cap_var_lvt` |
| Resistor | 22 | `res_generic_l1`, `res_generic_m1` to `m5`, `res_generic_nd`, `res_generic_nd__hv`, `res_generic_pd`, `res_generic_pd__hv`, `res_generic_po`, `res_high_po_0p35`, `_0p69`, `_1p41`, `_2p85`, `_5p73`, `res_iso_pw`, `res_xhigh_po_0p35`, `_0p69`, `_1p41`, `_2p85`, `_5p73` |
| MIM capacitor | 2 | `cap_mim_m3_1`, `cap_mim_m3_2` |
| Diode | 8 | `diode_pd2nw_05v5`, `_05v5_hvt`, `_05v5_lvt`, `_11v0`, `diode_pw2nd_05v5`, `_05v5_lvt`, `_05v5_nvt`, `_11v0` |
| Photodiode | 1 | `photodiode` |
| Fixed layout | 12 | `cap_vpp_04p4x04p6_m1m2_shieldl1`, `cap_vpp_08p6x07p8_m1m2_shieldl1`, `cap_vpp_11p5x11p7_m1m2_noshield`, `cap_vpp_11p5x11p7_m1m2m3m4_shieldl1m5`, `npn_05v5_W1p00L1p00`, `npn_05v5_W1p00L2p00`, `npn_11v0_W1p00L1p00`, `pnp_05v5_W0p68L0p68`, `pnp_05v5_W3p40L3p40`, `rf_test_coil1`, `rf_test_coil2`, `rf_test_coil3` |

The fixed-layout devices and the photodiode take only `nx`, `ny`, `deltax`
and `deltay`. The other 20 `_draw` procs in `sky130A.tcl` have no
`_defaults` proc, so Magic's gencell code can't build them as parameterized
cells, and they get no PCell:

- 13 are in Magic's "Devices 1" menu as commands that paint into the current
  box: `mcon`, `via1` to `via4`, `subconn`, `subconn_guard`, `mvsubconn`,
  `mvsubconn_guard` (the substrate contacts and guard rings), `nwell`,
  `mvnwell` (n-well regions with a guard ring), `deep_nwell` and
  `mvdeep_nwell`. Each takes no arguments, reads the box size, and prints a
  message and draws nothing when the box is below its minimum (via1:
  0.26 µm). A PCell for them would take the box size as its parameters; this
  version has none. Magic's `via4_draw` prints `Via3 width must be at least
  1.18um` for its own minimum.
- 7 are internal helpers that the device `_draw` procs call and Magic's
  menus don't offer: `cap`, `diode`, `fixed`, `guard_ring`, `mos`,
  `photodiode`, `res`.

The manifest lists all 20 with the reason, and the menu entry where there is
one. `sky130A.tcl` defines `res_xhigh_po_0p35_draw` twice with
the same body, which is why it has 81 `_draw` definitions for 80 procs.

The PCell declarations come from
`python/klayout_magic_pcells/data/manifest-sky130A.json`, built by querying
Magic in the pinned image:

```sh
scripts/manifest.sh            # rebuild it (python3 tools/build_manifest.py, in the image)
scripts/manifest.sh --check    # exit 1 if the committed manifest differs from the installed Magic
```

## Tests

Everything runs inside the pinned image, through `scripts/in_image.sh`, which
mounts the repository at `/repo` and uses a login shell (the image puts Magic
and KLayout on `PATH` only there).

```sh
scripts/test.sh                                       # unit and backend tests, about 45 s
scripts/parity.sh                                     # everything, about 7 minutes on 6 CPUs
scripts/parity.sh --quick                             # the 60 device defaults, under 3 minutes
scripts/parity.sh --devices 'sky130_fd_pr__res_*' --keep
scripts/parity.sh --update-baseline                   # rewrite the DRC baseline
```

`scripts/parity.sh` writes `out/parity/report.json` and `out/parity/report.md`
and exits 0 when every check passes, 1 when any check fails, and 2 when the
harness itself fails. It runs, in one container:

1. the unit tests (`tests/unit`, 59 tests: configuration, the wire format,
   the cache key and cache files including damaged and swapped entries,
   value formatting and the coverage-string check, the GDS import, stamps
   and their digest, the PCell declarations, the manifest's exclusions and
   coordinate grids, and the path A watchdog driven by a fake Magic that
   crashes on one point and hangs on another) and the backend tests
   (`tests/backend`, 28 tests: every device generated twice in one Magic
   session, a brace in a value, a killed Magic restarted and the request
   retried, a timeout, an unknown device, `_check` messages, the endless
   `mos_check` loop stopped, a coverage string holding a Tcl command refused
   by the server and, after saving and reopening a file with an empty cache,
   never run, damaged cache entries regenerated, start-up failures that name
   their cause, a missing vendor GDS named in the error marker, an rcfile
   without the PDK refused, an unwritable cache directory, `audit` after a
   local `sky130A.tcl` edit and on a file at dbu 0.005, the CLI's exit codes
   and temporary directories, a manifest whose
   names collide, no Magic left running after the client exits normally or
   is killed, registration from plain Python and under `klayout -b -rm`, and
   the Salt autorun under `klayout -zz`);
2. `tools/build_manifest.py --check`;
3. the sweep (`tests/parity/gen_sweep.py`): for each device the defaults, the
   minimum and maximum of each number, a value below each minimum that Magic
   enforces, each checkbox flipped, counts of 1 and 4, `+50` and `-50` for each coverage
   string, ` -50` and a tab before `+30` on the first and last coverage
   string, W and L off the 0.01 µm grid, `w = 0` and `l = 0` on resistors and
   diodes, a MOSFET more than 30 µm wide, and 5 seeded random combinations,
   at most 60 points per device. Numbers go through the plugin's own
   formatting (12 digits, Magic's default text); coverage strings are used
   exactly as typed;
4. path A, Magic alone: `tests/parity/magic_ref.tcl` calls `magic::gencell`
   for every point in one Magic process and uses none of this package's code.
   It has its own copy of the endless-loop guard, and `run_sweep.py` watches
   it: a point on which Magic crashes or makes no progress for 300 s is
   recorded as a Magic error, and Magic starts again on the next point;
5. path B, the PCell: `tests/parity/pcell_path.py` under `klayout -b -rm`,
   first with an empty cache and then again from the cache;
6. per point: the request path B sent against the text path A gave Magic,
   XOR of every layer and comparison of every label against path
   A, the bounding box (and, for each device's defaults, the box in the
   manifest), Magic's cell name, Magic's checked values, the cached run
   against the first run, no error marker, and the stamp;
7. round trips on the default, minimum and maximum points plus a 10 % sample:
   reopen the GDS and OASIS files with the library (live PCell, stored values,
   regenerated geometry) and without it (a `<defunct>` cell that keeps the
   stored geometry, and its stamp),
   save again without the library and reopen with it, and place each default
   in host layouts with database units of 0.5 nm and 5 nm;
8. DRC with both tools on both paths: KLayout's `sky130A_mr.drc` and Magic's
   `drc(full)`, with each device's points on one sheet and each device's
   defaults also run alone, compared as sets of rule IDs, and the defaults
   compared with `tests/parity/baseline/drc-defaults.json`;
9. Magic extraction of every MOSFET point on both paths: the same devices on
   both sides, and the model, W, L and count (`nf × m`) matching Magic's
   checked values.

### Last full run

2026-11-21, Magic 8.3.681, KLayout 0.30.11, open_pdks 026824c7:
`PARITY PASS 2234/2234`, with 59 unit and 28 backend tests passing and the
manifest check passing, in 7 minutes on 6 CPUs.

| Family | Points | Pass | Fail |
|---|---|---|---|
| MOSFET | 685 | 685 | 0 |
| Varactor | 173 | 173 | 0 |
| Resistor | 823 | 823 | 0 |
| MIM capacitor | 53 | 53 | 0 |
| Diode | 344 | 344 | 0 |
| Photodiode | 12 | 12 | 0 |
| Fixed layout | 144 | 144 | 0 |

Points that pass with a note, listed in the report:

- 33 zero-size points where Magic writes an empty cell (see above): 17
  resistors at `l = 0`, 6 at `w = 0`, and 5 diodes at each of `w = 0` and
  `l = 0`. The PCell writes the same empty cell, and the stamp check is
  skipped because there is no shape to carry one.
- 4 fixed devices whose 5 nm host placement isn't exact because their vendor
  GDS is off that grid (see above).
- 10 points of the two `g5v0d16v0` FETs with `nf` of 2 or more, where Magic's
  extraction of Magic's own layout reports every second finger as the
  `g5v0d10v5` model with a different length. Both paths give the same
  netlist. The pattern is recorded in `tests/parity/baseline/extract-known.json`.

On the device defaults, KLayout's deck reports `m1.6` on 8 devices,
`via2.1a_b` on 3, `m5.4`, `rpm.1a` and `urpm.1a` on 2 each, and
`MR_tunm.CON.1`, `dnwell.2` and `MR_li.WID.4` on one each. Magic's
`drc(full)` reports `met1.6` on the same 8 devices, `rpm.1` on 4 high-poly
resistors, `nwell.5a, 7` on 3 devices, `met5.4`, `licon.5a` and
`P+ poly.1a` on 2 each, nine rule IDs on `npn_11v0_W1p00L1p00`, and
`licon.11`, `varac.5`, `nwell.8` and `li.7` on one device each
(`special_sonosfet_star`, `cap_var_lvt`, `pfet_g5v0d16v0` and
`res_generic_l1`). The full list per device is in `drc-defaults.json`.
These come from Magic's own output, since both paths give the same rule
sets.

To check that the harness catches a broken plugin, one run used a copy of the
package whose importer dropped layer 67/44 and moved every label 5 nm. The
quick sweep then failed 56 of 60 points (geometry 47, texts 51) and exited 1.
Another used a copy whose `format()` stripped whitespace from coverage
strings: on `res_generic_po`, `cap_mim_m3_1` and `diode_pw2nd_05v5` the sweep
failed the 6 whitespace points of 113 (request, geometry and checked values)
and exited 1.

### CI

`.github/workflows/parity.yml` pulls the image by digest and runs
`scripts/parity.sh --quick` on pull requests and the full sweep on a weekly
schedule and on manual runs. The repository has no remote, so the workflow
has never run. GitHub lists 14 GB of disk for standard runners and the image
is 11.7 GB unpacked, so the workflow frees disk space first and prints `df`
before and after the pull; whether that is enough is unknown.

## Known limitations

- KLayout regenerates every variant from the installed Magic when it opens a
  file and doesn't ask first. The `kmp_created` warning, `audit --regen` and
  the versioned cache make a change visible; this version can't pin a Magic
  version.
- If Magic fails while a file is opening with the library registered, the
  failed variants get the error marker, and saving the file saves the marker
  in place of the device until the file is reopened with a working Magic.
- Every GUI, `-z` or `-zz` start pays about 0.23 s and a 72 MB Magic process,
  even in sessions that never place a sky130 device.
- Opening a large design runs Magic once per variant that isn't cached, about
  20 ms each.
- No pin shapes: Magic writes labels only. KLayout LVS of circuits built from
  these devices hasn't been tried.
- The child Magic is told to die with the KLayout thread that started it
  (`PR_SET_PDEATHSIG`); KLayout calls produce on its main thread. Linux only.
- A host layout whose database unit doesn't divide 5 nm rounds Magic's
  coordinates, and one of 5 nm rounds the 1 nm vendor coordinates of four
  fixed devices. `audit` reports both.
- The PCell copies Magic's output flat. For fixed devices Magic writes an
  array instance of the vendor cell, and the PCell holds every copy's shapes:
  a 60 × 60 `npn_05v5_W1p00L1p00` array is a 22 KB GDS from Magic and
  1,170,000 shapes in the PCell (1.8 s to place, 156 MB peak memory in plain
  Python). The flat geometry is the same, but Magic's DRC checks a
  hierarchical array differently: on `cap_vpp_11p5x11p7_m1m2_noshield` with
  `nx 2` and `deltax 0.0034`, where neighbouring copies overlap, Magic's
  `drc(full)` on Magic's own output reports "This layer can't abut or
  partially overlap between subcells", and on the PCell, or on Magic's
  output flattened, it reports nothing. KLayout's deck gives the same rule
  sets either way, and the harness flattens both sides, so it doesn't see
  this. Keeping the array would need PCell variants with child cells.
- A coverage string that is not a number draws the error marker, where Magic
  would reset it or draw nothing (see [Parameters](#parameters)).
- Another package that registers a library called `sky130_magic` would
  replace this one. The PDK's own library is called `skywater130`, so the
  names don't clash; loading both hasn't been tried.
- Not tried: the GUI itself, the Salt manager, KLayout's `.mag` reader,
  `ext2spice merge`, and KLayout's own LVS deck.

## Changes from the design

- The eight "[+/-](%)" coverage parameters are strings, not doubles (see
  [Parameters](#parameters)). The design typed them as floats.
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
  which gets nine rule IDs when checked alone. With one device per sheet, the
  sheet and the single runs agree on all 60 defaults.
- An empty GDS from Magic is reproduced instead of being replaced by the
  error marker.
- Coverage strings that are not numbers are refused before they reach
  Magic, because `sky130A.tcl` evaluates them with `expr`.
- The design said a cache entry is never checked again. The sidecar now
  records the SHA-256 of the stored GDS, and an entry whose GDS doesn't
  match is deleted and regenerated. Hashing the stored bytes once is
  unaffected by the timestamps that make two Magic writes differ.
- The stamps carry a digest of the generator code and the PDK besides the
  three version strings.
- `register()` also refuses when the running Magic lacks a device of the
  manifest, and an unwritable cache directory turns the disk cache off
  instead of stopping registration.
- The harness has two more checks per point (Magic's cell name and checked
  values from both paths must agree, and path B must send exactly the text
  path A gave Magic), a known-extraction list for the `g5v0d16v0` FETs, the
  manifest check, and a watchdog on path A. The entry point is
  `scripts/parity.sh`, as in the design.

## Licences and credits

The project's own licence hasn't been chosen yet, so there is no `LICENSE`
file. The shipped manifest is data extracted from `sky130A.tcl`, which has no
licence header. The design assumes that open_pdks' licence applies to it;
nobody has checked that licence yet. The harness runs the PDK's KLayout DRC deck
(`sky130A_mr.drc`, GPLv3 according to its header) from the PDK install and
doesn't copy it.

The devices themselves are Magic's: the generators in `sky130A.tcl` (by Tim
Edwards, according to its header) and Magic's `toolkit.tcl`, from open_pdks
and Magic.

Two earlier projects were read for their structure and licences, and no code
was copied from either:

- [efabless/sky130_klayout_pdk](https://github.com/efabless/sky130_klayout_pdk),
  Apache-2.0, with Python PCells by Mabrains LLC and Efabless; the same PCell
  code ships in the PDK as the `skywater130` library.
- [laurentc2/SKY130_for_KLayout](https://github.com/laurentc2/SKY130_for_KLayout),
  BSD-2-Clause, a technology, DRC and LVS setup with no PCells.
