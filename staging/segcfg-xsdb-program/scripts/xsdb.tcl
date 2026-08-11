# Program PDIs
connect

#Mandatory pre-requisites for VnX board
ta 1
rst -type por
mwr -force 0xF1260200 0x0100
mwr -force 0xF1110004 0x0
target -set -filter {name =~ "PMC*"}
rst -system
after 200



# Do write and Read tests
proc wr_rd_test {seed addr_cnt} {
  puts "INFO: Performing DDR Simple Write and Read test Seed = [format %x $seed]"
#  set addr_list {}
  set addr 0x0
  #lappend addr_list 0xA00000000
#  lappend addr_list 0x58000000000
  #lappend addr_list 0x68000000000
  set data $seed
  # write
  for {set a 0} {$a < $addr_cnt} {incr a} {
    puts "INFO: Writing into address [format %x $addr] -> Data [format %x $data]"
    mwr -force $addr $data
    set data [expr $data + 0x00000001]
    set addr [expr $addr + 0x00000004]
  }
  #read
  set data $seed  
  set addr 0x0
  for {set a 0} {$a < $addr_cnt} {incr a} {
    set rdata [mrd -force -value $addr]

    if {$rdata != $data} {
      puts "ERROR: Read data mismatch error for addr [format %x $addr]"
    } else {
      puts "INFO: Reading from address [format %x $addr] -> Data [format %x $rdata], OK"
    }

    set data [expr $data + 0x00000001]
    set addr [expr $addr + 0x00000004]
  }
  puts "INFO: Simple DDR Write and Read Passed Seed = [format %x $seed]"
}

# goto_pmc: re-anchor at device root before PMC filter.
# Required when switching from a CPU target (ta 20 / ta 31) back to PMC for PLD reload.
# Calling target-set-filter directly from a CPU context fails on the 3rd+ PLD load
# with PLM Error 0x2101/0x36 (CDO processing error).
proc goto_pmc {} {
  ta 1
  after 500
  target -set -filter {name =~ "PMC*"}
  after 1000
}

puts "INFO: Loading boot.pdi"
dev p ./ksb_ps_mb_ddr/ksb_ps_mb_ddr.runs/impl_1/ksb_ps_mb_ddr_wrapper_boot.pdi

# Test1
puts "INFO: Testing Cortex"
ta 20
#rst -proc
wr_rd_test 0x11223344 10

puts "INFO: Loading pld.pdi (1/3)"
goto_pmc
dev p ./ksb_ps_mb_ddr/ksb_ps_mb_ddr.runs/impl_1/ksb_ps_mb_ddr_wrapper_pld.pdi

puts "INFO: Loading pld.pdi (2/3)"
goto_pmc
dev p ./ksb_ps_mb_ddr/ksb_ps_mb_ddr.runs/impl_1/ksb_ps_mb_ddr_wrapper_pld.pdi
# Test2
puts "INFO: Testing Cortex"
ta 20
#rst -proc
wr_rd_test 0x11223345 10


#Test 3
puts "INFO: Testing Microblaze"
ta 31
rst -proc
wr_rd_test 0x1122AAAA 10

# Test 4
puts "INFO: Reloading pld.pdi (3/3)"
goto_pmc
dev p ./ksb_ps_mb_ddr/ksb_ps_mb_ddr.runs/impl_1/ksb_ps_mb_ddr_wrapper_pld.pdi
puts "INFO: Testing Cortex"
ta 20
#rst -proc
wr_rd_test 0x11223346 10

#Test 5
puts "INFO: Testing Microblaze"
ta 31
rst -proc
wr_rd_test 0x1122AAAA 10


puts "INFO: Test is done:)"
