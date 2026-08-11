// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_async_fifo (
    input  logic        wr_clk,
    input  logic        wr_rst,
    input  logic        wr_en,
    input  logic [31:0] wr_data,
    output logic        full,
    input  logic        rd_clk,
    input  logic        rd_rst,
    input  logic        rd_en,
    output logic [31:0] rd_data,
    output logic        empty
);

  localparam int ADDR_WIDTH = 4;
  localparam int PTR_WIDTH = ADDR_WIDTH + 1;

  logic [31:0] memory [0:15];
  logic [PTR_WIDTH-1:0] wr_bin, wr_gray, rd_bin, rd_gray;
  logic [PTR_WIDTH-1:0] wr_bin_next, wr_gray_next;
  logic [PTR_WIDTH-1:0] rd_bin_next, rd_gray_next;
  (* ASYNC_REG = "TRUE" *) logic [PTR_WIDTH-1:0] rd_gray_wr1, rd_gray_wr2;
  (* ASYNC_REG = "TRUE" *) logic [PTR_WIDTH-1:0] wr_gray_rd1, wr_gray_rd2;

  always_comb begin
    wr_bin_next = wr_bin;
    if (wr_en && !full)
      wr_bin_next = wr_bin + {{(PTR_WIDTH-1){1'b0}}, 1'b1};
    wr_gray_next = (wr_bin_next >> 1) ^ wr_bin_next;
    rd_bin_next = rd_bin;
    if (rd_en && !empty)
      rd_bin_next = rd_bin + {{(PTR_WIDTH-1){1'b0}}, 1'b1};
    rd_gray_next = (rd_bin_next >> 1) ^ rd_bin_next;
  end

  always_ff @(posedge wr_clk) begin
    if (wr_rst) begin
      wr_bin <= '0;
      wr_gray <= '0;
      rd_gray_wr1 <= '0;
      rd_gray_wr2 <= '0;
      full <= 1'b0;
    end else begin
      rd_gray_wr1 <= rd_gray;
      rd_gray_wr2 <= rd_gray_wr1;
      if (wr_en && !full)
        memory[wr_bin[ADDR_WIDTH-1:0]] <= wr_data;
      wr_bin <= wr_bin_next;
      wr_gray <= wr_gray_next;
      full <= (wr_gray_next ==
               {~rd_gray_wr2[PTR_WIDTH-1:PTR_WIDTH-2],
                 rd_gray_wr2[PTR_WIDTH-3:0]});
    end
  end

  always_ff @(posedge rd_clk) begin
    if (rd_rst) begin
      rd_bin <= '0;
      rd_gray <= '0;
      wr_gray_rd1 <= '0;
      wr_gray_rd2 <= '0;
      rd_data <= '0;
      empty <= 1'b1;
    end else begin
      wr_gray_rd1 <= wr_gray;
      wr_gray_rd2 <= wr_gray_rd1;
      if (rd_en && !empty)
        rd_data <= memory[rd_bin[ADDR_WIDTH-1:0]];
      rd_bin <= rd_bin_next;
      rd_gray <= rd_gray_next;
      empty <= (rd_gray_next == wr_gray_rd2);
    end
  end

endmodule
