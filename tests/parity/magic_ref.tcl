# Path A of the parity sweep: Magic alone, through magic::gencell.
#
#   KMP_SWEEP=sweep.json KMP_OUT=<dir> [KMP_START=<n>] \
#     magic -dnull -noconsole -rcfile <pdk>.magicrc magic_ref.tcl
#
# KMP_START skips the first n points and appends to index.jsonl (run_sweep.py
# restarts Magic after a point that crashed it or hung).
#
# Uses none of the plugin's Tcl or Python. For every point it calls Magic's
# documented non-interactive entry point, magic::gencell, which merges the
# defaults and runs _check once (through gencell_create), then writes:
#   - drawn devices: the device cell alone;
#   - fixed (nocell) devices: the ref_<id> cell holding the arrayed vendor cell.
# One JSON line per point goes to <dir>/index.jsonl.

package require json
catch {crashbackups stop}

set ::ref_log ""
set ::ref_checked {}
# A generator that prints the same message 10000 times in one point is in an
# endless loop (sky130::mos_check with w and l both above 28 um); the point is
# recorded as a Magic error instead of hanging the sweep.
set ::ref_counts {}
set ::ref_abort ""
rename ::puts ::ref_real_puts
proc ::puts {args} {
    set a $args
    set nonl 0
    if {[lindex $a 0] eq "-nonewline"} { set nonl 1; set a [lrange $a 1 end] }
    if {[llength $a] == 2 && [lindex $a 0] eq "stderr"} {
        if {$::ref_abort ne ""} { error $::ref_abort }
        set msg [lindex $a 1]
        dict incr ::ref_counts $msg
        if {[dict get $::ref_counts $msg] > 10000} {
            set ::ref_abort "endless loop: Magic printed \"[string trim $msg]\" 10000 times"
            error $::ref_abort
        }
        if {[dict get $::ref_counts $msg] <= 20} {
            append ::ref_log $msg
            if {!$nonl} { append ::ref_log "\n" }
        }
        return
    }
    uplevel 1 [list ::ref_real_puts {*}$args]
}
# The checked dict, as gencell_create hands it to gencell_setparams.
proc ::ref_on_setparams {cmd op} { set ::ref_checked [lindex $cmd 1] }
trace add execution ::magic::gencell_setparams enter ::ref_on_setparams

proc ::ref_js {s} {
    set s [string map [list \\ \\\\ \" \\\" \n \\n \r \\r \t \\t] $s]
    regsub -all {[\x00-\x1f]} $s {} s
    return "\"$s\""
}
proc ::ref_jobj {d} {
    set items {}
    dict for {k v} $d { lappend items "[::ref_js $k]:[::ref_js $v]" }
    return "\{[join $items ,]\}"
}

set fh [open $::env(KMP_SWEEP) r]
fconfigure $fh -encoding utf-8
set sweep [json::json2dict [read $fh]]
close $fh
set out $::env(KMP_OUT)
file mkdir $out
set start 0
if {[info exists ::env(KMP_START)]} { set start $::env(KMP_START) }
set ix [open [file join $out index.jsonl] [expr {$start > 0 ? "a" : "w"}]]
fconfigure $ix -encoding utf-8 -translation lf

set n 0
foreach pt [lrange [dict get $sweep points] $start end] {
    set id [dict get $pt id]
    set dev [dict get $pt device]
    set req [dict get $pt request]
    set nocell [dict exists [sky130::${dev}_defaults] nocell]
    set ::ref_log ""
    set ::ref_checked {}
    set ::ref_counts {}
    set ::ref_abort ""
    set g ""
    set top ""
    set gds [file join $out $id.gds]
    set rc [catch {
        load ref_$id -silent
        box 0 0 0 0
        magic::gencell sky130::$dev X {*}$req
        set g [instance list celldef X]
        if {$g eq ""} { error "magic::gencell placed no instance" }
        if {$nocell} {
            set top ref_$id
        } else {
            set top $g
            load $g
        }
        if {$::ref_abort ne ""} { error $::ref_abort }
        gds write $gds
    } err]
    if {$::ref_abort ne ""} { set rc 1; set err $::ref_abort }
    set ::ref_abort ""
    catch {load ref_$id}
    catch {select cell X; delete}
    if {!$nocell && $g ne ""} { catch {cellname delete $g -noprompt} }
    # Drop the empty wrapper too, so thousands of points don't pile up cells.
    catch {load ref_base -silent; cellname delete ref_$id -noprompt}
    ::ref_real_puts $ix "\{\"id\":[::ref_js $id],\"device\":[::ref_js $dev],\"rc\":$rc,\"top\":[::ref_js $top],\"magic_cell\":[::ref_js $g],\"log\":[::ref_js $::ref_log],\"error\":[::ref_js [expr {$rc ? $err : {}}]],\"checked\":[::ref_jobj $::ref_checked]\}"
    flush $ix
    incr n
}
close $ix
::ref_real_puts "REF_DONE $n"
flush stdout
quit -noprompt
