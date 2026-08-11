create_clock -name clk_a -period 5.000 [get_ports clk_a]
create_clock -name clk_b -period 8.000 [get_ports clk_b]

set_input_delay 1.000 -clock clk_a [get_ports {enable zeroize fault_inject[*] mem_addr[*] mem_we mem_wdata[*] s_axis_tvalid s_axis_tdata[*] s_axis_tkeep[*] s_axis_tlast s_axis_tuser m_axis_tready}]
set_output_delay 1.000 -clock clk_a [get_ports {s_axis_tready m_axis_tvalid m_axis_tdata[*] m_axis_tkeep[*] m_axis_tlast m_axis_tuser status[*]}]
set_output_delay 1.000 -clock clk_b [get_ports {link_status[*] link_status_valid}]

# XPM_CDC_SINGLE contributes its own scoped max-delay constraints. Do not override them with
# set_clock_groups or an overlapping false path.
