// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_i2s_receiver (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               enable,
    input  logic               i2s_bclk,
    input  logic               i2s_lrclk,
    input  logic               i2s_sdata,
    output logic               sample_valid,
    input  logic               sample_ready,
    output logic signed [15:0] left_sample,
    output logic signed [15:0] right_sample
);
    logic bclk_q, channel_q, skip_q;
    logic [4:0] bit_count_q;
    logic [15:0] shift_q, left_q;

    always_ff @(posedge clk) begin
        if (!rst_n || !enable) begin
            bclk_q      <= 1'b0;
            channel_q   <= 1'b0;
            skip_q      <= 1'b1;
            bit_count_q <= '0;
            shift_q     <= '0;
            left_q      <= '0;
            left_sample <= '0;
            right_sample <= '0;
            sample_valid <= 1'b0;
        end else begin
            bclk_q <= i2s_bclk;
            if (sample_valid && sample_ready)
                sample_valid <= 1'b0;

            if (!sample_valid && !bclk_q && i2s_bclk) begin
                if (i2s_lrclk != channel_q) begin
                    channel_q   <= i2s_lrclk;
                    bit_count_q <= '0;
                    // The transition-edge bit is the I2S one-bit delay.
                    skip_q      <= 1'b0;
                end else if (skip_q) begin
                    skip_q <= 1'b0;
                end else begin
                    shift_q <= {shift_q[14:0], i2s_sdata};
                    if (bit_count_q == 15) begin
                        bit_count_q <= '0;
                        skip_q      <= 1'b1;
                        if (!channel_q) begin
                            left_q <= {shift_q[14:0], i2s_sdata};
                        end else begin
                            left_sample  <= left_q;
                            right_sample <= {shift_q[14:0], i2s_sdata};
                            sample_valid <= 1'b1;
                        end
                    end else begin
                        bit_count_q <= bit_count_q + 1'b1;
                    end
                end
            end
        end
    end
endmodule
