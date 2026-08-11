// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_axi_traffic_monitor (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        s_valid,
    output logic        s_ready,
    input  logic        s_read_beat,
    input  logic        s_write_beat,
    input  logic        s_stall,
    input  logic        s_snapshot,
    output logic        m_valid,
    input  logic        m_ready,
    output logic [31:0] m_cycles,
    output logic [31:0] m_read_beats,
    output logic [31:0] m_write_beats,
    output logic [31:0] m_stalls
);
    logic [31:0] cycles;
    logic [31:0] read_beats;
    logic [31:0] write_beats;
    logic [31:0] stalls;

    assign s_ready = !m_valid || m_ready;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cycles       <= 32'd0;
            read_beats   <= 32'd0;
            write_beats  <= 32'd0;
            stalls       <= 32'd0;
            m_valid      <= 1'b0;
            m_cycles     <= 32'd0;
            m_read_beats <= 32'd0;
            m_write_beats<= 32'd0;
            m_stalls     <= 32'd0;
        end else begin
            if (m_valid && m_ready)
                m_valid <= 1'b0;
            if (s_valid && s_ready) begin
                if (s_snapshot) begin
                    m_valid       <= 1'b1;
                    m_cycles      <= cycles + 32'd1;
                    m_read_beats  <= read_beats + s_read_beat;
                    m_write_beats <= write_beats + s_write_beat;
                    m_stalls      <= stalls + s_stall;
                    cycles        <= 32'd0;
                    read_beats    <= 32'd0;
                    write_beats   <= 32'd0;
                    stalls        <= 32'd0;
                end else begin
                    cycles      <= cycles + 32'd1;
                    read_beats  <= read_beats + s_read_beat;
                    write_beats <= write_beats + s_write_beat;
                    stalls      <= stalls + s_stall;
                end
            end
        end
    end
endmodule
