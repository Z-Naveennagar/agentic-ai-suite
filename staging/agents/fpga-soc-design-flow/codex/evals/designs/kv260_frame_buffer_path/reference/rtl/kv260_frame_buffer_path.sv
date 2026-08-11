// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_frame_buffer_path (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        s_cap_tvalid,
    output logic        s_cap_tready,
    input  logic [23:0] s_cap_tdata,
    input  logic        s_cap_tuser,
    input  logic        s_cap_tlast,
    output logic        m_wr_tvalid,
    input  logic        m_wr_tready,
    output logic [31:0] m_wr_tdata,
    output logic [3:0]  m_wr_tkeep,
    output logic        m_wr_tuser,
    output logic        m_wr_tlast,
    input  logic        s_rd_tvalid,
    output logic        s_rd_tready,
    input  logic [31:0] s_rd_tdata,
    input  logic        s_rd_tuser,
    input  logic        s_rd_tlast,
    output logic        m_disp_tvalid,
    input  logic        m_disp_tready,
    output logic [23:0] m_disp_tdata,
    output logic        m_disp_tuser,
    output logic        m_disp_tlast
);
    always_comb begin
        s_cap_tready = ~m_wr_tvalid | m_wr_tready;
        s_rd_tready = ~m_disp_tvalid | m_disp_tready;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            m_wr_tvalid <= 1'b0;
            m_wr_tdata <= '0;
            m_wr_tkeep <= '0;
            m_wr_tuser <= 1'b0;
            m_wr_tlast <= 1'b0;
            m_disp_tvalid <= 1'b0;
            m_disp_tdata <= '0;
            m_disp_tuser <= 1'b0;
            m_disp_tlast <= 1'b0;
        end else begin
            if (s_cap_tready) begin
                m_wr_tvalid <= s_cap_tvalid;
                if (s_cap_tvalid) begin
                    m_wr_tdata <= {8'h00, s_cap_tdata};
                    m_wr_tkeep <= 4'hf;
                    m_wr_tuser <= s_cap_tuser;
                    m_wr_tlast <= s_cap_tlast;
                end
            end
            if (s_rd_tready) begin
                m_disp_tvalid <= s_rd_tvalid;
                if (s_rd_tvalid) begin
                    m_disp_tdata <= s_rd_tdata[23:0];
                    m_disp_tuser <= s_rd_tuser;
                    m_disp_tlast <= s_rd_tlast;
                end
            end
        end
    end
endmodule
