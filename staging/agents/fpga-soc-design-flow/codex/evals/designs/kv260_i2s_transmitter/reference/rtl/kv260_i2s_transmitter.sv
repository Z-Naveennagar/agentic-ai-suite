// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_i2s_transmitter #(
    parameter integer CLK_DIV = 2
) (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               enable,
    input  logic               sample_valid,
    output logic               sample_ready,
    input  logic signed [15:0] left_sample,
    input  logic signed [15:0] right_sample,
    output logic               i2s_bclk,
    output logic               i2s_lrclk,
    output logic               i2s_sdata,
    output logic               busy
);
    logic [31:0] frame_q;
    logic [5:0] bit_index_q;
    integer divider_q;

    assign sample_ready = enable && !busy;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            frame_q    <= '0;
            bit_index_q <= '0;
            divider_q  <= 0;
            i2s_bclk   <= 1'b0;
            i2s_lrclk  <= 1'b0;
            i2s_sdata  <= 1'b0;
            busy       <= 1'b0;
        end else if (!enable) begin
            bit_index_q <= '0;
            divider_q  <= 0;
            i2s_bclk   <= 1'b0;
            i2s_lrclk  <= 1'b0;
            i2s_sdata  <= 1'b0;
            busy       <= 1'b0;
        end else if (!busy) begin
            i2s_bclk  <= 1'b0;
            i2s_lrclk <= 1'b0;
            i2s_sdata <= 1'b0;
            divider_q <= 0;
            if (sample_valid) begin
                frame_q     <= {left_sample, right_sample};
                bit_index_q <= 0;
                busy        <= 1'b1;
            end
        end else if (divider_q == CLK_DIV - 1) begin
            divider_q <= 0;
            i2s_bclk  <= ~i2s_bclk;
            if (i2s_bclk) begin
                if (bit_index_q == 0) begin
                    i2s_lrclk <= 1'b0;
                    i2s_sdata <= 1'b0;
                end else if (bit_index_q <= 16) begin
                    i2s_lrclk <= 1'b0;
                    i2s_sdata <= frame_q[32-bit_index_q];
                end else if (bit_index_q == 17) begin
                    i2s_lrclk <= 1'b1;
                    i2s_sdata <= 1'b0;
                end else if (bit_index_q <= 33) begin
                    i2s_lrclk <= 1'b1;
                    i2s_sdata <= frame_q[33-bit_index_q];
                end else begin
                    i2s_lrclk <= 1'b0;
                    i2s_sdata <= 1'b0;
                    busy      <= 1'b0;
                end
                if (bit_index_q <= 33)
                    bit_index_q <= bit_index_q + 1'b1;
            end
        end else begin
            divider_q <= divider_q + 1;
        end
    end
endmodule
