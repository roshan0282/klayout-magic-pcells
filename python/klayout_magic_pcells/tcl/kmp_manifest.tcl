# Dump what tools/build_manifest.py needs to build the device manifest.
#
# Run as:  KMP_MANIFEST_OUT=<dir> magic -dnull -noconsole -rcfile <rc> kmp_manifest.tcl
#
# Writes into <dir>: versions.json, procs.txt, defaults.json, raw.json and one
# GDS per device under gds/ (generated with the defaults, through the same
# generate op the backend uses).

source [file join [file dirname [info script]] kmp_server.tcl]

set ::kmp::mout $::env(KMP_MANIFEST_OUT)
file mkdir [file join $::kmp::mout gds]

proc ::kmp::diffpairs {before after} {
    set out {}
    dict for {k v} $after {
        if {![dict exists $before $k]} {
            lappend out "\[[::kmp::jstr $k],null,[::kmp::jstr $v]\]"
        } elseif {[dict get $before $k] ne $v} {
            lappend out "\[[::kmp::jstr $k],[::kmp::jstr [dict get $before $k]],[::kmp::jstr $v]\]"
        }
    }
    dict for {k v} $before {
        if {![dict exists $after $k]} {
            lappend out "\[[::kmp::jstr $k],[::kmp::jstr $v],null\]"
        }
    }
    return "\[[join $out ,]\]"
}

proc ::kmp::run_check {dev params} {
    ::kmp::begin_request
    set merged [magic::gencell_defaults $dev sky130 $params]
    set err ""
    if {[catch {set checked [sky130::${dev}_check $merged]} err]} {
        set checked $merged
    } else {
        set err ""
    }
    return [list $merged $checked $::kmp::log $err]
}

# 1. Versions, proc text and defaults, before anything below stubs a proc.
set vi [::kmp::version_info]
::kmp::write_file [file join $::kmp::mout versions.json] "[::kmp::jobj $vi]\n"
::kmp::dump_procs [file join $::kmp::mout procs.txt]
::kmp::dump_defaults [file join $::kmp::mout defaults.json]

# 2. Dialog widgets, by running each _dialog against recording stubs.
set ::kmp::widgets {}
set ::kmp::stubbed {add_entry add_checkbox add_message add_selectlist add_selectindex add_dependency}
foreach p $::kmp::stubbed {
    if {[info commands ::magic::$p] ne ""} {
        rename ::magic::$p ::kmp::orig_$p
    }
}
proc ::magic::add_entry {pname ptext parameters} {
    lappend ::kmp::widgets [list entry $pname $ptext {}]
}
proc ::magic::add_checkbox {pname ptext parameters} {
    lappend ::kmp::widgets [list checkbox $pname $ptext {}]
}
proc ::magic::add_message {pname ptext parameters {color blue}} {
    lappend ::kmp::widgets [list message $pname $ptext {}]
}
proc ::magic::add_selectlist {pname ptext all_values parameters {itext ""}} {
    lappend ::kmp::widgets [list selectlist $pname $ptext $all_values]
}
proc ::magic::add_selectindex {pname ptext all_values parameters {ival 0}} {
    lappend ::kmp::widgets [list selectindex $pname $ptext $all_values]
}
proc ::magic::add_dependency {callback gencell_type library args} {
    lappend ::kmp::widgets [list dependency $callback $gencell_type $args]
}

set ::kmp::dialogs [dict create]
foreach dev [::kmp::devices] {
    set ::kmp::widgets {}
    set derr ""
    if {[info commands ::sky130::${dev}_dialog] ne ""} {
        if {[catch {sky130::${dev}_dialog [sky130::${dev}_defaults]} derr]} {
        } else {
            set derr ""
        }
    }
    dict set ::kmp::dialogs $dev [list $::kmp::widgets $derr]
}
foreach p $::kmp::stubbed {
    if {[info commands ::kmp::orig_$p] ne ""} {
        rename ::magic::$p ""
        rename ::kmp::orig_$p ::magic::$p
    }
}

# 3. Per device: _check on the defaults, probes, and one generation.
set devjs {}
foreach dev [::kmp::devices] {
    set defs [sky130::${dev}_defaults]
    lassign [dict get $::kmp::dialogs $dev] widgets derr
    set wjs {}
    foreach w $widgets {
        lassign $w kind pname ptext extra
        lappend wjs "\{\"kind\":[::kmp::jstr $kind],\"name\":[::kmp::jstr $pname],\"label\":[::kmp::jstr $ptext],\"extra\":[::kmp::jstr $extra]\}"
    }

    lassign [::kmp::run_check $dev {}] merged checked clog cerr
    set checkjs "\{\"changes\":[::kmp::diffpairs $merged $checked],\"messages\":[::kmp::jstr $clog],\"error\":[::kmp::jstr $cerr]\}"

    # Probes: each entry parameter set to 0, to 10000 and to 2.5.
    set probes {}
    foreach w $widgets {
        lassign $w kind pname ptext extra
        if {$kind ne "entry" || ![dict exists $defs $pname]} continue
        foreach val {0 10000 2.5} {
            lassign [::kmp::run_check $dev [list $pname $val]] m c plog perr
            set got [expr {[dict exists $c $pname] ? [dict get $c $pname] : ""}]
            lappend probes "\{\"param\":[::kmp::jstr $pname],\"value\":[::kmp::jstr $val],\"result\":[::kmp::jstr $got],\"messages\":[::kmp::jstr $plog],\"error\":[::kmp::jstr $perr]\}"
        }
    }

    set nocell [dict exists $defs nocell]
    set form [expr {$nocell ? "wrapper" : "cell"}]
    set gds [file join $::kmp::mout gds ${dev}.gds]
    ::kmp::begin_request
    set grc [catch {::kmp::op_generate [dict create device $dev params {} form $form out $gds]} gres]
    if {$grc} {
        set genjs "\{\"ok\":false,\"error\":[::kmp::jstr $gres],\"messages\":[::kmp::jstr $::kmp::log]\}"
    } else {
        set cell [dict get $gres kv cell]
        set genjs "\{\"ok\":true,\"cell\":[::kmp::jstr $cell],\"checked\":[::kmp::jpairs [dict get $gres params]],\"messages\":[::kmp::jstr $::kmp::log],\"gds\":[::kmp::jstr $gds]\}"
    }

    lappend devjs "\{\"name\":[::kmp::jstr $dev],\"has_check\":[llength [info commands ::sky130::${dev}_check]],\"has_convert\":[llength [info commands ::sky130::${dev}_convert]],\"has_dialog\":[llength [info commands ::sky130::${dev}_dialog]],\"draw_args\":[::kmp::jstr [info args ::sky130::${dev}_draw]],\"defaults\":[::kmp::jpairs $defs],\"widgets\":\[[join $wjs ,]\],\"dialog_error\":[::kmp::jstr $derr],\"check_on_defaults\":$checkjs,\"probes\":\[[join $probes ,]\],\"nocell\":[expr {$nocell ? "true" : "false"}],\"form\":[::kmp::jstr $form],\"defaults_run\":$genjs\}"
}

::kmp::write_file [file join $::kmp::mout raw.json] "\{\"devices\":\[\n[join $devjs ",\n"]\n\],\"helpers\":[::kmp::jlist [::kmp::helpers]]\}\n"
::kmp::real_puts "KMP_MANIFEST_DONE [llength $devjs]"
flush stdout
quit -noprompt
