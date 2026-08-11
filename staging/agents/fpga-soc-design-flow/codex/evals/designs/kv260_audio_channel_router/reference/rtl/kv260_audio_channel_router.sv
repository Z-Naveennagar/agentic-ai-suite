// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_audio_channel_router (
    input  logic               clk,
    input  logic               rst_n,
    input  logic        [1:0]  route_select,
    input  logic               s_valid,
    output logic               s_ready,
    input  logic signed [15:0] left_in,
    input  logic signed [15:0] right_in,
    output logic               m_valid,
    input  logic               m_ready,
    output logic signed [15:0] left_out,
    output logic signed [15:0] right_out
);
    logic signed [15:0] routed_left, routed_right;

    assign s_ready = !m_valid || m_ready;

    always_comb begin
        case (route_select)
            2'd0: begin routed_left = left_in;  routed_right = right_in; end
            2'd1: begin routed_left = right_in; routed_right = left_in;  end
            2'd2: begin routed_left = left_in;  routed_right = left_in;  end
            default: begin routed_left = right_in; routed_right = right_in; end
        endcase
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            m_valid   <= 1'b0;
            left_out  <= '0;
            right_out <= '0;
        end else if (s_ready) begin
            m_valid <= s_valid;
            if (s_valid) begin
                left_out  <= routed_left;
                right_out <= routed_right;
            end
        end
    end
endmodule
