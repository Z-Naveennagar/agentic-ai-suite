// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_watchdog_irq (
    input  logic        clk,
    input  logic        resetn,
    input  logic        enable,
    input  logic        reload,
    input  logic        clear_expired,
    input  logic [31:0] timeout_cycles,
    output logic        irq_o,
    output logic        expired_sticky_o
);
    logic [31:0] countdown;
    logic armed;

    always_ff @(posedge clk) begin
        if (!resetn) begin
            countdown       <= 32'd0;
            armed           <= 1'b0;
            irq_o           <= 1'b0;
            expired_sticky_o <= 1'b0;
        end else begin
            irq_o <= 1'b0;
            if (clear_expired)
                expired_sticky_o <= 1'b0;
            if (reload) begin
                countdown <= timeout_cycles;
                armed <= (timeout_cycles != 0);
            end else if (enable && armed) begin
                if (countdown <= 1) begin
                    countdown <= 32'd0;
                    armed <= 1'b0;
                    irq_o <= 1'b1;
                    expired_sticky_o <= 1'b1;
                end else begin
                    countdown <= countdown - 1'b1;
                end
            end
        end
    end
endmodule
