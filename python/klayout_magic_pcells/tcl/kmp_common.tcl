# Helpers shared by kmp_server.tcl and kmp_manifest.tcl.
#
# Nothing here redefines a proc in the ::magic or ::sky130 namespaces: the
# backend hashes the text of those procs (the "code" field of the cache key),
# and an override would put this file's code into that digest.  The checked
# parameter dict is captured with an execution trace instead.

namespace eval ::kmp {
    variable log ""
    variable capture_stdout 0
    variable stdout_buf ""
    variable checked {}
    # Runaway guard (see ::puts below): how often each stderr message was
    # printed in the current request, and the reason once a request is stopped.
    variable repeats {}
    variable abort ""
    variable max_repeat 10000
    variable log_repeat 20
}

# Call at the start of every request.
proc ::kmp::begin_request {} {
    set ::kmp::log ""
    set ::kmp::repeats {}
    set ::kmp::abort ""
}

proc ::kmp::hex {s} {
    return [binary encode hex [encoding convertto utf-8 $s]]
}

proc ::kmp::unhex {h} {
    return [encoding convertfrom utf-8 [binary decode hex $h]]
}

# Messages that Magic and the generators print with "puts stderr" go into
# ::kmp::log.  While ::kmp::capture_stdout is set, stdout text goes into
# ::kmp::stdout_buf (used to read the output of Magic's "version" command).
#
# Runaway guard: sky130::mos_check loops forever when a MOSFET or varactor has
# both w and l above 28 um (its tap-spacing loop sets w to 29 and tests the
# same condition again), printing the same two messages on every pass.  Once
# one message has been printed max_repeat times in a request, this puts
# raises an error and keeps raising on every later "puts stderr" of that
# request.  gencell_create catches the error from _check and prints it, so
# the second raise is what ends gencell_create before it draws anything.
# Only the first log_repeat copies of a message go into the log.
if {[info commands ::kmp::real_puts] eq ""} {
    rename ::puts ::kmp::real_puts
    proc ::puts {args} {
        set a $args
        set nonl 0
        if {[lindex $a 0] eq "-nonewline"} {
            set nonl 1
            set a [lrange $a 1 end]
        }
        if {[llength $a] == 2 && [lindex $a 0] eq "stderr"} {
            if {$::kmp::abort ne ""} {
                error $::kmp::abort
            }
            set msg [lindex $a 1]
            dict incr ::kmp::repeats $msg
            set n [dict get $::kmp::repeats $msg]
            if {$n > $::kmp::max_repeat} {
                set ::kmp::abort "stopped after Magic printed \"[string trim $msg]\" $::kmp::max_repeat times in one request: sky130A.tcl is in an endless loop for these values (Magic's own dialog hangs on them too)"
                error $::kmp::abort
            }
            if {$n <= $::kmp::log_repeat} {
                append ::kmp::log $msg
                if {!$nonl} {append ::kmp::log "\n"}
            }
            return
        }
        if {$::kmp::capture_stdout} {
            if {[llength $a] == 1 || ([llength $a] == 2 && [lindex $a 0] eq "stdout")} {
                append ::kmp::stdout_buf [lindex $a end]
                if {!$nonl} {append ::kmp::stdout_buf "\n"}
                return
            }
        }
        uplevel 1 [list ::kmp::real_puts {*}$args]
    }
}

# gencell_create passes the post-_check dict to gencell_setparams (toolkit.tcl,
# after the call to ${dev}_check).  In batch that proc returns at once because
# there is no dialog window; the trace records its argument.
proc ::kmp::on_setparams {cmd op} {
    set ::kmp::checked [lindex $cmd 1]
}
if {[lsearch -exact [trace info execution ::magic::gencell_setparams] {enter ::kmp::on_setparams}] < 0} {
    trace add execution ::magic::gencell_setparams enter ::kmp::on_setparams
}

# --- JSON output -----------------------------------------------------------

proc ::kmp::jstr {s} {
    set s [string map [list \\ \\\\ \" \\\" \n \\n \r \\r \t \\t \b \\b \f \\f] $s]
    if {[regexp {[\x00-\x1f]} $s]} {
        set out ""
        foreach ch [split $s ""] {
            scan $ch %c code
            if {$code < 32} {
                append out [format "\\u%04x" $code]
            } else {
                append out $ch
            }
        }
        set s $out
    }
    return "\"$s\""
}

# A Tcl dict as a JSON list of [key, value] string pairs (keeps Magic's order).
proc ::kmp::jpairs {d} {
    set items {}
    dict for {k v} $d {
        lappend items "\[[::kmp::jstr $k],[::kmp::jstr $v]\]"
    }
    return "\[[join $items ,]\]"
}

# A Tcl dict as a JSON object of strings.
proc ::kmp::jobj {d} {
    set items {}
    dict for {k v} $d {
        lappend items "[::kmp::jstr $k]:[::kmp::jstr $v]"
    }
    return "\{[join $items ,]\}"
}

proc ::kmp::jlist {l} {
    set items {}
    foreach v $l { lappend items [::kmp::jstr $v] }
    return "\[[join $items ,]\]"
}

proc ::kmp::write_file {path text} {
    set fh [open $path w]
    fconfigure $fh -encoding utf-8 -translation lf
    puts -nonewline $fh $text
    close $fh
}

# --- Introspection ----------------------------------------------------------

# Devices: every ::sky130::<dev>_draw that also has a <dev>_defaults proc.
proc ::kmp::devices {} {
    set out {}
    foreach d [lsort [info commands ::sky130::*_draw]] {
        if {[regexp {^::sky130::(.*)_draw$} $d -> dev]} {
            if {[info commands ::sky130::${dev}_defaults] ne ""} {
                lappend out $dev
            }
        }
    }
    return $out
}

# Helper _draw procs: a _draw proc with no _defaults (not a device).
proc ::kmp::helpers {} {
    set out {}
    foreach d [lsort [info commands ::sky130::*_draw]] {
        if {[regexp {^::sky130::(.*)_draw$} $d -> dev]} {
            if {[info commands ::sky130::${dev}_defaults] eq ""} {
                lappend out $dev
            }
        }
    }
    return $out
}

# Magic's "version" command prints "Version 8.3 revision 681. Compiled on ..."
# and returns nothing, so its output is captured.
proc ::kmp::magic_version_line {} {
    set ::kmp::stdout_buf ""
    set ::kmp::capture_stdout 1
    set rc [catch {version} err]
    set ::kmp::capture_stdout 0
    set line [string trim $::kmp::stdout_buf]
    set ::kmp::stdout_buf ""
    if {$rc} { return "" }
    return $line
}

proc ::kmp::version_info {} {
    set tv [tech version]
    set techfile ""
    catch {set techfile [tech filename]}
    set pdkpath ""
    if {[info exists ::PDKPATH]} { set pdkpath $::PDKPATH }
    return [dict create \
        magic_banner [::kmp::magic_version_line] \
        tech [lindex $tv 0] \
        tech_description [lindex $tv 1] \
        tech_name [tech name] \
        tech_file $techfile \
        tcl [info patchlevel] \
        pdkpath $pdkpath]
}

# Text of every proc in ::sky130 and ::magic, sorted by name, written to a
# file for hashing on the Python side.
proc ::kmp::dump_procs {path} {
    set out ""
    foreach ns {::sky130 ::magic} {
        foreach p [lsort [info procs ${ns}::*]] {
            set arglist {}
            foreach a [info args $p] {
                if {[info default $p $a def]} {
                    lappend arglist [list $a $def]
                } else {
                    lappend arglist $a
                }
            }
            append out "proc $p [list $arglist] [list [info body $p]]\n"
        }
    }
    ::kmp::write_file $path $out
    return [llength [split $out "\n"]]
}

# Defaults of every device as JSON: {"<dev>": [["k","v"], ...], ...}.
proc ::kmp::dump_defaults {path} {
    set items {}
    foreach dev [::kmp::devices] {
        lappend items "[::kmp::jstr $dev]:[::kmp::jpairs [sky130::${dev}_defaults]]"
    }
    ::kmp::write_file $path "\{[join $items ,]\}\n"
    return [llength $items]
}
