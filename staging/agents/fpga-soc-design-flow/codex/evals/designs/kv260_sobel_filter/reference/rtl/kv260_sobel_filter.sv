// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_sobel_filter (
    input  logic        clk,
    input  logic        rst,
    input  logic        s_valid,
    output logic        s_ready,
    input  logic [71:0] s_window,
    input  logic        s_line_start,
    input  logic        s_line_end,
    input  logic        s_border,
    output logic        m_valid,
    input  logic        m_ready,
    output logic [7:0]  m_magnitude,
    output logic        m_line_start,
    output logic        m_line_end,
    output logic        m_border
);

  function automatic logic [7:0] sobel_magnitude(
      input logic [71:0] window,
      input logic border
  );
    integer p0, p1, p2, p3, p5, p6, p7, p8;
    integer gx, gy, magnitude;
    begin
      p0 = {24'b0, window[7:0]};
      p1 = {24'b0, window[15:8]};
      p2 = {24'b0, window[23:16]};
      p3 = {24'b0, window[31:24]};
      p5 = {24'b0, window[47:40]};
      p6 = {24'b0, window[55:48]};
      p7 = {24'b0, window[63:56]};
      p8 = {24'b0, window[71:64]};
      gx = -p0 + p2 - (2*p3) + (2*p5) - p6 + p8;
      gy = p0 + (2*p1) + p2 - p6 - (2*p7) - p8;
      magnitude = ((gx < 0) ? -gx : gx) + ((gy < 0) ? -gy : gy);
      if (border)
        sobel_magnitude = 8'd0;
      else if (magnitude > 255)
        sobel_magnitude = 8'd255;
      else
        sobel_magnitude = magnitude[7:0];
    end
  endfunction

  assign s_ready = !m_valid || m_ready;

  always_ff @(posedge clk) begin
    if (rst) begin
      m_valid <= 1'b0;
      m_magnitude <= '0;
      m_line_start <= 1'b0;
      m_line_end <= 1'b0;
      m_border <= 1'b0;
    end else if (s_ready) begin
      m_valid <= s_valid;
      if (s_valid) begin
        m_magnitude <= sobel_magnitude(s_window, s_border);
        m_line_start <= s_line_start;
        m_line_end <= s_line_end;
        m_border <= s_border;
      end
    end
  end

endmodule
