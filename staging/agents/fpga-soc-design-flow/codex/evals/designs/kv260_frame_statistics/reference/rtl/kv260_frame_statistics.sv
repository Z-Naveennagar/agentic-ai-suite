// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_frame_statistics (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        s_valid,
    output logic        s_ready,
    input  logic [7:0]  s_sample,
    input  logic        s_frame_first,
    input  logic        s_frame_last,
    output logic        m_valid,
    input  logic        m_ready,
    output logic [7:0]  m_minimum,
    output logic [7:0]  m_maximum,
    output logic [7:0]  m_mean,
    output logic [15:0] m_count
);
    logic [31:0] sum;
    logic [15:0] count;
    logic [7:0] minimum;
    logic [7:0] maximum;

    assign s_ready = !m_valid || m_ready;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sum       <= 32'd0;
            count     <= 16'd0;
            minimum   <= 8'd0;
            maximum   <= 8'd0;
            m_valid   <= 1'b0;
            m_minimum <= 8'd0;
            m_maximum <= 8'd0;
            m_mean    <= 8'd0;
            m_count   <= 16'd0;
        end else begin
            if (m_valid && m_ready)
                m_valid <= 1'b0;
            if (s_valid && s_ready) begin
                if (s_frame_first) begin
                    sum     <= {24'd0, s_sample};
                    count   <= 16'd1;
                    minimum <= s_sample;
                    maximum <= s_sample;
                    if (s_frame_last) begin
                        m_valid   <= 1'b1;
                        m_minimum <= s_sample;
                        m_maximum <= s_sample;
                        m_mean    <= s_sample;
                        m_count   <= 16'd1;
                    end
                end else begin
                    sum   <= sum + s_sample;
                    count <= count + 16'd1;
                    if (s_sample < minimum)
                        minimum <= s_sample;
                    if (s_sample > maximum)
                        maximum <= s_sample;
                    if (s_frame_last) begin
                        m_valid   <= 1'b1;
                        m_minimum <= (s_sample < minimum) ? s_sample : minimum;
                        m_maximum <= (s_sample > maximum) ? s_sample : maximum;
                        m_mean    <= (sum + s_sample) / (count + 16'd1);
                        m_count   <= count + 16'd1;
                    end
                end
            end
        end
    end
endmodule
