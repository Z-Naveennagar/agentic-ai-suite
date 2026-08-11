// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_color_correction(
  input logic clk,input logic rst_n,input logic s_valid,output logic s_ready,
  input logic [23:0] s_data,input logic s_user,input logic s_last,
  output logic m_valid,input logic m_ready,output logic [23:0] m_data,
  output logic m_user,output logic m_last
);
  function automatic [7:0] clip(input integer v);
    begin if(v<0) clip=0; else if(v>255) clip=255; else clip=v[7:0]; end
  endfunction
  function automatic [23:0] correct(input logic [23:0] x);
    integer r,g,b,ro,go,bo;
    begin r=x[23:16];g=x[15:8];b=x[7:0];
      ro=(144*r-16*g+64)>>>7;go=(-8*r+136*g+64)>>>7;bo=(-16*g+144*b+64)>>>7;
      correct={clip(ro),clip(go),clip(bo)};
    end
  endfunction
  assign s_ready=!m_valid||m_ready;
  always_ff @(posedge clk) begin
    if(!rst_n) begin m_valid<=0;m_data<=0;m_user<=0;m_last<=0;end
    else if(s_ready) begin m_valid<=s_valid;if(s_valid) begin m_data<=correct(s_data);m_user<=s_user;m_last<=s_last;end end
  end
endmodule
