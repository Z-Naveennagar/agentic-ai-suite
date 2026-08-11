// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_multimedia_appliance (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        start,
    input  logic        clear,
    input  logic [15:0] target_frames,
    input  logic [15:0] target_audio_blocks,
    input  logic        frame_event,
    input  logic        audio_event,
    input  logic        ddr_error,
    input  logic        abort,
    output logic        busy,
    output logic        done,
    output logic        pass,
    output logic [15:0] error_code,
    output logic [15:0] frame_count,
    output logic [15:0] audio_count
);
    logic [15:0] frame_target;
    logic [15:0] audio_target;
    logic [15:0] next_frame_count;
    logic [15:0] next_audio_count;

    always_comb begin
        next_frame_count = frame_count + (frame_event ? 16'd1 : 16'd0);
        next_audio_count = audio_count + (audio_event ? 16'd1 : 16'd0);
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            busy        <= 1'b0;
            done        <= 1'b0;
            pass        <= 1'b0;
            error_code  <= 16'd0;
            frame_count <= 16'd0;
            audio_count <= 16'd0;
            frame_target<= 16'd0;
            audio_target<= 16'd0;
        end else if (clear) begin
            busy        <= 1'b0;
            done        <= 1'b0;
            pass        <= 1'b0;
            error_code  <= 16'd0;
            frame_count <= 16'd0;
            audio_count <= 16'd0;
            frame_target<= 16'd0;
            audio_target<= 16'd0;
        end else if (busy) begin
            if (ddr_error) begin
                busy       <= 1'b0;
                done       <= 1'b1;
                pass       <= 1'b0;
                error_code <= 16'd1;
            end else if (abort) begin
                busy       <= 1'b0;
                done       <= 1'b1;
                pass       <= 1'b0;
                error_code <= 16'd2;
            end else begin
                if (frame_event)
                    frame_count <= next_frame_count;
                if (audio_event)
                    audio_count <= next_audio_count;
                if ((next_frame_count >= frame_target) &&
                    (next_audio_count >= audio_target)) begin
                    busy       <= 1'b0;
                    done       <= 1'b1;
                    pass       <= 1'b1;
                    error_code <= 16'd0;
                end
            end
        end else if (start) begin
            frame_target <= target_frames;
            audio_target <= target_audio_blocks;
            frame_count  <= 16'd0;
            audio_count  <= 16'd0;
            error_code   <= 16'd0;
            if ((target_frames == 16'd0) &&
                (target_audio_blocks == 16'd0)) begin
                busy <= 1'b0;
                done <= 1'b1;
                pass <= 1'b1;
            end else begin
                busy <= 1'b1;
                done <= 1'b0;
                pass <= 1'b0;
            end
        end
    end
endmodule
