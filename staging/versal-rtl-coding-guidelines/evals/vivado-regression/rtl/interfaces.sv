`timescale 1ns/1ps
`default_nettype none

module axis_elastic2 #(
  parameter int WIDTH = 38
) (
  input  wire logic             clk,
  input  wire logic             rst,
  input  wire logic             s_valid,
  output logic             s_ready,
  input  wire logic [WIDTH-1:0] s_payload,
  output logic             m_valid,
  input  wire logic             m_ready,
  output logic [WIDTH-1:0] m_payload
);
  logic [WIDTH-1:0] storage [0:1];
  logic wr_ptr, rd_ptr;
  logic [1:0] count;
  logic push, pop;

  assign s_ready = (count != 2) || m_ready;
  assign m_valid = (count != 0);
  assign m_payload = storage[rd_ptr];
  assign push = s_valid && s_ready;
  assign pop  = m_valid && m_ready;

  always_ff @(posedge clk) begin
    if (rst) begin
      wr_ptr <= 1'b0;
      rd_ptr <= 1'b0;
      count <= 2'd0;
    end else begin
      if (push) begin
        storage[wr_ptr] <= s_payload;
        wr_ptr <= ~wr_ptr;
      end
      if (pop)
        rd_ptr <= ~rd_ptr;
      unique case ({push, pop})
        2'b10: count <= count + 1'b1;
        2'b01: count <= count - 1'b1;
        default: count <= count;
      endcase
    end
  end
endmodule

module framed_stream_pipeline (
  input  wire logic        clk,
  input  wire logic        rst,
  input  wire logic        s_tvalid,
  output logic        s_tready,
  input  wire logic [31:0] s_tdata,
  input  wire logic [3:0]  s_tkeep,
  input  wire logic        s_tlast,
  input  wire logic        s_tuser,
  output logic        m_tvalid,
  input  wire logic        m_tready,
  output logic [31:0] m_tdata,
  output logic [3:0]  m_tkeep,
  output logic        m_tlast,
  output logic        m_tuser
);
  logic [16:0] checksum;
  logic [37:0] in_payload, out_payload;
  assign checksum = {1'b0, s_tdata[31:16]} + {1'b0, s_tdata[15:0]};
  assign in_payload = {s_tuser, s_tlast, s_tkeep, s_tdata ^ {15'h0000, checksum}};

  axis_elastic2 #(.WIDTH(38)) u_buffer (
    .clk(clk), .rst(rst),
    .s_valid(s_tvalid), .s_ready(s_tready), .s_payload(in_payload),
    .m_valid(m_tvalid), .m_ready(m_tready), .m_payload(out_payload)
  );

  assign {m_tuser, m_tlast, m_tkeep, m_tdata} = out_payload;
endmodule

module axi_lite_regs (
  input  wire logic        clk,
  input  wire logic        rst,
  input  wire logic [7:0]  s_awaddr,
  input  wire logic        s_awvalid,
  output logic        s_awready,
  input  wire logic [31:0] s_wdata,
  input  wire logic [3:0]  s_wstrb,
  input  wire logic        s_wvalid,
  output logic        s_wready,
  output logic [1:0]  s_bresp,
  output logic        s_bvalid,
  input  wire logic        s_bready,
  input  wire logic [7:0]  s_araddr,
  input  wire logic        s_arvalid,
  output logic        s_arready,
  output logic [31:0] s_rdata,
  output logic [1:0]  s_rresp,
  output logic        s_rvalid,
  input  wire logic        s_rready,
  output logic [31:0] register0,
  output logic [31:0] register1
);
  logic aw_hold, w_hold;
  logic [7:0] awaddr_hold;
  logic [31:0] wdata_hold;
  logic [3:0] wstrb_hold;
  logic aw_fire, w_fire, write_commit;
  logic [7:0] commit_addr;
  logic [31:0] commit_data;
  logic [3:0] commit_strb;

  function automatic logic [31:0] apply_strobes(
    input logic [31:0] old_value,
    input logic [31:0] new_value,
    input logic [3:0] strobes
  );
    logic [31:0] result;
    result = old_value;
    for (int i = 0; i < 4; i++)
      if (strobes[i]) result[i*8 +: 8] = new_value[i*8 +: 8];
    return result;
  endfunction

  assign s_awready = !aw_hold && !s_bvalid;
  assign s_wready  = !w_hold  && !s_bvalid;
  assign aw_fire = s_awvalid && s_awready;
  assign w_fire  = s_wvalid  && s_wready;
  assign write_commit = !s_bvalid && (aw_hold || aw_fire) && (w_hold || w_fire);
  assign commit_addr = aw_hold ? awaddr_hold : s_awaddr;
  assign commit_data = w_hold ? wdata_hold : s_wdata;
  assign commit_strb = w_hold ? wstrb_hold : s_wstrb;
  assign s_bresp = 2'b00;

  assign s_arready = !s_rvalid;
  assign s_rresp = 2'b00;

  always_ff @(posedge clk) begin
    if (rst) begin
      aw_hold <= 1'b0;
      w_hold <= 1'b0;
      s_bvalid <= 1'b0;
      s_rvalid <= 1'b0;
      s_rdata <= '0;
      register0 <= '0;
      register1 <= '0;
    end else begin
      if (aw_fire) begin
        aw_hold <= 1'b1;
        awaddr_hold <= s_awaddr;
      end
      if (w_fire) begin
        w_hold <= 1'b1;
        wdata_hold <= s_wdata;
        wstrb_hold <= s_wstrb;
      end
      if (write_commit) begin
        if (commit_addr == 8'h00)
          register0 <= apply_strobes(register0, commit_data, commit_strb);
        else if (commit_addr == 8'h04)
          register1 <= apply_strobes(register1, commit_data, commit_strb);
        aw_hold <= 1'b0;
        w_hold <= 1'b0;
        s_bvalid <= 1'b1;
      end else if (s_bvalid && s_bready) begin
        s_bvalid <= 1'b0;
      end

      if (s_arvalid && s_arready) begin
        unique case (s_araddr)
          8'h00: s_rdata <= register0;
          8'h04: s_rdata <= register1;
          default: s_rdata <= 32'h0;
        endcase
        s_rvalid <= 1'b1;
      end else if (s_rvalid && s_rready) begin
        s_rvalid <= 1'b0;
      end
    end
  end
endmodule

`default_nettype wire
