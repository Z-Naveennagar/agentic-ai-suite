// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_audio_tone_generator (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               enable,
    input  logic        [31:0] phase_increment,
    input  logic signed [15:0] amplitude,
    output logic               m_valid,
    input  logic               m_ready,
    output logic signed [15:0] m_data
);
    logic [31:0] phase_q;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            phase_q <= '0;
            m_valid <= 1'b0;
            m_data  <= '0;
        end else if (!enable) begin
            phase_q <= '0;
            m_valid <= 1'b0;
            m_data  <= '0;
        end else if (!m_valid || m_ready) begin
            m_valid <= 1'b1;
            m_data  <= phase_q[31] ? -amplitude : amplitude;
            phase_q <= phase_q + phase_increment;
        end
    end
endmodule
