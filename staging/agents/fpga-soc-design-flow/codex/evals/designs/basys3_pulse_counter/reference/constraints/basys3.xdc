# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

set_property PACKAGE_PIN W5 [get_ports clk]
set_property IOSTANDARD LVCMOS33 [get_ports clk]
create_clock -name clk -period 10.000 [get_ports clk]

set_property PACKAGE_PIN V17 [get_ports rst]
set_property PACKAGE_PIN V16 [get_ports event_i]
set_property PACKAGE_PIN W16 [get_ports clear_i]
set_property IOSTANDARD LVCMOS33 [get_ports {rst event_i clear_i}]

set_property PACKAGE_PIN U16 [get_ports {count_o[0]}]
set_property PACKAGE_PIN E19 [get_ports {count_o[1]}]
set_property PACKAGE_PIN U19 [get_ports {count_o[2]}]
set_property PACKAGE_PIN V19 [get_ports {count_o[3]}]
set_property PACKAGE_PIN W18 [get_ports {count_o[4]}]
set_property PACKAGE_PIN U15 [get_ports {count_o[5]}]
set_property PACKAGE_PIN U14 [get_ports {count_o[6]}]
set_property PACKAGE_PIN V14 [get_ports {count_o[7]}]
set_property PACKAGE_PIN V13 [get_ports overflow_o]
set_property IOSTANDARD LVCMOS33 [get_ports {count_o[*] overflow_o}]
