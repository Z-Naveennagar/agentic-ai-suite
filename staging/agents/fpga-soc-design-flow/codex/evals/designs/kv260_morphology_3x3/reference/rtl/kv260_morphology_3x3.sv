// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_morphology_3x3(
 input logic clk,input logic rst_n,input logic s_valid,output logic s_ready,
 input logic [8:0] s_window,input logic s_dilate,input logic s_user,input logic s_last,
 output logic m_valid,input logic m_ready,output logic m_pixel,output logic m_user,output logic m_last
);
 assign s_ready=!m_valid||m_ready;
 always_ff @(posedge clk) begin
  if(!rst_n) begin m_valid<=0;m_pixel<=0;m_user<=0;m_last<=0;end
  else if(s_ready) begin m_valid<=s_valid;if(s_valid) begin m_pixel<=s_dilate?(|s_window):(&s_window);m_user<=s_user;m_last<=s_last;end end
 end
endmodule
