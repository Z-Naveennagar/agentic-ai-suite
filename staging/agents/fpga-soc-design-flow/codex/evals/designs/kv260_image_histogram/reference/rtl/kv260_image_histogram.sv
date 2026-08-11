// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_image_histogram(
  input logic clk,input logic rst_n,input logic clear,input logic s_valid,
  output logic s_ready,input logic [7:0] s_data,input logic [3:0] query_bin,
  output logic [31:0] query_count,output logic [31:0] total_count
);
  logic [31:0] histogram[0:15];
  integer i;
  assign s_ready=rst_n;
  assign query_count=histogram[query_bin];
  always_ff @(posedge clk) begin
    if(!rst_n || clear) begin
      total_count<=0;
      for(i=0;i<16;i=i+1) histogram[i]<=0;
    end else if(s_valid && s_ready) begin
      histogram[s_data[7:4]]<=histogram[s_data[7:4]]+1'b1;
      total_count<=total_count+1'b1;
    end
  end
endmodule
