// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_audio_gain (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               s_valid,
    output logic               s_ready,
    input  logic signed [15:0] s_data,
    input  logic        [15:0] gain_q14,
    output logic               m_valid,
    input  logic               m_ready,
    output logic signed [15:0] m_data
);
    logic signed [31:0] product;
    logic signed [31:0] scaled;

    function automatic logic signed [15:0] saturate16(input logic signed [31:0] value);
        if (value > 32767)
            saturate16 = 16'sh7fff;
        else if (value < -32768)
            saturate16 = 16'sh8000;
        else
            saturate16 = value[15:0];
    endfunction

    assign s_ready = !m_valid || m_ready;

    always_comb begin
        product = $signed(s_data) * $signed({1'b0, gain_q14});
        scaled = product >>> 14;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            m_valid <= 1'b0;
            m_data  <= '0;
        end else if (s_ready) begin
            m_valid <= s_valid;
            if (s_valid)
                m_data <= saturate16(scaled);
        end
    end
endmodule
