# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

set_property PACKAGE_PIN W5 [get_ports clk]
set_property IOSTANDARD LVCMOS33 [get_ports clk]
create_clock -name clk -period 10.000 [get_ports clk]

set_property PACKAGE_PIN V17 [get_ports rst]
set_property PACKAGE_PIN U16 [get_ports pass_o]
set_property PACKAGE_PIN E19 [get_ports fail_o]
set_property IOSTANDARD LVCMOS33 [get_ports {rst pass_o fail_o}]
