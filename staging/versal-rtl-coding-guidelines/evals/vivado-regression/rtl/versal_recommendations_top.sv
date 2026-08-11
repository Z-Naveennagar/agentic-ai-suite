`timescale 1ns/1ps
`default_nettype none

module versal_recommendations_top (
  input  wire logic         clk_a,
  input  wire logic         clk_b,
  input  wire logic         arst,
  input  wire logic         enable,
  input  wire logic         zeroize,
  input  wire logic [2:0]   fault_inject,
  input  wire logic [11:0]  mem_addr,
  input  wire logic         mem_we,
  input  wire logic [63:0]  mem_wdata,
  input  wire logic         s_axis_tvalid,
  output logic         s_axis_tready,
  input  wire logic [31:0]  s_axis_tdata,
  input  wire logic [3:0]   s_axis_tkeep,
  input  wire logic         s_axis_tlast,
  input  wire logic         s_axis_tuser,
  output logic         m_axis_tvalid,
  input  wire logic         m_axis_tready,
  output logic [31:0]  m_axis_tdata,
  output logic [3:0]   m_axis_tkeep,
  output logic         m_axis_tlast,
  output logic         m_axis_tuser,
  output logic [127:0] status,
  output logic [63:0]  link_status,
  output logic         link_status_valid
);
  logic rst_a, rst_b;
  logic enable_b;
  logic [31:0] bram_data;
  logic [63:0] uram_data, ecc_data;
  logic ecc_sbit, ecc_dbit;
  logic dsp_valid;
  logic signed [47:0] dsp_result;
  logic [2:0] fsm_state;
  logic [7:0] tmr_status;
  logic tmr_disagreement;
  logic [31:0] key_digest;
  logic key_valid;
  logic gearbox_valid;
  logic [63:0] gearbox_data;
  logic [7:0] cycle_counter;
  logic [31:0] link_counter;
  logic [31:0] control_diag, diagnostic_fold;

  logic [7:0] ax_awaddr, ax_araddr;
  logic [31:0] ax_wdata, ax_rdata, ax_reg0, ax_reg1;
  logic [3:0] ax_wstrb;
  logic ax_awvalid, ax_awready, ax_wvalid, ax_wready;
  logic ax_bvalid, ax_rvalid, ax_arvalid, ax_arready;
  logic [1:0] ax_bresp, ax_rresp;

  reset_sync u_reset_a (.clk(clk_a), .arst(arst), .rst(rst_a));
  reset_sync u_reset_b (.clk(clk_b), .arst(arst), .rst(rst_b));

  xpm_cdc_single #(
    .DEST_SYNC_FF(2),
    .INIT_SYNC_FF(0),
    .SIM_ASSERT_CHK(1),
    .SRC_INPUT_REG(1)
  ) u_enable_cdc (
    .src_clk(clk_a),
    .src_in(enable),
    .dest_clk(clk_b),
    .dest_out(enable_b)
  );

  memory_suite u_memory (
    .clk(clk_a), .rst(rst_a), .en(enable), .we(mem_we), .addr(mem_addr),
    .wdata(mem_wdata), .inject_sbit(fault_inject[0]), .inject_dbit(fault_inject[1]),
    .bram_rdata(bram_data), .uram_rdata(uram_data), .ecc_rdata(ecc_data),
    .ecc_sbit(ecc_sbit), .ecc_dbit(ecc_dbit)
  );

  dsp_timing_suite u_dsp (
    .clk(clk_a), .rst(rst_a), .valid_in(s_axis_tvalid && s_axis_tready),
    .a(s_axis_tdata[15:0]), .b(s_axis_tdata[31:16]),
    .c(mem_wdata[15:0]), .d(mem_wdata[31:16]),
    .valid_out(dsp_valid), .result(dsp_result)
  );

  safe_control_fsm u_fsm (
    .clk(clk_a), .rst(rst_a), .start(s_axis_tvalid), .done(m_axis_tvalid && m_axis_tready),
    .state_status(fsm_state)
  );

  tmr_supervisor u_tmr (
    .clk(clk_a), .rst(rst_a), .update(enable), .status_in(cycle_counter),
    .fault_inject(fault_inject), .voted_status(tmr_status), .disagreement(tmr_disagreement)
  );

  key_zeroize_store u_key_store (
    .clk(clk_a), .rst(rst_a), .load(mem_we), .zeroize(zeroize),
    .key_in({mem_wdata, mem_wdata ^ 64'hA5A55A5AC3C33C3C}),
    .key_digest(key_digest), .key_valid(key_valid)
  );

  framed_stream_pipeline u_domain_stream (
    .clk(clk_a), .rst(rst_a),
    .s_tvalid(s_axis_tvalid), .s_tready(s_axis_tready), .s_tdata(s_axis_tdata),
    .s_tkeep(s_axis_tkeep), .s_tlast(s_axis_tlast), .s_tuser(s_axis_tuser),
    .m_tvalid(m_axis_tvalid), .m_tready(m_axis_tready), .m_tdata(m_axis_tdata),
    .m_tkeep(m_axis_tkeep), .m_tlast(m_axis_tlast), .m_tuser(m_axis_tuser)
  );

  link_gearbox u_gearbox (
    .clk(clk_b), .rst(rst_b), .aligned(enable_b),
    .in_valid(enable_b), .in_data(link_counter),
    .out_valid(gearbox_valid), .out_data(gearbox_data)
  );

  always_ff @(posedge clk_b) begin
    if (rst_b) link_counter <= '0;
    else if (enable_b) link_counter <= link_counter + 1'b1;
  end

  always_ff @(posedge clk_a) begin
    if (rst_a) cycle_counter <= '0;
    else if (enable) cycle_counter <= cycle_counter + 1'b1;
  end

  assign ax_awvalid = (cycle_counter[3:0] == 4'h1);
  assign ax_wvalid  = (cycle_counter[3:0] == 4'h3);
  assign ax_arvalid = (cycle_counter[3:0] == 4'h8);
  assign ax_awaddr  = {5'h0, cycle_counter[4], 2'b00};
  assign ax_araddr  = ax_awaddr;
  assign ax_wdata   = {24'h0, cycle_counter};
  assign ax_wstrb   = 4'hF;

  axi_lite_regs u_axi_lite (
    .clk(clk_a), .rst(rst_a),
    .s_awaddr(ax_awaddr), .s_awvalid(ax_awvalid), .s_awready(ax_awready),
    .s_wdata(ax_wdata), .s_wstrb(ax_wstrb), .s_wvalid(ax_wvalid), .s_wready(ax_wready),
    .s_bresp(ax_bresp), .s_bvalid(ax_bvalid), .s_bready(1'b1),
    .s_araddr(ax_araddr), .s_arvalid(ax_arvalid), .s_arready(ax_arready),
    .s_rdata(ax_rdata), .s_rresp(ax_rresp), .s_rvalid(ax_rvalid), .s_rready(1'b1),
    .register0(ax_reg0), .register1(ax_reg1)
  );

  assign control_diag = {
    7'b0, fsm_state, tmr_status, key_valid, tmr_disagreement,
    ecc_sbit, ecc_dbit, dsp_valid,
    ax_awready, ax_wready, ax_bvalid, ax_arready, ax_rvalid,
    ax_bresp, ax_rresp
  };
  assign diagnostic_fold =
    bram_data ^ uram_data[31:0] ^ uram_data[63:32] ^
    ecc_data[31:0] ^ ecc_data[63:32] ^ dsp_result[31:0] ^
    {16'b0, dsp_result[47:32]} ^ ax_rdata ^ ax_reg0 ^ ax_reg1 ^ control_diag;
  assign status = {key_digest, diagnostic_fold, ax_reg0, ax_reg1};
  assign link_status = gearbox_data;
  assign link_status_valid = gearbox_valid;
endmodule

`default_nettype wire
