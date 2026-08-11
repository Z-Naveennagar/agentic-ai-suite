// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module axis_selftest_top (
    input  logic clk,
    input  logic rst,
    output logic pass_o,
    output logic fail_o
);

  logic [31:0] generated;
  logic [31:0] expected;
  logic        source_valid;
  logic        source_ready;
  logic [31:0] sink_data;
  logic        sink_valid;

  assign source_valid = 1'b1;

  axis_register_slice dut (
      .clk(clk),
      .rst(rst),
      .s_axis_tvalid(source_valid),
      .s_axis_tready(source_ready),
      .s_axis_tdata(generated),
      .s_axis_tlast(generated[3:0] == 4'hf),
      .m_axis_tvalid(sink_valid),
      .m_axis_tready(1'b1),
      .m_axis_tdata(sink_data),
      .m_axis_tlast()
  );

  always_ff @(posedge clk) begin
    if (rst) begin
      generated <= 32'h0;
      expected <= 32'h0;
      pass_o <= 1'b0;
      fail_o <= 1'b0;
    end else begin
      if (source_valid && source_ready) begin
        generated <= generated + 1'b1;
      end
      if (sink_valid) begin
        if (sink_data != expected) begin
          fail_o <= 1'b1;
        end else begin
          expected <= expected + 1'b1;
          if (expected == 32'd255) begin
            pass_o <= 1'b1;
          end
        end
      end
    end
  end

endmodule
