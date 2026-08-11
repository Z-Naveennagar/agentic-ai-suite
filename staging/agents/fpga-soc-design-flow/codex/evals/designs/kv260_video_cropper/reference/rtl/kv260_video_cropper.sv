// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_video_cropper(
 input logic clk,input logic rst_n,input logic [15:0] crop_x0,input logic [15:0] crop_y0,
 input logic [15:0] crop_x1,input logic [15:0] crop_y1,input logic s_valid,output logic s_ready,
 input logic [23:0] s_data,input logic [15:0] s_x,input logic [15:0] s_y,
 output logic m_valid,input logic m_ready,output logic [23:0] m_data,output logic m_user,output logic m_last
);
 logic pixel_in_crop;
 assign pixel_in_crop=(s_x>=crop_x0)&&(s_x<crop_x1)&&(s_y>=crop_y0)&&(s_y<crop_y1);
 assign s_ready=pixel_in_crop?(!m_valid||m_ready):1'b1;
 always_ff @(posedge clk) begin
  if(!rst_n) begin m_valid<=0;m_data<=0;m_user<=0;m_last<=0;end
  else begin
   if(m_valid&&m_ready)m_valid<=0;
   if(s_valid&&s_ready&&pixel_in_crop) begin
    m_valid<=1;m_data<=s_data;m_user<=(s_x==crop_x0)&&(s_y==crop_y0);m_last<=(s_x==crop_x1-1'b1);
   end
  end
 end
endmodule
