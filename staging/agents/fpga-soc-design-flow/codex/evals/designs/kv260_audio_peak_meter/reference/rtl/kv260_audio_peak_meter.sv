// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_audio_peak_meter #(
    parameter integer WINDOW_SIZE = 8
) (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               s_valid,
    output logic               s_ready,
    input  logic signed [15:0] s_data,
    output logic               peak_valid,
    input  logic               peak_ready,
    output logic        [15:0] peak_value
);
    logic [15:0] peak_q;
    integer count_q;
    logic [15:0] magnitude;

    always_comb begin
        if (s_data == 16'sh8000)
            magnitude = 16'h8000;
        else if (s_data[15])
            magnitude = -s_data;
        else
            magnitude = s_data;
    end

    assign s_ready = !peak_valid || peak_ready;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            peak_q    <= '0;
            count_q   <= 0;
            peak_valid <= 1'b0;
            peak_value <= '0;
        end else begin
            if (peak_valid && peak_ready)
                peak_valid <= 1'b0;
            if (s_valid && s_ready) begin
                if (count_q == WINDOW_SIZE - 1) begin
                    peak_value <= (magnitude > peak_q) ? magnitude : peak_q;
                    peak_valid <= 1'b1;
                    peak_q     <= '0;
                    count_q    <= 0;
                end else begin
                    if (magnitude > peak_q)
                        peak_q <= magnitude;
                    count_q <= count_q + 1;
                end
            end
        end
    end
endmodule
