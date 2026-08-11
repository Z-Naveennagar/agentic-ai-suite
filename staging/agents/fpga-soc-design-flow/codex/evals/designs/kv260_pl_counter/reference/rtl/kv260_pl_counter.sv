// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_pl_counter #(
    parameter int unsigned WIDTH = 32,
    parameter logic [WIDTH-1:0] TERMINAL_COUNT = 32'd15
) (
    input  logic                 clk,
    input  logic                 resetn,
    input  logic                 enable,
    input  logic                 clear,
    output logic [WIDTH-1:0]     count,
    output logic                 terminal_pulse
);
    always_ff @(posedge clk) begin
        if (!resetn) begin
            count          <= '0;
            terminal_pulse <= 1'b0;
        end else begin
            terminal_pulse <= 1'b0;
            if (clear) begin
                count <= '0;
            end else if (enable) begin
                if (count == TERMINAL_COUNT) begin
                    count          <= '0;
                    terminal_pulse <= 1'b1;
                end else begin
                    count <= count + 1'b1;
                end
            end
        end
    end
endmodule
