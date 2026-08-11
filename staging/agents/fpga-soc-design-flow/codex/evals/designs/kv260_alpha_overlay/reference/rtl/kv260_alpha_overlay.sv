// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_alpha_overlay(
 input logic clk,input logic rst_n,input logic s_valid,output logic s_ready,
 input logic [23:0] s_foreground,input logic [23:0] s_background,input logic [7:0] s_alpha,
 input logic s_user,input logic s_last,output logic m_valid,input logic m_ready,
 output logic [23:0] m_data,output logic m_user,output logic m_last
);
 function automatic [7:0] blend(input logic [7:0] fg,input logic [7:0] bg,input logic [7:0] a);
  integer n;begin n=a*fg+(255-a)*bg+127;blend=n/255;end
 endfunction
 assign s_ready=!m_valid||m_ready;
 always_ff @(posedge clk) begin
  if(!rst_n) begin m_valid<=0;m_data<=0;m_user<=0;m_last<=0;end
  else if(s_ready) begin
   m_valid<=s_valid;
   if(s_valid) begin
    m_data<={blend(s_foreground[23:16],s_background[23:16],s_alpha),blend(s_foreground[15:8],s_background[15:8],s_alpha),blend(s_foreground[7:0],s_background[7:0],s_alpha)};
    m_user<=s_user;m_last<=s_last;
   end
  end
 end
endmodule
