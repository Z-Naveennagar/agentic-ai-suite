// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_motion_detector (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       s_valid,
    output logic       s_ready,
    input  logic [7:0] s_current,
    input  logic [7:0] s_reference,
    input  logic [7:0] s_threshold,
    input  logic       s_user,
    input  logic       s_last,
    output logic       m_valid,
    input  logic       m_ready,
    output logic [7:0] m_difference,
    output logic       m_motion,
    output logic       m_user,
    output logic       m_last
);
    logic [7:0] difference;

    always_comb begin
        if (s_current >= s_reference)
            difference = s_current - s_reference;
        else
            difference = s_reference - s_current;
    end

    assign s_ready = !m_valid || m_ready;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            m_valid      <= 1'b0;
            m_difference <= 8'd0;
            m_motion     <= 1'b0;
            m_user       <= 1'b0;
            m_last       <= 1'b0;
        end else begin
            if (m_valid && m_ready)
                m_valid <= 1'b0;
            if (s_valid && s_ready) begin
                m_valid      <= 1'b1;
                m_difference <= difference;
                m_motion     <= (difference >= s_threshold);
                m_user       <= s_user;
                m_last       <= s_last;
            end
        end
    end
endmodule
