// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_audio_fir_equalizer (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               s_valid,
    output logic               s_ready,
    input  logic signed [15:0] s_data,
    output logic               m_valid,
    input  logic               m_ready,
    output logic signed [19:0] m_data
);
    logic signed [15:0] history [0:3];
    logic signed [19:0] convolution;
    integer index;

    assign s_ready = !m_valid || m_ready;
    always_comb begin
        convolution =
            $signed(s_data)    * 20'sd1 +
            $signed(history[0]) * 20'sd2 +
            $signed(history[1]) * 20'sd3 +
            $signed(history[2]) * 20'sd2 +
            $signed(history[3]) * 20'sd1;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            m_valid <= 1'b0;
            m_data  <= '0;
            for (index = 0; index < 4; index = index + 1)
                history[index] <= '0;
        end else if (s_ready) begin
            m_valid <= s_valid;
            if (s_valid) begin
                m_data <= convolution;
                for (index = 3; index > 0; index = index - 1)
                    history[index] <= history[index-1];
                history[0] <= s_data;
            end
        end
    end
endmodule
