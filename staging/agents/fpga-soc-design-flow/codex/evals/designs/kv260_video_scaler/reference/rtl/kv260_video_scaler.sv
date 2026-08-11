// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_video_scaler (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [15:0] input_width,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic [23:0] s_axis_tdata,
    input  logic        s_axis_tuser,
    input  logic        s_axis_tlast,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic [23:0] m_axis_tdata,
    output logic        m_axis_tuser,
    output logic        m_axis_tlast
);
    logic [15:0] x;
    logic row_odd;
    logic retain;
    logic output_slot;
    logic retained_eol;

    always_comb begin
        retain = ~row_odd && ~x[0];
        output_slot = ~m_axis_tvalid | m_axis_tready;
        s_axis_tready = retain ? output_slot : 1'b1;
        retained_eol = input_width[0]
                     ? s_axis_tlast
                     : (input_width >= 2 && x == input_width - 2);
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            x <= '0;
            row_odd <= 1'b0;
            m_axis_tvalid <= 1'b0;
            m_axis_tdata <= '0;
            m_axis_tuser <= 1'b0;
            m_axis_tlast <= 1'b0;
        end else begin
            if (output_slot)
                m_axis_tvalid <= 1'b0;

            if (s_axis_tvalid && s_axis_tready) begin
                if (retain) begin
                    m_axis_tvalid <= 1'b1;
                    m_axis_tdata <= s_axis_tdata;
                    m_axis_tuser <= s_axis_tuser;
                    m_axis_tlast <= retained_eol;
                end
                if (s_axis_tlast) begin
                    x <= 0;
                    row_odd <= ~row_odd;
                end else begin
                    x <= x + 1'b1;
                end
                if (s_axis_tuser) begin
                    x <= 1;
                    row_odd <= 1'b0;
                end
            end
        end
    end
endmodule
