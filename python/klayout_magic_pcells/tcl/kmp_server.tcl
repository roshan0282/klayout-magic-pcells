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
}

fconfigure stdout -buffering line
catch {crashbackups stop}
package require json

load $::kmp::top -silent
set ::kmp::base_cells [cellname list allcells]

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
    if {[info commands ::sky130::${dev}_draw] eq "" ||
        [info commands ::sky130::${dev}_defaults] eq ""} {
        error "unknown device \"$dev\""
    }
}

# sky130A.tcl evaluates some parameter values with an unbraced expr (for
# example "expr abs($viagb)"), which substitutes [commands] and $variables
# inside the value.  The Python side only sends numbers; this refuses any
# value that could substitute, whoever sent it.
proc ::kmp::require_safe_params {params} {
    dict for {k v} $params {
        if {[regexp {[][$\\]} $v]} {
            error "parameter $k: the value contains \[, \], \$ or a backslash, which sky130A.tcl would substitute; refused"
        }
    }
}

# Cells that a request left behind, other than the cells that existed at start
# and the vendor cells that fixed devices load from libs.ref (those stay loaded
# and are reused).
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

proc ::kmp::op_versions {r} {
    set kv [::kmp::version_info]
    dict set kv protocol $::kmp::protocol
    if {[dict exists $r procs_out]} {
        dict set kv procs_lines [::kmp::dump_procs [dict get $r procs_out]]
    }
    if {[dict exists $r defaults_out]} {
        dict set kv devices [::kmp::dump_defaults [dict get $r defaults_out]]
    }
    return [dict create kv $kv params {}]
}

proc ::kmp::op_check {r} {
    set dev [dict get $r device]
    ::kmp::require_device $dev
    set params [dict get $r params]
    ::kmp::require_safe_params $params
    set checked [sky130::${dev}_check [magic::gencell_defaults $dev sky130 $params]]
    return [dict create kv {} params $checked]
}

proc ::kmp::op_generate {r} {
    set dev [dict get $r device]
    ::kmp::require_device $dev
    set params [dict get $r params]
    ::kmp::require_safe_params $params
    set form [dict get $r form]
    set out [dict get $r out]
    if {$form ni {cell wrapper}} { error "unknown form \"$form\"" }

    set ::kmp::checked {}
    set inst ""
    set g ""
    set rc [catch {
        load $::kmp::top
        box 0 0 0 0
        # Always the merged defaults: an empty dict sends gencell_create down
        # its dialog branch.
        set inst [magic::gencell_create $dev sky130 [magic::gencell_defaults $dev sky130 $params]]
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
    # for the same parameters starts from an empty name.
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
    if {$rc} {
        set kv [dict create rc 1 error $err]
        set params {}
    } else {
        set kv [dict merge [dict create rc 0] [dict get $res kv]]
        set params [dict get $res params]
    }
    dict set kv log $::kmp::log
    dict set kv us [lindex $t 0]
    ::kmp::emit $id $kv $params
    ::kmp::begin_request
}

::kmp::real_puts "KMP_READY $::kmp::protocol"
flush stdout
