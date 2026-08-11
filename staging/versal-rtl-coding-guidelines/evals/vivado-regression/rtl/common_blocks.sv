`timescale 1ns/1ps
`default_nettype none

module reset_sync (
  input  wire logic clk,
  input  wire logic arst,
  output logic rst
);
  (* ASYNC_REG = "TRUE" *) logic [1:0] pipe;
  always_ff @(posedge clk or posedge arst) begin
    if (arst) pipe <= 2'b11;
    else      pipe <= {pipe[0], 1'b0};
  end
  assign rst = pipe[1];
endmodule

module memory_suite (
  input  wire logic        clk,
  input  wire logic        rst,
  input  wire logic        en,
  input  wire logic        we,
  input  wire logic [11:0] addr,
  input  wire logic [63:0] wdata,
  input  wire logic        inject_sbit,
  input  wire logic        inject_dbit,
  output logic [31:0] bram_rdata,
  output logic [63:0] uram_rdata,
  output logic [63:0] ecc_rdata,
  output logic        ecc_sbit,
  output logic        ecc_dbit
);
  (* ram_style = "block" *) logic [31:0] bram [0:1023];
  (* ram_style = "ultra" *) logic [63:0] uram [0:4095];
  logic [63:0] uram_array_q;

  always_ff @(posedge clk) begin
    if (en) begin
      if (we) begin
        bram[addr[9:0]] <= wdata[31:0];
        uram[addr]      <= wdata;
      end
      bram_rdata  <= bram[addr[9:0]];
      uram_array_q <= uram[addr];
      uram_rdata  <= uram_array_q;
    end
  end

  xpm_memory_sdpram #(
    .ADDR_WIDTH_A(10),
    .ADDR_WIDTH_B(10),
    .AUTO_SLEEP_TIME(0),
    .BYTE_WRITE_WIDTH_A(64),
    .CASCADE_HEIGHT(0),
    .CLOCKING_MODE("common_clock"),
    .ECC_BIT_RANGE("[7:0]"),
    .ECC_MODE("both_encode_and_decode"),
    .ECC_TYPE("none"),
    .IGNORE_INIT_SYNTH(0),
    .MEMORY_INIT_FILE("none"),
    .MEMORY_INIT_PARAM("0"),
    .MEMORY_OPTIMIZATION("true"),
    .MEMORY_PRIMITIVE("block"),
    .MEMORY_SIZE(65536),
    .MESSAGE_CONTROL(0),
    .RAM_DECOMP("auto"),
    .READ_DATA_WIDTH_B(64),
    .READ_LATENCY_B(2),
    .READ_RESET_VALUE_B("0"),
    .RST_MODE_A("SYNC"),
    .RST_MODE_B("SYNC"),
    .SIM_ASSERT_CHK(1),
    .USE_EMBEDDED_CONSTRAINT(0),
    .USE_MEM_INIT(0),
    .USE_MEM_INIT_MMI(0),
    .WAKEUP_TIME("disable_sleep"),
    .WRITE_DATA_WIDTH_A(64),
    .WRITE_MODE_B("read_first"),
    .WRITE_PROTECT(1)
  ) u_ecc_mem (
    .dbiterrb(ecc_dbit),
    .doutb(ecc_rdata),
    .sbiterrb(ecc_sbit),
    .addra(addr[9:0]),
    .addrb(addr[9:0]),
    .clka(clk),
    .clkb(clk),
    .dina(wdata),
    .ena(en),
    .enb(en),
    .injectdbiterra(inject_dbit),
    .injectsbiterra(inject_sbit),
    .regceb(1'b1),
    .rstb(rst),
    .sleep(1'b0),
    .wea(we)
  );
endmodule

module dsp_timing_suite (
  input  wire logic               clk,
  input  wire logic               rst,
  input  wire logic               valid_in,
  input  wire logic signed [15:0] a,
  input  wire logic signed [15:0] b,
  input  wire logic signed [15:0] c,
  input  wire logic signed [15:0] d,
  output logic               valid_out,
  output logic signed [47:0] result
);
  logic signed [15:0] a_q, b_q, c_q, d_q;
  (* use_dsp = "yes" *) logic signed [31:0] m0_q, m1_q;
  logic signed [32:0] sum_q;
  logic [3:0] valid_q;

  always_ff @(posedge clk) begin
    a_q <= a;
    b_q <= b;
    c_q <= c;
    d_q <= d;
    m0_q <= a_q * b_q;
    m1_q <= c_q * d_q;
    sum_q <= m0_q + m1_q;
    result <= {{15{sum_q[32]}}, sum_q};
    if (rst) valid_q <= '0;
    else     valid_q <= {valid_q[2:0], valid_in};
  end
  assign valid_out = valid_q[3];
endmodule

module safe_control_fsm (
  input  wire logic       clk,
  input  wire logic       rst,
  input  wire logic       start,
  input  wire logic       done,
  output logic [2:0] state_status
);
  typedef enum logic [2:0] {IDLE=3'b000, LOAD=3'b001, RUN=3'b010, DONE=3'b100} state_t;
  (* FSM_ENCODING = "auto", FSM_SAFE_STATE = "default_state" *) state_t state_q, state_d;

  always_ff @(posedge clk) begin
    if (rst) state_q <= IDLE;
    else     state_q <= state_d;
  end

  always_comb begin
    state_d = state_q;
    unique case (state_q)
      IDLE: if (start) state_d = LOAD;
      LOAD:            state_d = RUN;
      RUN:  if (done)  state_d = DONE;
      DONE:            state_d = IDLE;
      default:         state_d = IDLE;
    endcase
  end
  assign state_status = state_q;
endmodule

module tmr_supervisor (
  input  wire logic       clk,
  input  wire logic       rst,
  input  wire logic       update,
  input  wire logic [7:0] status_in,
  input  wire logic [2:0] fault_inject,
  output logic [7:0] voted_status,
  output logic       disagreement
);
  (* DONT_TOUCH = "TRUE" *) logic [7:0] copy_a, copy_b, copy_c;
  always_ff @(posedge clk) begin
    if (rst) begin
      copy_a <= '0;
      copy_b <= '0;
      copy_c <= '0;
    end else if (update) begin
      copy_a <= status_in ^ {8{fault_inject[0]}};
      copy_b <= status_in ^ {8{fault_inject[1]}};
      copy_c <= status_in ^ {8{fault_inject[2]}};
    end
  end
  assign voted_status = (copy_a & copy_b) | (copy_a & copy_c) | (copy_b & copy_c);
  assign disagreement = (copy_a != copy_b) || (copy_a != copy_c) || (copy_b != copy_c);
endmodule

module key_zeroize_store (
  input  wire logic         clk,
  input  wire logic         rst,
  input  wire logic         load,
  input  wire logic         zeroize,
  input  wire logic [127:0] key_in,
  output logic [31:0]  key_digest,
  output logic         key_valid
);
  logic [127:0] key_q;
  always_ff @(posedge clk) begin
    if (rst || zeroize) begin
      key_q <= '0;
      key_valid <= 1'b0;
    end else if (load) begin
      key_q <= key_in;
      key_valid <= 1'b1;
    end
  end
  assign key_digest = key_q[31:0] ^ key_q[63:32] ^ key_q[95:64] ^ key_q[127:96];
endmodule

module link_gearbox (
  input  wire logic        clk,
  input  wire logic        rst,
  input  wire logic        aligned,
  input  wire logic        in_valid,
  input  wire logic [31:0] in_data,
  output logic        out_valid,
  output logic [63:0] out_data
);
  logic half_full;
  logic [31:0] first_half;
  always_ff @(posedge clk) begin
    if (rst || !aligned) begin
      half_full <= 1'b0;
      out_valid <= 1'b0;
      out_data <= '0;
    end else begin
      out_valid <= 1'b0;
      if (in_valid) begin
        if (!half_full) begin
          first_half <= in_data;
          half_full <= 1'b1;
        end else begin
          out_data <= {in_data, first_half};
          out_valid <= 1'b1;
          half_full <= 1'b0;
        end
      end
    end
  end
endmodule

`default_nettype wire
