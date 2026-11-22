# Request server for the klayout-magic-pcells backend.
#
# The backend starts "magic -dnull -noconsole -rcfile <pdk>.magicrc" with its
# stdin, stdout and stderr on pipes and sends "source kmp_server.tcl".  After
# that, every line it sends is one complete Tcl command:
#
#     kmp::req <id> <hex>
#
# where <hex> is the hex encoding of a UTF-8 JSON object such as
#     {"op":"generate","device":"sky130_fd_pr__nfet_01v8",
#      "params":{"w":"1.5","l":"0.5"},"form":"cell","out":"/path/x.gds"}
# The form is "cell" (a drawn device: its cell alone), "wrapper" (a fixed
# device: the cell holding the arrayed vendor cell) or "box" (a box-paint
# generator: the box set to w x h um with its lower-left corner at the
# origin, the generator called with no arguments, as Magic's menu calls it).
# No parameter value is ever part of the Tcl source of a request, so a value
# with an unbalanced brace cannot leave the session waiting for more input.
#
# Each reply is a block of lines on stdout:
#     KMP_BEGIN <id>
#     KMP_KV <id> <key> <hex of value>        (rc first, then the other keys)
#     KMP_PARAM <id> <hex of name> <hex of value>   (checked dict, in order)
#     KMP_END <id>
# Any other line on stdout is Magic talking and is ignored by the client.

source [file join [file dirname [info script]] kmp_common.tcl]

namespace eval ::kmp {
    variable protocol 1
    variable base_cells {}
    variable vendor_cells {}
    variable top kmp_top
    variable box_seq 0
}

fconfigure stdout -buffering line
catch {crashbackups stop}
package require json

load $::kmp::top -silent
set ::kmp::base_cells [cellname list allcells]
::kmp::record_state

proc ::kmp::emit {id kv params} {
    ::kmp::real_puts "KMP_BEGIN $id"
    if {[dict exists $kv rc]} {
        ::kmp::real_puts "KMP_KV $id rc [::kmp::hex [dict get $kv rc]]"
    }
    dict for {k v} $kv {
        if {$k eq "rc"} continue
        ::kmp::real_puts "KMP_KV $id $k [::kmp::hex $v]"
    }
    dict for {k v} $params {
        ::kmp::real_puts "KMP_PARAM $id [::kmp::hex $k] [::kmp::hex $v]"
    }
    ::kmp::real_puts "KMP_END $id"
    flush stdout
}

proc ::kmp::require_device {dev} {
    set ns $::kmp::ns
    if {[info commands ::${ns}::${dev}_draw] eq "" ||
        [info commands ::${ns}::${dev}_defaults] eq ""} {
        error "unknown device \"$dev\""
    }
}

proc ::kmp::require_boxpaint {name} {
    if {![::kmp::is_boxpaint $name]} {
        error "unknown box-paint generator \"$name\""
    }
}

# The PDKs' generator code evaluates some parameter values with an unbraced
# expr (for example "expr abs($viagb)" in sky130A.tcl), which substitutes
# [commands] and $variables inside the value.  The Python side only sends
# numbers and names from the dialog's choices; this refuses any value that
# could substitute, whoever sent it.
proc ::kmp::require_safe_params {params} {
    dict for {k v} $params {
        if {[regexp {[][$\\]} $v]} {
            error "parameter $k: the value contains \[, \], \$ or a backslash, which the PDK's generator code would substitute; refused"
        }
    }
}

# A box size, interpolated into "box values ...um": a plain decimal number.
proc ::kmp::require_size {k v} {
    if {![regexp {^[0-9]+(\.[0-9]*)?([eE][+-]?[0-9]+)?$} $v] && ![regexp {^\.[0-9]+([eE][+-]?[0-9]+)?$} $v]} {
        error "box size $k=\"$v\" is not a number"
    }
}

# Every cell below a cell, at any depth.
proc ::kmp::descendants {c} {
    set out {}
    set todo [list $c]
    while {[llength $todo]} {
        set todo [lassign $todo x]
        set kids {}
        catch {set kids [cellname list children $x]}
        foreach k $kids {
            if {[lsearch -exact $out $k] < 0} {
                lappend out $k
                lappend todo $k
            }
        }
    }
    return $out
}

# Cells that a request left behind, other than the cells that existed at start
# and the cells kept on purpose: the vendor cells that fixed devices load from
# libs.ref, and cells that a generator places inside its device and reuses
# (sg13g2::npn13g2_draw creates npn13g2_base once).  Kept cells stay loaded
# and are reused, as in one session of Magic.
proc ::kmp::leftover_cells {} {
    set out {}
    foreach c [cellname list allcells] {
        if {[lsearch -exact $::kmp::base_cells $c] >= 0} continue
        if {[dict exists $::kmp::vendor_cells $c]} continue
        lappend out $c
    }
    return $out
}

proc ::kmp::op_ping {r} {
    return [dict create kv [dict create protocol $::kmp::protocol] params {}]
}

# Where Magic finds a cell's .mag (the first match on its search path, as
# "getcell" resolves it) and the vendor GDS file that .mag names.  Fixed
# devices copy their geometry from that file, so the backend hashes both.
proc ::kmp::resolve_cell {c} {
    set mag ""
    foreach dir [path search] {
        set d $dir
        catch {set d [subst -nocommands -nobackslashes $dir]}
        set f [file join $d $c.mag]
        if {[file isfile $f]} { set mag [file normalize $f]; break }
    }
    set gds ""
    if {$mag ne ""} {
        set fh [open $mag r]
        set text [read $fh]
        close $fh
        if {[regexp {string GDS_FILE (\S+)} $text -> gds]} {
            set map {}
            if {[info exists ::PDKPATH]} { lappend map {$PDKPATH} $::PDKPATH {${PDKPATH}} $::PDKPATH }
            if {[info exists ::env(PDK_ROOT)]} { lappend map {$PDK_ROOT} $::env(PDK_ROOT) {${PDK_ROOT}} $::env(PDK_ROOT) }
            set gds [string map $map $gds]
            if {[file pathtype $gds] eq "relative"} { set gds [file join [file dirname $mag] $gds] }
        }
    }
    return [list $mag $gds]
}

proc ::kmp::op_versions {r} {
    set kv [::kmp::version_info]
    dict set kv protocol $::kmp::protocol
    if {[dict exists $r vendor_cells]} {
        set lines {}
        foreach c [dict get $r vendor_cells] {
            lassign [::kmp::resolve_cell $c] mag gds
            lappend lines "$c\t$mag\t$gds"
        }
        dict set kv vendor [join $lines "\n"]
    }
    if {[dict exists $r procs_out]} {
        dict set kv procs_lines [::kmp::dump_procs [dict get $r procs_out]]
    }
    if {[dict exists $r defaults_out]} {
        dict set kv devices [::kmp::dump_defaults [dict get $r defaults_out]]
    }
    return [dict create kv $kv params {}]
}

# _check once on the merged defaults; nothing is drawn.  A device without a
# _check proc (sg13g2 rm6, rm7), or whose _check raises (gf180mcu npolyf_s at
# w 0), gets what gencell_create would draw with: the merged values,
# unchecked, with the reason in the log.
proc ::kmp::op_check {r} {
    set dev [dict get $r device]
    set params [dict get $r params]
    ::kmp::require_safe_params $params
    if {[dict exists $r form] && [dict get $r form] eq "box"} {
        return [::kmp::gen_box $dev $params ""]
    }
    ::kmp::require_device $dev
    set ns $::kmp::ns
    set merged [magic::gencell_defaults $dev $ns $params]
    if {[info commands ::${ns}::${dev}_check] eq ""} {
        append ::kmp::log "$dev has no _check proc; Magic draws the values unchecked\n"
        return [dict create kv [dict create check none] params $merged]
    }
    if {[catch {set checked [::${ns}::${dev}_check $merged]} err]} {
        if {$::kmp::abort ne ""} { error $::kmp::abort }
        append ::kmp::log "_check failed: $err; Magic draws the values unchecked\n"
        return [dict create kv [dict create check failed check_error $err] params $merged]
    }
    return [dict create kv {} params $checked]
}

# Internal units as um, written without float noise: 1.005, not
# 1.0050000000000001.
proc ::kmp::um {n} {
    set v [string trimright [format %.6f [magic::i2u $n]] 0]
    if {[string index $v end] eq "."} { append v 0 }
    return $v
}

# A box-paint generator: a fresh cell, the box w x h um with its lower-left
# corner at the origin, the generator called with no arguments (as Magic's
# menu calls it), and, when out is not empty, the cell written to out.  The
# reply's params hold the box Magic used, in um, after it rounded the size
# to its internal grid; kv box holds it in internal units.
proc ::kmp::gen_box {name params out} {
    ::kmp::require_boxpaint $name
    foreach k {w h} {
        if {![dict exists $params $k]} { error "box-paint generator $name needs $k" }
        ::kmp::require_size $k [dict get $params $k]
    }
    set w [dict get $params w]
    set h [dict get $params h]
    set cell kmp_box_[incr ::kmp::box_seq]
    set bv {}
    set rc [catch {
        load $cell -silent
        box values 0um 0um ${w}um ${h}um
        set bv [box values]
        ::${::kmp::ns}::${name}_draw
        if {$out ne ""} {
            file delete -force $out
            gds write $out
            if {![file exists $out]} { error "gds write produced no file" }
        }
    } err opts]
    catch {load $::kmp::top}
    catch {cellname delete $cell -noprompt}
    catch {select clear}
    if {$rc} { return -options $opts $err }
    lassign $bv x1 y1 x2 y2
    set drawn [dict create w [::kmp::um [expr {$x2 - $x1}]] h [::kmp::um [expr {$y2 - $y1}]]]
    return [dict create kv [dict create cell "" box $bv] params $drawn]
}

proc ::kmp::op_generate {r} {
    set dev [dict get $r device]
    set params [dict get $r params]
    ::kmp::require_safe_params $params
    set form [dict get $r form]
    set out [dict get $r out]
    if {$form eq "box"} {
        return [::kmp::gen_box $dev $params $out]
    }
    ::kmp::require_device $dev
    if {$form ni {cell wrapper}} { error "unknown form \"$form\"" }
    set ns $::kmp::ns

    set ::kmp::checked {}
    set inst ""
    set g ""
    set rc [catch {
        load $::kmp::top
        box 0 0 0 0
        # Always the merged defaults: an empty dict sends gencell_create down
        # its dialog branch.
        set inst [magic::gencell_create $dev $ns [magic::gencell_defaults $dev $ns $params]]
        if {$inst eq ""} {
            error "gencell_create returned no instance (no box, or an exact copy of an existing cell)"
        }
        set g [instance list celldef $inst]
        if {$form eq "cell"} {
            load $g
        } else {
            load $::kmp::top
        }
        file delete -force $out
        gds write $out
        if {![file exists $out]} { error "gds write produced no file" }
    } err opts]

    # Clean up whatever exists, even after an error, so that the next request
    # for the same parameters starts from an empty name.  Cells below the
    # device are kept: a fixed device's vendor cell and its children, and
    # cells a generator places in its device and reuses (npn13g2_base).
    set kept {}
    if {$g ne ""} {
        foreach k [::kmp::descendants $g] {
            if {![dict exists $::kmp::vendor_cells $k]} { lappend kept $k }
            dict set ::kmp::vendor_cells $k 1
        }
    }
    catch {load $::kmp::top}
    if {$inst ne ""} {
        catch {select cell $inst; delete}
    }
    if {$g ne ""} {
        if {$form eq "cell"} {
            catch {cellname delete $g -noprompt}
        } else {
            dict set ::kmp::vendor_cells $g 1
        }
    }
    catch {select clear}
    if {$rc} {
        return -options $opts $err
    }
    set left [::kmp::leftover_cells]
    set kv [dict create cell $g]
    if {[llength $kept]} {
        dict set kv kept [join $kept " "]
    }
    if {[llength $left]} {
        dict set kv restart 1
        dict set kv leftover [join $left " "]
    }
    return [dict create kv $kv params $::kmp::checked]
}

proc ::kmp::req {id hex} {
    ::kmp::begin_request
    set res {}
    set t [time {
        set rc [catch {
            set r [json::json2dict [::kmp::unhex $hex]]
            set op [dict get $r op]
            if {[info commands ::kmp::op_$op] eq ""} { error "unknown op \"$op\"" }
            set res [::kmp::op_$op $r]
        } err]
    }]
    # A stopped request is an error even if something on the way swallowed it.
    if {$::kmp::abort ne ""} {
        set rc 1
        set err $::kmp::abort
    }
    set ::kmp::abort ""
    set restored [::kmp::restore_state]
    if {$rc} {
        set kv [dict create rc 1 error $err]
        set params {}
    } else {
        set kv [dict merge [dict create rc 0] [dict get $res kv]]
        set params [dict get $res params]
    }
    dict set kv log $::kmp::log
    dict set kv us [lindex $t 0]
    if {$restored ne ""} { dict set kv restored $restored }
    ::kmp::emit $id $kv $params
    ::kmp::begin_request
}

::kmp::real_puts "KMP_READY $::kmp::protocol"
flush stdout
