// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_adaptive_threshold(
 input logic clk,input logic rst_n,input logic s_valid,output logic s_ready,
 input logic [7:0] s_pixel,input logic [7:0] s_mean,input logic [7:0] threshold_offset,
 input logic s_user,input logic s_last,output logic m_valid,input logic m_ready,
 output logic [7:0] m_mask,output logic m_user,output logic m_last
);
 logic [8:0] adjusted;
 assign adjusted={1'b0,s_pixel}+{1'b0,threshold_offset};
 assign s_ready=!m_valid||m_ready;
 always_ff @(posedge clk) begin
  if(!rst_n) begin m_valid<=0;m_mask<=0;m_user<=0;m_last<=0;end
  else if(s_ready) begin m_valid<=s_valid;if(s_valid) begin m_mask<=(adjusted>{1'b0,s_mean})?8'hff:8'h00;m_user<=s_user;m_last<=s_last;end end
 end
endmodule
