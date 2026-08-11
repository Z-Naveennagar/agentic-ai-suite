// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_axis_register_slice (
    input  logic        aclk,
    input  logic        aresetn,
    input  logic [31:0] s_axis_tdata,
    input  logic        s_axis_tlast,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    output logic [31:0] m_axis_tdata,
    output logic        m_axis_tlast,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready
);
    logic [31:0] data_q;
    logic last_q, valid_q;

    assign s_axis_tready = !valid_q || m_axis_tready;
    assign m_axis_tdata  = data_q;
    assign m_axis_tlast  = last_q;
    assign m_axis_tvalid = valid_q;

    always_ff @(posedge aclk) begin
        if (!aresetn) begin
            valid_q <= 1'b0;
            data_q  <= 32'd0;
            last_q  <= 1'b0;
        end else if (s_axis_tready) begin
            valid_q <= s_axis_tvalid;
            if (s_axis_tvalid) begin
                data_q <= s_axis_tdata;
                last_q <= s_axis_tlast;
            end
        end
    end
endmodule
