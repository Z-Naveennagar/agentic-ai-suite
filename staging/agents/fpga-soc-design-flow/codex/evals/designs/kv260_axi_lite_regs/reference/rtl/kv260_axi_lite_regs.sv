// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_axi_lite_regs #(
    parameter int unsigned ADDR_WIDTH = 6
) (
    input  logic                  s_axi_aclk,
    input  logic                  s_axi_aresetn,
    input  logic [ADDR_WIDTH-1:0] s_axi_awaddr,
    input  logic                  s_axi_awvalid,
    output logic                  s_axi_awready,
    input  logic [31:0]           s_axi_wdata,
    input  logic [3:0]            s_axi_wstrb,
    input  logic                  s_axi_wvalid,
    output logic                  s_axi_wready,
    output logic [1:0]            s_axi_bresp,
    output logic                  s_axi_bvalid,
    input  logic                  s_axi_bready,
    input  logic [ADDR_WIDTH-1:0] s_axi_araddr,
    input  logic                  s_axi_arvalid,
    output logic                  s_axi_arready,
    output logic [31:0]           s_axi_rdata,
    output logic [1:0]            s_axi_rresp,
    output logic                  s_axi_rvalid,
    input  logic                  s_axi_rready
);
    logic [31:0] regs [0:3];
    logic [ADDR_WIDTH-1:0] awaddr_q;
    logic [31:0] wdata_q;
    logic [3:0] wstrb_q;
    logic aw_pending, w_pending;
    integer i, byte_index;

    assign s_axi_awready = !aw_pending && !s_axi_bvalid;
    assign s_axi_wready  = !w_pending && !s_axi_bvalid;
    assign s_axi_arready = !s_axi_rvalid;

    always_ff @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            aw_pending <= 1'b0;
            w_pending  <= 1'b0;
            s_axi_bvalid <= 1'b0;
            s_axi_bresp  <= 2'b00;
            s_axi_rvalid <= 1'b0;
            s_axi_rresp  <= 2'b00;
            s_axi_rdata  <= 32'd0;
            for (i = 0; i < 4; i = i + 1)
                regs[i] <= 32'd0;
        end else begin
            if (s_axi_awready && s_axi_awvalid) begin
                awaddr_q <= s_axi_awaddr;
                aw_pending <= 1'b1;
            end
            if (s_axi_wready && s_axi_wvalid) begin
                wdata_q <= s_axi_wdata;
                wstrb_q <= s_axi_wstrb;
                w_pending <= 1'b1;
            end

            if (aw_pending && w_pending && !s_axi_bvalid) begin
                if ((awaddr_q[1:0] == 2'b00) && (awaddr_q[ADDR_WIDTH-1:2] < 4)) begin
                    for (byte_index = 0; byte_index < 4; byte_index = byte_index + 1)
                        if (wstrb_q[byte_index])
                            regs[awaddr_q[3:2]][byte_index*8 +: 8] <=
                                wdata_q[byte_index*8 +: 8];
                    s_axi_bresp <= 2'b00;
                end else begin
                    s_axi_bresp <= 2'b10;
                end
                aw_pending <= 1'b0;
                w_pending <= 1'b0;
                s_axi_bvalid <= 1'b1;
            end else if (s_axi_bvalid && s_axi_bready) begin
                s_axi_bvalid <= 1'b0;
            end

            if (s_axi_arready && s_axi_arvalid) begin
                if ((s_axi_araddr[1:0] == 2'b00) &&
                    (s_axi_araddr[ADDR_WIDTH-1:2] < 4)) begin
                    s_axi_rdata <= regs[s_axi_araddr[3:2]];
                    s_axi_rresp <= 2'b00;
                end else begin
                    s_axi_rdata <= 32'd0;
                    s_axi_rresp <= 2'b10;
                end
                s_axi_rvalid <= 1'b1;
            end else if (s_axi_rvalid && s_axi_rready) begin
                s_axi_rvalid <= 1'b0;
            end
        end
    end
endmodule
