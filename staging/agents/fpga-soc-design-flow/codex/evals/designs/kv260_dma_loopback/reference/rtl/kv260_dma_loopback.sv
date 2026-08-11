// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_dma_loopback #(
    parameter logic [31:0] XOR_MASK = 32'hA5A55A5A
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic [31:0] s_axis_tdata,
    input  logic [3:0]  s_axis_tkeep,
    input  logic        s_axis_tlast,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic [31:0] m_axis_tdata,
    output logic [3:0]  m_axis_tkeep,
    output logic        m_axis_tlast
);

  assign s_axis_tready = !m_axis_tvalid || m_axis_tready;

  always_ff @(posedge clk) begin
    if (rst) begin
      m_axis_tvalid <= 1'b0;
      m_axis_tdata <= '0;
      m_axis_tkeep <= '0;
      m_axis_tlast <= 1'b0;
    end else if (s_axis_tready) begin
      m_axis_tvalid <= s_axis_tvalid;
      if (s_axis_tvalid) begin
        m_axis_tdata <= s_axis_tdata ^ XOR_MASK;
        m_axis_tkeep <= s_axis_tkeep;
        m_axis_tlast <= s_axis_tlast;
      end
    end
  end

endmodule
