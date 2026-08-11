// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_vision_pipeline #(
    parameter integer MAX_WIDTH = 1920
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] input_width,
    input  logic [11:0] threshold,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic [23:0] s_axis_tdata,
    input  logic        s_axis_tuser,
    input  logic        s_axis_tlast,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic [7:0]  m_axis_tdata,
    output logic        m_axis_tuser,
    output logic        m_axis_tlast
);
    logic [7:0] prev_line [0:MAX_WIDTH-1];
    logic [7:0] prev2_line [0:MAX_WIDTH-1];
    localparam integer ADDR_WIDTH = $clog2(MAX_WIDTH);
    localparam logic [15:0] MAX_WIDTH_U16 = MAX_WIDTH;
    logic [15:0] x;
    logic [ADDR_WIDTH-1:0] x_idx;
    logic [15:0] y;
    logic sof_pending;
    logic edge_d1;
    logic edge_d2;
    logic [7:0] top_l, top_c, mid_l, mid_c, bot_l, bot_c;
    logic [15:0] gray_sum;
    logic [7:0] gray;
    logic [7:0] top_r;
    logic [7:0] mid_r;
    logic selected;
    logic output_slot;
    integer gx_calc;
    integer gy_calc;
    integer mag_calc;
    logic edge_calc;

    always_comb begin
        gray_sum = (16'd77  * s_axis_tdata[23:16])
                 + (16'd150 * s_axis_tdata[15:8])
                 + (16'd29  * s_axis_tdata[7:0])
                 + 16'd128;
        gray = gray_sum[15:8];
        x_idx = x[ADDR_WIDTH-1:0];
        top_r = prev2_line[x_idx];
        mid_r = prev_line[x_idx];
        selected = (y >= 2) && (x >= 2);
        output_slot = ~m_axis_tvalid | m_axis_tready;
        s_axis_tready = selected ? output_slot : 1'b1;

        gx_calc = $signed({1'b0, top_r}) + ($signed({1'b0, mid_r}) <<< 1)
                + $signed({1'b0, gray}) - $signed({1'b0, top_l})
                - ($signed({1'b0, mid_l}) <<< 1) - $signed({1'b0, bot_l});
        gy_calc = $signed({1'b0, bot_l}) + ($signed({1'b0, bot_c}) <<< 1)
                + $signed({1'b0, gray}) - $signed({1'b0, top_l})
                - ($signed({1'b0, top_c}) <<< 1) - $signed({1'b0, top_r});
        mag_calc = (gx_calc < 0 ? -gx_calc : gx_calc)
                 + (gy_calc < 0 ? -gy_calc : gy_calc);
        edge_calc = mag_calc >= threshold;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            x <= 0;
            y <= 0;
            sof_pending <= 1'b0;
            edge_d1 <= 1'b0;
            edge_d2 <= 1'b0;
            top_l <= 0; top_c <= 0;
            mid_l <= 0; mid_c <= 0;
            bot_l <= 0; bot_c <= 0;
            m_axis_tvalid <= 1'b0;
            m_axis_tdata <= 0;
            m_axis_tuser <= 1'b0;
            m_axis_tlast <= 1'b0;
        end else begin
            if (output_slot)
                m_axis_tvalid <= 1'b0;

            if (s_axis_tvalid && s_axis_tready) begin
                if (s_axis_tuser)
                    sof_pending <= 1'b1;
                if (x < MAX_WIDTH_U16) begin
                    prev2_line[x_idx] <= prev_line[x_idx];
                    prev_line[x_idx] <= gray;
                end

                top_l <= top_c; top_c <= top_r;
                mid_l <= mid_c; mid_c <= mid_r;
                bot_l <= bot_c; bot_c <= gray;

                if (selected) begin
                    m_axis_tvalid <= 1'b1;
                    m_axis_tdata <= (edge_calc | edge_d1 | edge_d2) ? 8'hff : 8'h00;
                    m_axis_tuser <= sof_pending;
                    m_axis_tlast <= s_axis_tlast;
                    sof_pending <= 1'b0;
                    edge_d2 <= edge_d1;
                    edge_d1 <= edge_calc;
                end

                if (s_axis_tlast) begin
                    x <= 0;
                    y <= y + 1'b1;
                    top_l <= 0; top_c <= 0;
                    mid_l <= 0; mid_c <= 0;
                    bot_l <= 0; bot_c <= 0;
                    edge_d1 <= 1'b0;
                    edge_d2 <= 1'b0;
                end else begin
                    x <= x + 1'b1;
                end
                if (s_axis_tuser) begin
                    x <= 1;
                    y <= 0;
                end
            end
        end
    end
endmodule
