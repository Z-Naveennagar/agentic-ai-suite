// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_mipi_capture_pipeline #(
    parameter integer MAX_WIDTH = 1920,
    parameter integer BLACK_LEVEL = 16
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] input_width,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic [7:0]  s_axis_tdata,
    input  logic        s_axis_tuser,
    input  logic        s_axis_tlast,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic [7:0]  m_axis_tdata,
    output logic        m_axis_tuser,
    output logic        m_axis_tlast
);
    logic [7:0] line_mem [0:MAX_WIDTH-1];
    localparam integer ADDR_WIDTH = $clog2(MAX_WIDTH);
    localparam logic [7:0] BLACK_LEVEL_U8 = BLACK_LEVEL;
    localparam logic [15:0] MAX_WIDTH_U16 = MAX_WIDTH;
    logic [15:0] x;
    logic [ADDR_WIDTH-1:0] x_idx;
    logic row_odd;
    logic sof_pending;
    logic [7:0] bottom_left;
    logic [7:0] clamped;
    logic selected;
    logic output_slot;
    logic [9:0] block_sum;

    always_comb begin
        x_idx = x[ADDR_WIDTH-1:0];
        clamped = (s_axis_tdata > BLACK_LEVEL_U8)
                ? s_axis_tdata - BLACK_LEVEL_U8 : 8'd0;
        selected = row_odd && x[0];
        output_slot = ~m_axis_tvalid | m_axis_tready;
        s_axis_tready = selected ? output_slot : 1'b1;
        if (selected && x < MAX_WIDTH_U16)
            block_sum = {2'b00, line_mem[x_idx-1'b1]}
                      + {2'b00, line_mem[x_idx]}
                      + {2'b00, bottom_left}
                      + {2'b00, clamped};
        else
            block_sum = 0;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            x <= 0;
            row_odd <= 1'b0;
            sof_pending <= 1'b0;
            bottom_left <= 0;
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
                if (!row_odd && x < MAX_WIDTH_U16)
                    line_mem[x_idx] <= clamped;
                if (row_odd && !x[0])
                    bottom_left <= clamped;
                if (selected) begin
                    m_axis_tvalid <= 1'b1;
                    m_axis_tdata <= block_sum[9:2];
                    m_axis_tuser <= sof_pending;
                    m_axis_tlast <= s_axis_tlast;
                    sof_pending <= 1'b0;
                end
                if (s_axis_tlast) begin
                    x <= 0;
                    row_odd <= ~row_odd;
                end else begin
                    x <= x + 1'b1;
                end
            end
        end
    end
endmodule
