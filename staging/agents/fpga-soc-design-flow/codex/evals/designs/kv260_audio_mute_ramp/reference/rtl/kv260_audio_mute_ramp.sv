// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_audio_mute_ramp #(
    parameter integer RAMP_STEPS = 8
) (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               mute,
    input  logic               s_valid,
    output logic               s_ready,
    input  logic signed [15:0] s_data,
    output logic               m_valid,
    input  logic               m_ready,
    output logic signed [15:0] m_data,
    output logic        [3:0]  gain_step
);
    localparam logic [3:0] RAMP_STEPS_W = 4'(RAMP_STEPS);

    logic [3:0] next_gain;
    logic signed [20:0] scaled;

    assign s_ready = !m_valid || m_ready;

    always_comb begin
        if (mute)
            next_gain = (gain_step == 0) ? 4'd0 : gain_step - 4'd1;
        else
            next_gain = (gain_step >= RAMP_STEPS_W) ?
                RAMP_STEPS_W : gain_step + 4'd1;
        scaled = $signed(s_data) * $signed({1'b0, next_gain});
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            gain_step <= RAMP_STEPS_W;
            m_valid   <= 1'b0;
            m_data    <= '0;
        end else if (s_ready) begin
            m_valid <= s_valid;
            if (s_valid) begin
                gain_step <= next_gain;
                m_data    <= scaled[18:3];
            end
        end
    end
endmodule
