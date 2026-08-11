// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_audio_dc_blocker (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               s_valid,
    output logic               s_ready,
    input  logic signed [15:0] s_data,
    output logic               m_valid,
    input  logic               m_ready,
    output logic signed [15:0] m_data
);
    logic signed [15:0] x_previous;
    logic signed [23:0] y_previous;
    logic signed [39:0] feedback_product;
    logic signed [23:0] sample_extended;
    logic signed [23:0] previous_extended;
    logic signed [23:0] feedback_term;
    logic signed [23:0] next_y;

    function automatic logic signed [15:0] saturate16(input logic signed [23:0] value);
        if (value > 32767)
            saturate16 = 16'sh7fff;
        else if (value < -32768)
            saturate16 = 16'sh8000;
        else
            saturate16 = value[15:0];
    endfunction

    assign s_ready = !m_valid || m_ready;

    always_comb begin
        sample_extended = {{8{s_data[15]}}, s_data};
        previous_extended = {{8{x_previous[15]}}, x_previous};
        feedback_product =
            $signed({{16{y_previous[23]}}, y_previous}) * 40'sd15;
        feedback_term = feedback_product[27:4];
        next_y = sample_extended - previous_extended + feedback_term;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            x_previous <= '0;
            y_previous <= '0;
            m_valid    <= 1'b0;
            m_data     <= '0;
        end else if (s_ready) begin
            m_valid <= s_valid;
            if (s_valid) begin
                x_previous <= s_data;
                y_previous <= next_y;
                m_data     <= saturate16(next_y);
            end
        end
    end
endmodule
