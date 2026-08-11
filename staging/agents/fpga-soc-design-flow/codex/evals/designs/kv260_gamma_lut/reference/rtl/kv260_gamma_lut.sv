// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_gamma_lut(
  input logic clk,input logic rst_n,input logic s_valid,output logic s_ready,
  input logic [7:0] s_data,input logic s_user,input logic s_last,
  output logic m_valid,input logic m_ready,output logic [7:0] m_data,
  output logic m_user,output logic m_last
);
  function automatic [7:0] gamma(input logic [7:0] x);
    logic [16:0] square;
    begin square=x*x+17'd255;gamma=square[15:8];end
  endfunction
  assign s_ready=!m_valid||m_ready;
  always_ff @(posedge clk) begin
    if(!rst_n) begin m_valid<=0;m_data<=0;m_user<=0;m_last<=0;end
    else if(s_ready) begin m_valid<=s_valid;if(s_valid) begin m_data<=gamma(s_data);m_user<=s_user;m_last<=s_last;end end
  end
endmodule
