puts "Opening Vivado hardware manager..."

if {[catch {open_hw_manager} result]} {
    puts "open_hw_manager failed: $result"
    exit 1
}

puts "Connecting to local hardware server..."

if {[catch {connect_hw_server -allow_non_jtag} result]} {
    puts "connect_hw_server failed: $result"
    exit 1
}

set targets [get_hw_targets *]
puts "Hardware targets found: $targets"

if {[llength $targets] == 0} {
    puts "No hardware targets were found."
    exit 2
}

foreach target $targets {
    puts "Trying target: $target"
    current_hw_target $target

    if {[catch {open_hw_target} result]} {
        puts "open_hw_target failed for $target: $result"
    } else {
        set devices [get_hw_devices *]
        puts "Hardware devices found on $target: $devices"
        close_hw_target
    }
}

exit 0
