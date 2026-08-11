// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_axis_packetizer #(
    parameter int WORDS_PER_PACKET = 8
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic [31:0] s_axis_tdata,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic [31:0] m_axis_tdata,
    output logic        m_axis_tlast
);

  localparam int COUNT_WIDTH = (WORDS_PER_PACKET <= 1) ? 1 : $clog2(WORDS_PER_PACKET);
  localparam logic [COUNT_WIDTH-1:0] LAST_WORD =
      COUNT_WIDTH'(WORDS_PER_PACKET-1);
  logic [COUNT_WIDTH-1:0] word_index;

  assign s_axis_tready = m_axis_tready;
  assign m_axis_tvalid = s_axis_tvalid;
  assign m_axis_tdata = s_axis_tdata;
  assign m_axis_tlast = (word_index == LAST_WORD);

  always_ff @(posedge clk) begin
    if (rst) begin
      word_index <= '0;
    end else if (s_axis_tvalid && s_axis_tready) begin
      if (word_index == LAST_WORD)
        word_index <= '0;
      else
        word_index <= word_index + 1'b1;
    end
  end

endmodule
