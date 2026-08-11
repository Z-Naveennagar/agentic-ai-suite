// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_crc32_stream (
    input  logic        clk,
    input  logic        rst,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic [7:0]  s_axis_tdata,
    input  logic        s_axis_tlast,
    output logic        crc_valid,
    input  logic        crc_ready,
    output logic [31:0] crc_data
);

  logic [31:0] crc_state;

  function automatic logic [31:0] update_crc32(
      input logic [31:0] crc_in,
      input logic [7:0] data_in
  );
    logic [31:0] value;
    integer bit_index;
    begin
      value = crc_in;
      for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
        if (value[0] ^ data_in[bit_index])
          value = (value >> 1) ^ 32'hEDB88320;
        else
          value = value >> 1;
      end
      update_crc32 = value;
    end
  endfunction

  assign s_axis_tready = !crc_valid;

  always_ff @(posedge clk) begin
    if (rst) begin
      crc_state <= 32'hFFFFFFFF;
      crc_valid <= 1'b0;
      crc_data <= '0;
    end else begin
      if (crc_valid && crc_ready)
        crc_valid <= 1'b0;

      if (s_axis_tvalid && s_axis_tready) begin
        if (s_axis_tlast) begin
          crc_data <= ~update_crc32(crc_state, s_axis_tdata);
          crc_valid <= 1'b1;
          crc_state <= 32'hFFFFFFFF;
        end else begin
          crc_state <= update_crc32(crc_state, s_axis_tdata);
        end
      end
    end
  end

endmodule
