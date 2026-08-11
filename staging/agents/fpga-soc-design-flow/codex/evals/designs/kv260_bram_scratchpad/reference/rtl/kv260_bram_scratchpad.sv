// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_bram_scratchpad (
    input  logic        clk,
    input  logic        rst,
    input  logic        a_en,
    input  logic [3:0]  a_we,
    input  logic [7:0]  a_addr,
    input  logic [31:0] a_wdata,
    output logic [31:0] a_rdata,
    input  logic        b_en,
    input  logic [3:0]  b_we,
    input  logic [7:0]  b_addr,
    input  logic [31:0] b_wdata,
    output logic [31:0] b_rdata
);

  (* ram_style = "block" *) logic [31:0] memory [0:255];
  integer byte_index;

  always_ff @(posedge clk) begin
    if (rst) begin
      a_rdata <= '0;
      b_rdata <= '0;
    end else begin
      if (a_en) begin
        a_rdata <= memory[a_addr];
        for (byte_index = 0; byte_index < 4; byte_index = byte_index + 1)
          if (a_we[byte_index])
            memory[a_addr][byte_index*8 +: 8] <=
                a_wdata[byte_index*8 +: 8];
      end
      if (b_en) begin
        b_rdata <= memory[b_addr];
        for (byte_index = 0; byte_index < 4; byte_index = byte_index + 1)
          if (b_we[byte_index])
            memory[b_addr][byte_index*8 +: 8] <=
                b_wdata[byte_index*8 +: 8];
      end
    end
  end

endmodule
