// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_rgb_to_grayscale (
    input  logic        clk,
    input  logic        rst_n,
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
    logic [15:0] luma_sum;

    always_comb begin
        luma_sum = (16'd77  * s_axis_tdata[23:16])
                 + (16'd150 * s_axis_tdata[15:8])
                 + (16'd29  * s_axis_tdata[7:0])
                 + 16'd128;
        s_axis_tready = ~m_axis_tvalid | m_axis_tready;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            m_axis_tvalid <= 1'b0;
            m_axis_tdata  <= '0;
            m_axis_tuser  <= 1'b0;
            m_axis_tlast  <= 1'b0;
        end else if (s_axis_tready) begin
            m_axis_tvalid <= s_axis_tvalid;
            if (s_axis_tvalid) begin
                m_axis_tdata <= luma_sum[15:8];
                m_axis_tuser <= s_axis_tuser;
                m_axis_tlast <= s_axis_tlast;
            end
        end
    end
endmodule
