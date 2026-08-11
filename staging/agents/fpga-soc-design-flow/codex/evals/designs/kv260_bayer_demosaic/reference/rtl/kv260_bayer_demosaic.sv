// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_bayer_demosaic(
  input logic clk,input logic rst_n,input logic s_valid,output logic s_ready,
  input logic [71:0] s_data,input logic [1:0] s_phase,input logic s_user,input logic s_last,
  output logic m_valid,input logic m_ready,output logic [23:0] m_data,
  output logic m_user,output logic m_last
);
  function automatic [23:0] demosaic(input logic [71:0] w,input logic [1:0] phase);
    integer p0,p1,p2,p3,p4,p5,p6,p7,p8,r,g,b;
    begin
      p0=w[7:0];p1=w[15:8];p2=w[23:16];p3=w[31:24];p4=w[39:32];
      p5=w[47:40];p6=w[55:48];p7=w[63:56];p8=w[71:64];
      case(phase)
        2'd0: begin r=p4;g=(p1+p3+p5+p7)/4;b=(p0+p2+p6+p8)/4;end
        2'd1: begin g=p4;r=(p3+p5)/2;b=(p1+p7)/2;end
        2'd2: begin g=p4;r=(p1+p7)/2;b=(p3+p5)/2;end
        default: begin b=p4;g=(p1+p3+p5+p7)/4;r=(p0+p2+p6+p8)/4;end
      endcase
      demosaic={r[7:0],g[7:0],b[7:0]};
    end
  endfunction
  assign s_ready=!m_valid||m_ready;
  always_ff @(posedge clk) begin
    if(!rst_n) begin m_valid<=0;m_data<=0;m_user<=0;m_last<=0;end
    else if(s_ready) begin
      m_valid<=s_valid;
      if(s_valid) begin m_data<=demosaic(s_data,s_phase);m_user<=s_user;m_last<=s_last;end
    end
  end
endmodule
