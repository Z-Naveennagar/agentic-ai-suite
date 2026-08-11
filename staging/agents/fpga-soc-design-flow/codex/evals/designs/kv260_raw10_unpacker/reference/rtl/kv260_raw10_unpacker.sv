// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_raw10_unpacker(
  input logic clk,input logic rst_n,input logic s_valid,output logic s_ready,
  input logic [39:0] s_data,input logic s_user,input logic s_last,
  output logic m_valid,input logic m_ready,output logic [63:0] m_data,
  output logic m_user,output logic m_last
);
  logic [15:0] p0,p1,p2,p3;
  always_comb begin
    p0={6'b0,s_data[7:0],s_data[33:32]};
    p1={6'b0,s_data[15:8],s_data[35:34]};
    p2={6'b0,s_data[23:16],s_data[37:36]};
    p3={6'b0,s_data[31:24],s_data[39:38]};
  end
  assign s_ready=!m_valid||m_ready;
  always_ff @(posedge clk) begin
    if(!rst_n) begin m_valid<=0;m_data<='0;m_user<=0;m_last<=0; end
    else if(s_ready) begin
      m_valid<=s_valid;
      if(s_valid) begin m_data<={p3,p2,p1,p0};m_user<=s_user;m_last<=s_last; end
    end
  end
endmodule
