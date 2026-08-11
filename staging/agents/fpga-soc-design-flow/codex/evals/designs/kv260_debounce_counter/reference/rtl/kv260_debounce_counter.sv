// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_debounce_counter #(
    parameter int unsigned DEBOUNCE_CYCLES = 4
) (
    input  logic        clk,
    input  logic        resetn,
    input  logic        signal_i,
    output logic        debounced_o,
    output logic        rise_pulse_o,
    output logic [31:0] edge_count_o
);
    localparam int COUNT_WIDTH = (DEBOUNCE_CYCLES <= 1) ? 1 : $clog2(DEBOUNCE_CYCLES);
    logic sync_ff1, sync_ff2;
    logic [COUNT_WIDTH-1:0] stable_count;

    always_ff @(posedge clk) begin
        if (!resetn) begin
            sync_ff1    <= 1'b0;
            sync_ff2    <= 1'b0;
            debounced_o <= 1'b0;
            rise_pulse_o <= 1'b0;
            edge_count_o <= 32'd0;
            stable_count <= '0;
        end else begin
            sync_ff1 <= signal_i;
            sync_ff2 <= sync_ff1;
            rise_pulse_o <= 1'b0;
            if (sync_ff2 == debounced_o) begin
                stable_count <= '0;
            end else if ((DEBOUNCE_CYCLES <= 1) ||
                         (stable_count == COUNT_WIDTH'(DEBOUNCE_CYCLES - 1))) begin
                stable_count <= '0;
                debounced_o <= sync_ff2;
                if (sync_ff2) begin
                    rise_pulse_o <= 1'b1;
                    edge_count_o <= edge_count_o + 1'b1;
                end
            end else begin
                stable_count <= stable_count + 1'b1;
            end
        end
    end
endmodule
