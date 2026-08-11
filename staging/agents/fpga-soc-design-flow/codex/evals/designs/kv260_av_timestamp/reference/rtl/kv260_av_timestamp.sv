// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_av_timestamp (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        v_valid,
    output logic        v_ready,
    input  logic [63:0] v_timestamp,
    input  logic        a_valid,
    output logic        a_ready,
    input  logic [63:0] a_timestamp,
    output logic        m_valid,
    input  logic        m_ready,
    output logic [63:0] m_video_timestamp,
    output logic [63:0] m_audio_timestamp,
    output logic [64:0] m_skew
);
    logic        video_pending;
    logic        audio_pending;
    logic [63:0] video_hold;
    logic [63:0] audio_hold;
    logic        video_fire;
    logic        audio_fire;
    logic        have_video;
    logic        have_audio;
    logic [63:0] selected_video;
    logic [63:0] selected_audio;

    assign v_ready = !video_pending;
    assign a_ready = !audio_pending;
    assign video_fire = v_valid && v_ready;
    assign audio_fire = a_valid && a_ready;
    assign have_video = video_pending || video_fire;
    assign have_audio = audio_pending || audio_fire;
    assign selected_video = video_fire ? v_timestamp : video_hold;
    assign selected_audio = audio_fire ? a_timestamp : audio_hold;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            video_pending      <= 1'b0;
            audio_pending      <= 1'b0;
            video_hold         <= 64'd0;
            audio_hold         <= 64'd0;
            m_valid            <= 1'b0;
            m_video_timestamp  <= 64'd0;
            m_audio_timestamp  <= 64'd0;
            m_skew             <= 65'd0;
        end else begin
            if (m_valid && m_ready)
                m_valid <= 1'b0;
            if (video_fire) begin
                video_pending <= 1'b1;
                video_hold    <= v_timestamp;
            end
            if (audio_fire) begin
                audio_pending <= 1'b1;
                audio_hold    <= a_timestamp;
            end
            if ((!m_valid || m_ready) && have_video && have_audio) begin
                m_valid           <= 1'b1;
                m_video_timestamp <= selected_video;
                m_audio_timestamp <= selected_audio;
                m_skew <= $signed({1'b0, selected_video}) -
                          $signed({1'b0, selected_audio});
                video_pending <= 1'b0;
                audio_pending <= 1'b0;
            end
        end
    end
endmodule
