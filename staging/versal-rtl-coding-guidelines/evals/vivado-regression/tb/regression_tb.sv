`timescale 1ns/1ps
`default_nettype none

module regression_tb;
  logic clk_a = 0;
  logic clk_b = 0;
  logic arst = 1;
  logic enable = 0;
  logic zeroize = 0;
  logic [2:0] fault_inject = 0;
  logic [11:0] mem_addr = 0;
  logic mem_we = 0;
  logic [63:0] mem_wdata = 0;
  logic s_valid = 0;
  logic s_ready;
  logic [31:0] s_data = 0;
  logic [3:0] s_keep = 0;
  logic s_last = 0;
  logic s_user = 0;
  logic m_valid;
  logic m_ready = 0;
  logic [31:0] m_data;
  logic [3:0] m_keep;
  logic m_last, m_user;
  logic [127:0] status;
  logic [63:0] link_status;
  logic link_status_valid;

  logic [31:0] exp_data [0:7];
  logic [3:0] exp_keep [0:7];
  logic exp_last [0:7];
  logic exp_user [0:7];
  integer produced = 0;
  integer consumed = 0;
  integer errors = 0;
  integer link_packets = 0;
  logic [3:0] accepted_history = '0;
  logic [7:0] expected_vote = '0;
  logic test_pass = 1'b0;

  always #2.5 clk_a = ~clk_a;
  always #4.0 clk_b = ~clk_b;

  versal_recommendations_top dut (
    .clk_a(clk_a), .clk_b(clk_b), .arst(arst), .enable(enable), .zeroize(zeroize),
    .fault_inject(fault_inject), .mem_addr(mem_addr), .mem_we(mem_we), .mem_wdata(mem_wdata),
    .s_axis_tvalid(s_valid), .s_axis_tready(s_ready), .s_axis_tdata(s_data),
    .s_axis_tkeep(s_keep), .s_axis_tlast(s_last), .s_axis_tuser(s_user),
    .m_axis_tvalid(m_valid), .m_axis_tready(m_ready), .m_axis_tdata(m_data),
    .m_axis_tkeep(m_keep), .m_axis_tlast(m_last), .m_axis_tuser(m_user), .status(status),
    .link_status(link_status), .link_status_valid(link_status_valid)
  );

  function automatic logic [31:0] transform(input logic [31:0] value);
    logic [16:0] checksum;
    checksum = {1'b0, value[31:16]} + {1'b0, value[15:0]};
    return value ^ {15'h0000, checksum};
  endfunction

  task automatic send_beat(input logic [31:0] data, input logic [3:0] keep,
                           input logic last, input logic user);
    begin
      exp_data[produced] = transform(data);
      exp_keep[produced] = keep;
      exp_last[produced] = last;
      exp_user[produced] = user;
      produced = produced + 1;
      @(negedge clk_a);
      s_data = data;
      s_keep = keep;
      s_last = last;
      s_user = user;
      s_valid = 1;
      do @(posedge clk_a); while (!s_ready);
      @(negedge clk_a);
      s_valid = 0;
    end
  endtask

  always @(posedge clk_b)
    if (!arst && link_status_valid)
      link_packets = link_packets + 1;

  always @(posedge clk_a) begin
    if (arst) begin
      accepted_history <= '0;
    end else begin
      if (dut.dsp_valid !== accepted_history[3]) begin
        $display("ERROR DSP valid latency got %b expected %b", dut.dsp_valid, accepted_history[3]);
        errors = errors + 1;
      end
      accepted_history <= {accepted_history[2:0], s_valid && s_ready};
    end
    if (!arst && m_valid && m_ready) begin
      if (m_data !== exp_data[consumed] || m_keep !== exp_keep[consumed] ||
          m_last !== exp_last[consumed] || m_user !== exp_user[consumed]) begin
        $display("ERROR stream beat %0d got %h/%h/%b/%b expected %h/%h/%b/%b",
                 consumed, m_data, m_keep, m_last, m_user,
                 exp_data[consumed], exp_keep[consumed], exp_last[consumed], exp_user[consumed]);
        errors = errors + 1;
      end
      consumed = consumed + 1;
    end
  end

  initial begin
    repeat (5) @(posedge clk_a);
    arst = 0;
    enable = 1;

    @(negedge clk_a);
    mem_addr = 12'h12;
    mem_wdata = 64'h0123_4567_89AB_CDEF;
    mem_we = 1;
    @(negedge clk_a);
    mem_we = 0;

    fork
      begin
        for (int i = 0; i < 8; i++)
          send_beat(32'h1000_0000 + i, (i == 7) ? 4'b0011 : 4'hF, i == 7, i == 0);
      end
      begin
        repeat (3) @(posedge clk_a);
        for (int j = 0; j < 30; j++) begin
          @(negedge clk_a);
          m_ready = (j % 4 != 1);
        end
        m_ready = 1;
      end
    join

    wait (consumed == 8);
    repeat (4) @(posedge clk_a);
    if (dut.bram_data !== mem_wdata[31:0] || dut.uram_data !== mem_wdata || dut.ecc_data !== mem_wdata) begin
      $display("ERROR memory readback BRAM=%h URAM=%h ECC=%h expected=%h",
               dut.bram_data, dut.uram_data, dut.ecc_data, mem_wdata);
      errors = errors + 1;
    end
    s_data = 32'h0003_0002;
    mem_wdata = 64'h0000_0000_0004_0005;
    repeat (6) @(posedge clk_a);
    if ($signed(dut.dsp_result) !== 48'sd26) begin
      $display("ERROR DSP pipeline got %0d expected 26", $signed(dut.dsp_result));
      errors = errors + 1;
    end
    repeat (14) @(posedge clk_a);
    if (link_packets == 0) begin
      $display("ERROR link-domain gearbox never produced a framed word");
      errors = errors + 1;
    end
    if (dut.ax_reg0 == 0 || dut.ax_reg1 == 0) begin
      $display("ERROR AXI-Lite independent-channel generator did not update both registers: %h %h", dut.ax_reg0, dut.ax_reg1);
      errors = errors + 1;
    end

    @(negedge clk_a);
    expected_vote = dut.cycle_counter;
    fault_inject = 3'b001;
    @(posedge clk_a);
    @(negedge clk_a);
    if (!dut.tmr_disagreement) begin
      $display("ERROR TMR disagreement was not detected");
      errors = errors + 1;
    end
    if (dut.tmr_status !== expected_vote) begin
      $display("ERROR TMR voter got %h expected uncorrupted %h", dut.tmr_status, expected_vote);
      errors = errors + 1;
    end
    fault_inject = 0;
    @(posedge clk_a);

    zeroize = 1;
    @(posedge clk_a);
    zeroize = 0;
    @(posedge clk_a);
    if (dut.key_valid || dut.key_digest != 0) begin
      $display("ERROR key zeroization failed");
      errors = errors + 1;
    end

    if (errors == 0) begin
      test_pass = 1'b1;
      $display("REGRESSION_PASS beats=%0d", consumed);
      $finish;
    end else begin
      $fatal(1, "REGRESSION_FAIL errors=%0d", errors);
    end
  end
endmodule

`default_nettype wire
