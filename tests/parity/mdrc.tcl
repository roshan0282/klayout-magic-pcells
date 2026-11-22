# Magic DRC on a GDS file, for the parity harness.
#
#   KMP_GDS=sheet.gds KMP_TOP=SHEET KMP_OUT=result.tsv \
#     magic -dnull -noconsole -rcfile <pdk>.magicrc mdrc.tcl
#
# Writes one line per error box: "<message>\t<l> <b> <r> <t>" in um, in the
# top cell's coordinates. "drc catchup" is needed in batch: without it Magic
# reports no errors at all. Works for every PDK: the rcfile picks the rules.
catch {crashbackups stop}
drc off
gds read $::env(KMP_GDS)
load $::env(KMP_TOP)
select top cell
# Check a margin around the cell too: an error area that lies outside the
# cell's bounding box (the far side of a metal5 square narrower than the
# width rule) is clipped to the checked box, so a lone device would lose it.
box grow c 10um
drc euclidean on
drc style drc(full)
drc check
drc catchup
set scale [cif scale out]
set fh [open $::env(KMP_OUT) w]
set n 0
foreach {why boxes} [drc listall why] {
    foreach b $boxes {
        set um {}
        foreach v $b { lappend um [expr {$v * $scale}] }
        puts $fh "[string map {\t { } \n { }} $why]\t$um"
        incr n
    }
}
close $fh
puts stdout "MDRC_DONE $n"
flush stdout
quit -noprompt
