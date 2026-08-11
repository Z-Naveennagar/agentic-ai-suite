// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_camera_audio_synchronizer (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        s_valid,
    output logic        s_ready,
    input  logic [15:0] s_camera_epoch,
    input  logic [15:0] s_audio_epoch,
    input  logic [63:0] s_camera_timestamp,
    input  logic [63:0] s_audio_timestamp,
    input  logic [31:0] s_tolerance,
    output logic        m_valid,
    input  logic        m_ready,
    output logic [15:0] m_epoch,
    output logic [64:0] m_skew,
    output logic        m_epoch_match,
    output logic        m_aligned
);
    logic [64:0] skew_value;
    logic [64:0] skew_magnitude;

    assign s_ready = !m_valid || m_ready;
    assign skew_value = {1'b0, s_camera_timestamp} -
                        {1'b0, s_audio_timestamp};
    assign skew_magnitude = (s_camera_timestamp >= s_audio_timestamp) ?
                            ({1'b0, s_camera_timestamp} -
                             {1'b0, s_audio_timestamp}) :
                            ({1'b0, s_audio_timestamp} -
                             {1'b0, s_camera_timestamp});

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            m_valid       <= 1'b0;
            m_epoch       <= 16'd0;
            m_skew        <= 65'd0;
            m_epoch_match <= 1'b0;
            m_aligned     <= 1'b0;
        end else begin
            if (m_valid && m_ready)
                m_valid <= 1'b0;
            if (s_valid && s_ready) begin
                m_valid       <= 1'b1;
                m_epoch       <= s_camera_epoch;
                m_skew        <= skew_value;
                m_epoch_match <= (s_camera_epoch == s_audio_epoch);
                m_aligned     <= (s_camera_epoch == s_audio_epoch) &&
                                 (skew_magnitude <= {33'd0, s_tolerance});
            end
        end
    end
endmodule
