// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_dma_descriptor_queue (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        push_valid,
    output logic        push_ready,
    input  logic [63:0] push_address,
    input  logic [23:0] push_length,
    input  logic [7:0]  push_tag,
    output logic        pop_valid,
    input  logic        pop_ready,
    output logic [63:0] pop_address,
    output logic [23:0] pop_length,
    output logic [7:0]  pop_tag,
    input  logic        completion_valid,
    output logic [31:0] completion_count,
    output logic [2:0]  queued_count
);
    logic [63:0] address_mem [0:3];
    logic [23:0] length_mem [0:3];
    logic [7:0]  tag_mem [0:3];
    logic [1:0]  write_pointer;
    logic [1:0]  read_pointer;
    logic        push_fire;
    logic        pop_fire;

    assign pop_valid = (queued_count != 3'd0);
    assign push_ready = (queued_count != 3'd4) || (pop_valid && pop_ready);
    assign push_fire = push_valid && push_ready;
    assign pop_fire = pop_valid && pop_ready;
    assign pop_address = address_mem[read_pointer];
    assign pop_length = length_mem[read_pointer];
    assign pop_tag = tag_mem[read_pointer];

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            write_pointer   <= 2'd0;
            read_pointer    <= 2'd0;
            queued_count    <= 3'd0;
            completion_count<= 32'd0;
        end else begin
            if (completion_valid)
                completion_count <= completion_count + 32'd1;
            if (push_fire) begin
                address_mem[write_pointer] <= push_address;
                length_mem[write_pointer]  <= push_length;
                tag_mem[write_pointer]     <= push_tag;
                write_pointer              <= write_pointer + 2'd1;
            end
            if (pop_fire)
                read_pointer <= read_pointer + 2'd1;
            case ({push_fire, pop_fire})
                2'b10: queued_count <= queued_count + 3'd1;
                2'b01: queued_count <= queued_count - 3'd1;
                default: queued_count <= queued_count;
            endcase
        end
    end
endmodule
