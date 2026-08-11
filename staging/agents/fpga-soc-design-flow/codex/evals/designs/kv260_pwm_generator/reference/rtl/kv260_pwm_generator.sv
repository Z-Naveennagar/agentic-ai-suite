// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_pwm_generator (
    input  logic        clk,
    input  logic        resetn,
    input  logic [31:0] period_i,
    input  logic [31:0] duty_i,
    output logic        pwm_o
);
    logic [31:0] phase;

    always_ff @(posedge clk) begin
        if (!resetn) begin
            phase <= 32'd0;
        end else if ((period_i == 0) || (phase >= period_i - 1'b1)) begin
            phase <= 32'd0;
        end else begin
            phase <= phase + 1'b1;
        end
    end

    always_comb begin
        if ((period_i == 0) || (duty_i == 0))
            pwm_o = 1'b0;
        else if (duty_i >= period_i)
            pwm_o = 1'b1;
        else
            pwm_o = (phase < duty_i);
    end
endmodule
