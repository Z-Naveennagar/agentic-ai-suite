// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_interrupt_aggregator (
    input  logic       clk,
    input  logic       rst_n,
    input  logic [7:0] sources,
    input  logic [7:0] mask,
    input  logic [7:0] clear,
    output logic [7:0] pending,
    output logic       irq,
    output logic       priority_valid,
    output logic [2:0] priority_index
);
    logic [7:0] active;
    integer index;

    assign active = pending & mask;
    assign irq = |active;

    always_comb begin
        priority_valid = 1'b0;
        priority_index = 3'd0;
        for (index = 0; index < 8; index = index + 1) begin
            if (!priority_valid && active[index]) begin
                priority_valid = 1'b1;
                priority_index = index[2:0];
            end
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n)
            pending <= 8'd0;
        else
            pending <= (pending | sources) & ~clear;
    end
endmodule
