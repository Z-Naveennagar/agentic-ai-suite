// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_linux_gpio_mailbox (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        cmd_valid,
    output logic        cmd_ready,
    input  logic [7:0]  cmd_opcode,
    input  logic [31:0] cmd_argument,
    output logic        rsp_valid,
    input  logic        rsp_ready,
    output logic [31:0] rsp_data,
    output logic        rsp_error,
    output logic [31:0] accumulator
);
    assign cmd_ready = !rsp_valid || rsp_ready;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rsp_valid   <= 1'b0;
            rsp_data    <= 32'd0;
            rsp_error   <= 1'b0;
            accumulator <= 32'd0;
        end else begin
            if (rsp_valid && rsp_ready)
                rsp_valid <= 1'b0;
            if (cmd_valid && cmd_ready) begin
                rsp_valid <= 1'b1;
                rsp_error <= 1'b0;
                case (cmd_opcode)
                    8'd0: rsp_data <= 32'd0;
                    8'd1: rsp_data <= cmd_argument;
                    8'd2: begin
                        accumulator <= accumulator + cmd_argument;
                        rsp_data <= accumulator + cmd_argument;
                    end
                    8'd3: rsp_data <= accumulator;
                    8'd4: begin
                        accumulator <= 32'd0;
                        rsp_data <= 32'd0;
                    end
                    default: begin
                        rsp_data <= 32'hDEAD0000 | {24'd0, cmd_opcode};
                        rsp_error <= 1'b1;
                    end
                endcase
            end
        end
    end
endmodule
