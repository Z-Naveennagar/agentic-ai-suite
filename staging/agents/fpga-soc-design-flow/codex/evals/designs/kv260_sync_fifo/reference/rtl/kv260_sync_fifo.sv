// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_sync_fifo #(
    parameter int unsigned DATA_WIDTH = 32,
    parameter int unsigned DEPTH = 16
) (
    input  logic                  clk,
    input  logic                  resetn,
    input  logic                  wr_en,
    input  logic [DATA_WIDTH-1:0] wr_data,
    input  logic                  rd_en,
    output logic [DATA_WIDTH-1:0] rd_data,
    output logic                  full,
    output logic                  empty,
    output logic [$clog2(DEPTH):0] level
);
    localparam int ADDR_WIDTH = $clog2(DEPTH);
    localparam int LEVEL_WIDTH = $clog2(DEPTH) + 1;
    logic [DATA_WIDTH-1:0] memory [0:DEPTH-1];
    logic [ADDR_WIDTH-1:0] wr_ptr, rd_ptr;
    logic push, pop;

    assign full  = (level == LEVEL_WIDTH'(DEPTH));
    assign empty = (level == 0);
    assign push  = wr_en && !full;
    assign pop   = rd_en && !empty;

    always_ff @(posedge clk) begin
        if (!resetn) begin
            wr_ptr  <= '0;
            rd_ptr  <= '0;
            rd_data <= '0;
            level   <= '0;
        end else begin
            if (push) begin
                memory[wr_ptr] <= wr_data;
                wr_ptr <= wr_ptr + 1'b1;
            end
            if (pop) begin
                rd_data <= memory[rd_ptr];
                rd_ptr <= rd_ptr + 1'b1;
            end
            case ({push, pop})
                2'b10: level <= level + 1'b1;
                2'b01: level <= level - 1'b1;
                default: level <= level;
            endcase
        end
    end
endmodule
