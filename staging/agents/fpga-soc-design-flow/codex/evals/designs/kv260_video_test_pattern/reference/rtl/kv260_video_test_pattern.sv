// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_video_test_pattern (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        enable,
    input  logic [15:0] frame_width,
    input  logic [15:0] frame_height,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic [23:0] m_axis_tdata,
    output logic        m_axis_tuser,
    output logic        m_axis_tlast
);
    logic [15:0] x;
    logic [15:0] y;
    logic [18:0] scaled_x;
    logic [2:0]  bar_index;
    logic [23:0] bar_color;
    integer bar_calc;

    always_comb begin
        scaled_x = x * 8;
        bar_calc = (frame_width != 0)
                 ? scaled_x / {3'b000, frame_width} : 0;
        bar_index = bar_calc[2:0];
        unique case (bar_index)
            3'd0: bar_color = 24'hffffff;
            3'd1: bar_color = 24'hffff00;
            3'd2: bar_color = 24'h00ffff;
            3'd3: bar_color = 24'h00ff00;
            3'd4: bar_color = 24'hff00ff;
            3'd5: bar_color = 24'hff0000;
            3'd6: bar_color = 24'h0000ff;
            default: bar_color = 24'h000000;
        endcase
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            x <= '0;
            y <= '0;
            m_axis_tvalid <= 1'b0;
            m_axis_tdata <= '0;
            m_axis_tuser <= 1'b0;
            m_axis_tlast <= 1'b0;
        end else if (!m_axis_tvalid || m_axis_tready) begin
            if (enable && frame_width != 0 && frame_height != 0) begin
                m_axis_tvalid <= 1'b1;
                m_axis_tdata <= bar_color;
                m_axis_tuser <= (x == 0) && (y == 0);
                m_axis_tlast <= (x == frame_width - 1);
                if (x == frame_width - 1) begin
                    x <= 0;
                    y <= (y == frame_height - 1) ? 0 : y + 1'b1;
                end else begin
                    x <= x + 1'b1;
                end
            end else begin
                x <= '0;
                y <= '0;
                m_axis_tvalid <= 1'b0;
            end
        end
    end
endmodule
