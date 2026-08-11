// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_stereo_mixer (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               s_valid,
    output logic               s_ready,
    input  logic signed [15:0] left_data,
    input  logic signed [15:0] right_data,
    output logic               m_valid,
    input  logic               m_ready,
    output logic signed [15:0] mono_data
);
    logic signed [16:0] sum;

    assign s_ready = !m_valid || m_ready;
    always_comb sum = $signed(left_data) + $signed(right_data);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            m_valid   <= 1'b0;
            mono_data <= '0;
        end else if (s_ready) begin
            m_valid <= s_valid;
            if (s_valid)
                mono_data <= sum[16:1];
        end
    end
endmodule
