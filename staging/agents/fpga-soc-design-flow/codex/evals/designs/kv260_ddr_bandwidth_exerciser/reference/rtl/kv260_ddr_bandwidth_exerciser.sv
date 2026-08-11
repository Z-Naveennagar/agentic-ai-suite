// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_ddr_bandwidth_exerciser (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        start,
    input  logic [31:0] base_address,
    input  logic [15:0] beat_count,
    input  logic [15:0] stride_bytes,
    input  logic        write_mode,
    output logic        busy,
    output logic        req_valid,
    input  logic        req_ready,
    output logic [31:0] req_address,
    output logic        req_write,
    output logic        done,
    output logic [15:0] issued_count
);
    logic [15:0] target_count;
    logic [15:0] stride;

    assign req_valid = busy;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            busy         <= 1'b0;
            req_address  <= 32'd0;
            req_write    <= 1'b0;
            done         <= 1'b0;
            issued_count <= 16'd0;
            target_count <= 16'd0;
            stride       <= 16'd0;
        end else begin
            done <= 1'b0;
            if (!busy && start) begin
                req_address  <= base_address;
                req_write    <= write_mode;
                issued_count <= 16'd0;
                target_count <= beat_count;
                stride       <= stride_bytes;
                if (beat_count == 16'd0) begin
                    busy <= 1'b0;
                    done <= 1'b1;
                end else begin
                    busy <= 1'b1;
                end
            end else if (busy && req_ready) begin
                issued_count <= issued_count + 16'd1;
                if (issued_count + 16'd1 == target_count) begin
                    busy <= 1'b0;
                    done <= 1'b1;
                end else begin
                    req_address <= req_address + {16'd0, stride};
                end
            end
        end
    end
endmodule
