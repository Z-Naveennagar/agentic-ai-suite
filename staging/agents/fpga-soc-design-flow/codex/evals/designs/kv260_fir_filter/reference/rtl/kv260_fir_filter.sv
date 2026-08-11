// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_fir_filter (
    input  logic               clk,
    input  logic               rst,
    input  logic               s_valid,
    input  logic signed [15:0] s_data,
    output logic               m_valid,
    output logic signed [35:0] m_data
);

  logic signed [15:0] delay [0:6];
  logic signed [35:0] convolution;
  integer index;

  always_comb begin
    convolution =
        $signed(s_data) * 36'sd1 +
        $signed(delay[0]) * 36'sd2 +
        $signed(delay[1]) * 36'sd3 +
        $signed(delay[2]) * 36'sd4 +
        $signed(delay[3]) * 36'sd4 +
        $signed(delay[4]) * 36'sd3 +
        $signed(delay[5]) * 36'sd2 +
        $signed(delay[6]) * 36'sd1;
  end

  always_ff @(posedge clk) begin
    if (rst) begin
      m_valid <= 1'b0;
      m_data <= '0;
      for (index = 0; index < 7; index = index + 1)
        delay[index] <= '0;
    end else begin
      m_valid <= s_valid;
      if (s_valid) begin
        m_data <= convolution;
        for (index = 6; index > 0; index = index - 1)
          delay[index] <= delay[index-1];
        delay[0] <= s_data;
      end
    end
  end

endmodule
