# Magic resistance extraction of one net, for gate_resistance.py.
#
#   KMP_GDS=hw.gds KMP_TOP=HW_FET KMP_NET=G KMP_OUT=<dir> \
#     magic -dnull -noconsole -rcfile sky130A.magicrc extresist.tcl
#
# Writes <dir>/<top>_res.spice. Labels become ports so that the gate net,
# which has no source/drain on it, has a driver; extresist skips a net
# without one.
catch {crashbackups stop}
drc off
gds read $::env(KMP_GDS)
load $::env(KMP_TOP)
select top cell
port makeall
cd $::env(KMP_OUT)
extract do resistance
extract all
ext2sim labels on
ext2sim
extresist threshold 0
extresist mindelay 0
extresist minres 1
extresist include $::env(KMP_NET)
extresist simplify off
extresist all
ext2spice lvs
ext2spice extresist on
ext2spice cthresh infinite
ext2spice -o $::env(KMP_TOP)_res.spice
puts stdout "EXTRESIST_DONE"
flush stdout
quit -noprompt
