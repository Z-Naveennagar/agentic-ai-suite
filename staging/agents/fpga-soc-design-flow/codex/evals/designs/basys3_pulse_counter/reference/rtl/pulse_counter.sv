// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module pulse_counter (
    input  logic       clk,
    input  logic       rst,
    input  logic       event_i,
    input  logic       clear_i,
    output logic [7:0] count_o,
    output logic       overflow_o
);

  logic event_d;

  always_ff @(posedge clk) begin
    if (rst) begin
      event_d <= 1'b0;
      count_o <= 8'h00;
      overflow_o <= 1'b0;
    end else begin
      event_d <= event_i;
      overflow_o <= 1'b0;
      if (clear_i) begin
        count_o <= 8'h00;
      end else if (event_i && !event_d) begin
        if (count_o == 8'hff) begin
          count_o <= 8'h00;
          overflow_o <= 1'b1;
        end else begin
          count_o <= count_o + 1'b1;
        end
      end
    end
  end

endmodule
