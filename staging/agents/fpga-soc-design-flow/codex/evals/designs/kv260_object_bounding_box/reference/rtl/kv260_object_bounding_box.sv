// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

module kv260_object_bounding_box(
 input logic clk,input logic rst_n,input logic s_valid,output logic s_ready,
 input logic s_foreground,input logic [15:0] s_x,input logic [15:0] s_y,
 input logic s_frame_first,input logic s_frame_last,
 output logic m_valid,input logic m_ready,output logic m_found,
 output logic [15:0] m_x_min,output logic [15:0] m_y_min,
 output logic [15:0] m_x_max,output logic [15:0] m_y_max
);
 logic have;logic [15:0] x_min,y_min,x_max,y_max;
 assign s_ready=!m_valid||m_ready;
 always_ff @(posedge clk) begin
  if(!rst_n) begin
   have<=0;x_min<=0;y_min<=0;x_max<=0;y_max<=0;
   m_valid<=0;m_found<=0;m_x_min<=0;m_y_min<=0;m_x_max<=0;m_y_max<=0;
  end else begin
   if(m_valid&&m_ready) m_valid<=0;
   if(s_valid&&s_ready) begin
    if(s_frame_first) begin
     have<=s_foreground;
     x_min<=s_foreground?s_x:0;y_min<=s_foreground?s_y:0;
     x_max<=s_foreground?s_x:0;y_max<=s_foreground?s_y:0;
    end else if(s_foreground) begin
     if(!have) begin have<=1;x_min<=s_x;y_min<=s_y;x_max<=s_x;y_max<=s_y;end
     else begin
      if(s_x<x_min)x_min<=s_x;if(s_y<y_min)y_min<=s_y;
      if(s_x>x_max)x_max<=s_x;if(s_y>y_max)y_max<=s_y;
     end
    end
    if(s_frame_last) begin
     m_valid<=1;
     if(s_frame_first) begin
      m_found<=s_foreground;
      m_x_min<=s_foreground?s_x:0;m_y_min<=s_foreground?s_y:0;
      m_x_max<=s_foreground?s_x:0;m_y_max<=s_foreground?s_y:0;
     end else if(have||s_foreground) begin
      m_found<=1;
      m_x_min<=!have?s_x:((s_foreground&&s_x<x_min)?s_x:x_min);
      m_y_min<=!have?s_y:((s_foreground&&s_y<y_min)?s_y:y_min);
      m_x_max<=!have?s_x:((s_foreground&&s_x>x_max)?s_x:x_max);
      m_y_max<=!have?s_y:((s_foreground&&s_y>y_max)?s_y:y_max);
     end else begin m_found<=0;m_x_min<=0;m_y_min<=0;m_x_max<=0;m_y_max<=0;end
    end
   end
  end
 end
endmodule
