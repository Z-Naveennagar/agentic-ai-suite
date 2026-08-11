# Validation Workflow (Stage 5)

## Project Directory Structure

Create the following under `<ABSOLUTE_PATH>/designs/`:

```
designs/
├── utility_scripts/
│   ├── extract_aie_resources.py
│   ├── extract_latency.py
│   └── extract_throughput.py
└── <IP_NAME>_<ROW_NO>_<throughput_value>/
    ├── src/
    │   ├── fft_128_graph.h
    │   └── fft_128_app.cpp
    ├── Makefile
    ├── aie.cfg
    ├── gen_vectors.m        (FFT-specific only)
    └── regression.m         (FFT-specific only)
```

## Step 5a: Generate Graph Code (fft_ifft_dit_1ch)

### graph.h Template

Replace placeholders with values from the selected CSV row. `TP_SHIFT` = `log2(TP_POINT_SIZE)`.

```cpp
//
// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT
//

#pragma once

#include <adf.h>
#include <vector>

#include <fft_ifft_dit_1ch_graph.hpp>

using namespace adf;
namespace dsplib = xf::dsp::aie::fft::dit_1ch;

class fft_ifft_dit_1ch_graph : public graph {
public:
  static constexpr int  WIN_SIZE = <TP_WINDOW_SIZE>;
  typedef <TT_DATA>                             TT_TYPE;
  typedef <TT_TWIDDLE>                          TT_TWIDDLE;
  static constexpr int  TP_POINT_SIZE         = <TP_POINT_SIZE>;
  static constexpr int  TP_FFT_NIFFT          = <TP_FFT_NIFFT>;
  static constexpr int  TP_SHIFT              = <log2(TP_POINT_SIZE)>;
  static constexpr int  TP_CASC_LEN           = <TP_CASC_LEN>;
  static constexpr int  TP_DYN_PT_SIZE        = <TP_DYN_PT_SIZE>;
  static constexpr int  TP_WINDOW_SIZE        = WIN_SIZE;
  static constexpr int  TP_API                = <TP_API>;
  static constexpr int  TP_PARALLEL_POWER     = <TP_PARALLEL_POWER>;
  static constexpr int  NPORTS_IO             = 1 << ((TP_API == 0) ? TP_PARALLEL_POWER : (TP_PARALLEL_POWER+1));

  std::array<port< input>,NPORTS_IO> sig_i;
  std::array<port<output>,NPORTS_IO> sig_o;

  using TT_FFT = dsplib::fft_ifft_dit_1ch_graph<TT_TYPE,TT_TWIDDLE,TP_POINT_SIZE,TP_FFT_NIFFT,TP_SHIFT,
                                                TP_CASC_LEN,TP_DYN_PT_SIZE,TP_WINDOW_SIZE,TP_API,
                                                TP_PARALLEL_POWER>;
  TT_FFT fft;

  fft_ifft_dit_1ch_graph(void)
  {
    for (int ii=0; ii < NPORTS_IO; ii++) {
      connect<stream,stream>( sig_i[ii],   fft.in[ii] );
      connect<stream,stream>( fft.out[ii], sig_o[ii]  );
    }
  }
};
```

### graph.cpp (Testbench) Template

The graph header filename should match the graph.h file generated above (always `fft_128_graph.h`).

```cpp
//
// Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT
//

#include <iostream>
#include "fft_128_graph.h"

using TT_DUT = fft_ifft_dit_1ch_graph;

class dut_graph : public graph {
public:
  TT_DUT dut;
  std::array< input_plio,TT_DUT::NPORTS_IO> sig_i;
  std::array<output_plio,TT_DUT::NPORTS_IO> sig_o;
  dut_graph(void)
  {
    for (int ii=0; ii < TT_DUT::NPORTS_IO; ii++) {
      std::string fname_i = "data/sig_i_" + std::to_string(ii) + ".txt";
      std::string fname_o = "data/sig_o_" + std::to_string(ii) + ".txt";
      std::string pname_i = "PLIO_i_" + std::to_string(ii);
      std::string pname_o = "PLIO_o_" + std::to_string(ii);
      sig_i[ii] =  input_plio::create(pname_i,plio_64_bits,fname_i);
      sig_o[ii] = output_plio::create(pname_o,plio_64_bits,fname_o);
      connect<stream,stream>( sig_i[ii].out[0],  dut.sig_i[ii]   );
      connect<stream,stream>( dut.sig_o[ii],     sig_o[ii].in[0] );
    }
  }
};

dut_graph aie_dut;

int main(void)
{
  aie_dut.init();
  aie_dut.run(4);
  aie_dut.end();

  return 0;
}
```

### aie.cfg

```
[aie]
kernel-linting=true
xlopt=1
verbose=true
pl-freq=625
Xmapper=BufferOptLevel9
```

Place `graph.h` and `graph.cpp` under `<project_dir>/src/`.
Place `aie.cfg` in `<project_dir>/`.

## Step 5b: Platform Selection

**Agent must ask the user before creating the Makefile.** Present these options:

```
Before creating the Makefile, which platform option do you want?
1. Use the default platform: <PLATFORM_NAME>
2. Enter a different platform name
3. Use a PART number instead
```

### Default Platforms

| AIE Variant | Default Platform |
|-------------|-----------------|
| AIE | `xilinx_vck190_base_202520_1` |
| AIE-ML | `xilinx_vek280_base_202520_1` |
| AIE-MLv2 | `vek385_base_revb` |

Wait for user response before proceeding. After receiving the choice, inform the user which platform/part will be used.

## Step 5c: Makefile Generation

### Makefile Template (Option 1 or 2: Platform-based)

Replace `<PLATFORM_USE>` with the platform name. Replace `<MY_APP>` with `fft_128_app`.

```makefile
 #
 # Copyright 2021 Xilinx, Inc.
 #
 # Licensed under the Apache License, Version 2.0 (the "License");
 # you may not use this file except in compliance with the License.
 # You may obtain a copy of the License at
 #
 #     http://www.apache.org/licenses/LICENSE-2.0
 #
 # Unless required by applicable law or agreed to in writing, software
 # distributed under the License is distributed on an "AS IS" BASIS,
 # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 # See the License for the specific language governing permissions and
 # limitations under the License.
 #

SIM_FIFO          := false

SRC_DIR           := src
MY_APP            := fft_128_app
MY_SOURCES        := ${SRC_DIR}/${MY_APP}.cpp ${SRC_DIR}/fft_128_graph.h

PLATFORM_USE	  := <PLATFORM_USE>
PLATFORM          := --platform=${PLATFORM_REPO_PATHS}/${PLATFORM_USE}/${PLATFORM_USE}.xpfm

CHECK_FIFO        := --evaluate-fifo-depth -Xrouter=disablePathBalancing

DSPLIB_OPTS 	  := --include=${DSPLIB_ROOT}/L2/include/aie \
		     		 --include=${DSPLIB_ROOT}/L1/include/aie \
		     	     --include=${DSPLIB_ROOT}/L1/src/aie \
		     	     --include=${SRC_DIR}

PROJ_DIR          ?= .
DATATYPE          ?= cint16
PLIO_WIDTH        ?= 64

AIE_OUTPUT := libadf.a

AIE_FLAGS :=	${DSPLIB_OPTS} ${PLATFORM} ${SRC_DIR}/${MY_APP}.cpp --aie.output-archive=${AIE_OUTPUT}

ifeq (${SIM_FIFO}, true)
	AIE_FLAGS := ${AIE_FLAGS} ${CHECK_FIFO}
endif

.PHONY: help clean x86compile x86sim sim profile check_sim_output_x86 check_sim_output_aie extract-latency extract-resources extract-throughput analyze

help::
	@echo "Makefile Usage:"
	@echo "  make all"
	@echo "      Command to generate everything for this design"
	@echo ""
	@echo "  make compile"
	@echo "      Run AIE compiler and build the design"
	@echo ""
	@echo "  make profile"
	@echo "      Run AIE simulator with profiling and generate outputs suitable for Vitis Analyzer"
	@echo ""
	@echo "  make analyze"
	@echo "      Run Vitis Analyzer to inspect results"
	@echo ""
	@echo "  make check_sim_output_x86"
	@echo "    Verify x86 simulation results"
	@echo ""
	@echo "  make check_sim_output_aie"
	@echo "    Verify AIE simulation results"
	@echo ""
	@echo "  make extract-latency"
	@echo "    Extract latency metrics from AIE simulation"
	@echo ""
	@echo "  make extract-resources"
	@echo "    Extract AIE resource utilization"
	@echo ""
	@echo "  make extract-throughput"
	@echo "    Extract throughput metrics from AIE simulation"
	@echo ""
	@echo "  make clean"
	@echo "    Remove all generated files"

all:	compile profile check_sim_output_aie extract-latency extract-throughput extract-resources

x86all: x86compile x86sim check_sim_output_x86

gen_vectors:
	@echo "Generating test data with MATLAB..."
	matlab -batch "gen_vectors"

x86compile:
	v++ -c --mode aie --target=x86sim --config aie.cfg $(AIE_FLAGS) |& tee log

x86sim:
	@echo "Running x86 simulation..."
	x86simulator |& tee -a log

compile: ${MY_SOURCES}
	v++ -c --mode aie --target=hw --config aie.cfg $(AIE_FLAGS) |& tee log

sim:
	@echo "Running AIE simulation..."
	aiesimulator |& tee -a log

profile:
	@echo "Running AIE simulation with profiling..."
	aiesimulator --profile --online -wdb -ctf |& tee -a log

check_sim_output_x86:
	@echo "Checking x86 simulation output..."
	matlab -batch regression

check_sim_output_aie:
	@echo "Checking AIE simulation output..."
	matlab -batch "regression(0)"

extract-latency:
	@echo "Extracting latency metrics using Vitis Python API..."
	vitis -s ../utility_scripts/extract_latency.py .

extract-resources:
	@echo ""
	@echo "Usage: python3 ../utility_scripts/extract_aie_resources.py <project_folder_name>"
	@echo "Default: Uses the <proj_dir> as current directory"
	@echo "To select a different project directory, use: make extract-resources PROJ_DIR=<project_folder_name>"
	@echo ""
	@echo "Extracting AIE resource utilization metrics..."
	@echo ""
	python3 ../utility_scripts/extract_aie_resources.py $(PROJ_DIR)

extract-throughput:
	
	@echo ""
	@echo "Usage: python3 extract_throughput.py <proj_dir> <datatype> <plio_width>"
	@echo "<proj_dir>: single_tile or multi_tile"
	@echo "<datatype>: float, cfloat, cint16, etc."
	@echo "<plio_width>: 32, 64, 128 (PLIO width in bits)"
	@echo "Example: python3 extract_throughput.py <proj_dir> <datatype> <plio_width>"
	@echo ""
	@echo "Default: Uses the <proj_dir> as current directory and <datatype> as cint16 and <plio_width> as 64"
	@echo ""
	@echo "Extracting throughput metrics..."
	@echo ""
	python3 ../utility_scripts/extract_throughput.py $(PROJ_DIR) $(DATATYPE) $(PLIO_WIDTH)

analyze:
	vitis_analyzer aiesimulator_output/default.aierun_summary

clean:
	rm -rf .Xil Work libadf.a
	rm -rf aiesimulator_output* aiesimulator*.log
	rm -rf x86simulator_output*
	rm -rf log log*
	rm -rf *.xpe *.elf *.db *.soln Map_* xnw* *.lp *.log .xil .Xil *.lp *.db *.log *.exe *.vcd *.json
	rm -rf vitis_analyzer* pl_sample_counts* pl_sample_count_*
	rm -rf temp ISS_RPC_SERVER_PORT .crashReporter .AIE_SIM_CMD_LINE_OPTIONS
	rm -rf system*.* trdata.aiesim function_wdb_dir
	@rm -rf Work* .Xil function_wdb_dir .crashReporter .AIE_SIM_CMD_LINE_OPTIONS
	@rm -rf AIECompiler.log xcd.log log aiesimulator_output x86simulator_output
	@rm -rf libadf.a sol.db Map_Report.csv AIESimulator.log pl_sample_counts
	@rm -rf ISS_RPC_SERVER_PORT system_flat.wcfg system.wcfg system.wdb
	@rm -rf tmp.vcd.vcd trdata.aiesim vcdanalyze.log vitis_analyzer_pid* logs
	@rm -rf VCDAnalyze.log plio_throughput_info.json qemu_rp.log .wsdata _ide
	@rm -rf diag_report.log xsc_report.log vitis_analyzer.* throughput_info.json
	@rm -rf  matlab/AIECompiler.log matlab/vfs_work matlab/.Xil
	@echo "Clean complete."
```

### Makefile Modification for Option 3 (PART number)

If the user selects option 3 (use a PART number), replace the `PLATFORM_USE` and `PLATFORM` lines with:

```makefile
PART              ?= <USER_PART_NUMBER>
```

And change `AIE_FLAGS` to use `--part` instead of `${PLATFORM}`:

```makefile
AIE_FLAGS :=	${DSPLIB_OPTS} --part=${PART} ${SRC_DIR}/${MY_APP}.cpp --aie.output-archive=${AIE_OUTPUT}
```

Remove the `PLATFORM_USE` and `PLATFORM` variable lines entirely when using PART mode.

## Step 5d: Utility Scripts

Read and copy these files from their source location to `<ABSOLUTE_PATH>/designs/utility_scripts/`:

| Script | Source Location |
|--------|----------------|
| `extract_aie_resources.py` | `/group/techsup/cbalakr/various_tasks/config_qor_helper/utility_scripts/extract_aie_resources.py` |
| `extract_latency.py` | `/group/techsup/cbalakr/various_tasks/config_qor_helper/utility_scripts/extract_latency.py` |
| `extract_throughput.py` | `/group/techsup/cbalakr/various_tasks/config_qor_helper/utility_scripts/extract_throughput.py` |

Read each file from the source location and create it in the destination.

## Step 5e: FFT-Specific Test Vectors (fft_ifft_dit_1ch only)

**IMPORTANT**: Inform the user that this step is only for IP "fft_ifft_dit_1ch".

### gen_vectors.m Template

Replace `<TP_POINT_SIZE>`, `<TP_WINDOW_SIZE>`, `<TP_PARALLEL_POWER>`, `<TP_SHIFT>`, `<TP_API>` with values from the selected configuration row.

```matlab
%
% Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
% SPDX-License-Identifier: MIT
%

clear all;
close all;
rng(1);

TP_POINT_SIZE = <TP_POINT_SIZE>;
TP_WINDOW_SIZE = <TP_WINDOW_SIZE>;
TP_PARALLEL_POWER = <TP_PARALLEL_POWER>;
TP_SHIFT = <TP_SHIFT>;
TP_API = <TP_API>;

if (TP_API == 0)
  NportsI = bitshift(1, TP_PARALLEL_POWER);
  NportsO = bitshift(1, TP_PARALLEL_POWER);
else
  NportsI = bitshift(1, TP_PARALLEL_POWER + 1);
  NportsO = bitshift(1, TP_PARALLEL_POWER + 1);
end

[~,~,~] = mkdir('png');

% Generate Test Signal
Fs_Msps = 1000;

A1 = 0.3;
A2 = 0.5;
A = A1 + A2;
Ftone1_MHz = 50;
Ftone2_MHz = 200;

WIN_SIZE = TP_WINDOW_SIZE;
Nsamp = 4 * WIN_SIZE;
tone1 = A1 * exp(1i*2*pi*Ftone1_MHz/Fs_Msps*[0:Nsamp-1]);
tone2 = A2 * exp(1i*2*pi*Ftone2_MHz/Fs_Msps*[0:Nsamp-1]);
sig_i = tone1 + tone2;

sig_i_fxp  = fi(sig_i,1,16,15,'RoundingMethod','Nearest','OverflowAction','Saturate');
sig_i_flt = double(sig_i_fxp);

figure;
subplot(2,1,1); plot(real(sig_i_flt),'b.-');
xlabel('Sample Index'); ylabel('Real part'); title('FFT Input Signal');
axis([1,256,-A,+A]);
subplot(2,1,2); plot(imag(sig_i_flt),'r.-');
xlabel('Sample Index'); ylabel('Imag part'); title('FFT Input Signal');
axis([1,256,-A,+A]);
saveas(gcf,'png/fft_input.png');

% Compute Expected FFT Output
scale = 0.5^TP_SHIFT;
Nfft = TP_POINT_SIZE;

tmp = reshape(sig_i_flt,Nfft,[]);
fft_o = scale*fft(tmp,[],1);
fft_o_fxp = fi(fft_o,1,16,15,'RoundingMethod','Nearest','OverflowAction','Saturate');
fft_o_flt = double(fft_o_fxp);

figure;
ff = linspace(0,Fs_Msps,1+Nfft); ff = ff(1:end-1);
subplot(2,1,1);
plot(ff,abs(fft_o_flt(:,2)),'b.-');
xlabel('Frequency (MHz)'); ylabel('Magnitude'); grid on;
title('FFT Output Spectrum');
xline(Ftone1_MHz,'r--','LineWidth',1.5);
xline(Ftone2_MHz,'r--','LineWidth',1.5);
subplot(2,1,2);
plot(ff,angle(fft_o_flt(:,2)),'b.-');
xlabel('Frequency (MHz)'); ylabel('Phase (rad)'); grid on;
title('FFT Output Phase');
saveas(gcf,'png/fft_spectrum.png');

% Save Test Vectors for AIE Simulation
[~,~,~] = mkdir('data');

for pp = 1 : NportsI
  fid = fopen(sprintf('data/sig_i_%d.txt',pp-1),'w');
  data = sig_i_fxp(pp:NportsI:end);
  for ii = 1 : 2 : numel(data)
    fprintf(fid,'%d %d %d %d\n',...
            real(data(ii+0)).int,imag(data(ii+0)).int,...
            real(data(ii+1)).int,imag(data(ii+1)).int);
  end
  fclose(fid);
end

for pp = 1 : NportsO
  fid = fopen(sprintf('data/fft_o_%d.txt',pp-1),'w');
  data = fft_o_fxp(pp:NportsO:end);
  for ii = 1 : 2 : numel(data)
    fprintf(fid,'%d %d %d %d\n',...
            real(data(ii+0)).int,imag(data(ii+0)).int,...
            real(data(ii+1)).int,imag(data(ii+1)).int);
  end
  fclose(fid);
end

fprintf('Test vectors generated successfully!\n');
fprintf('FFT Point Size: %d\n', TP_POINT_SIZE);
fprintf('Window Size: %d\n', TP_WINDOW_SIZE);
fprintf('Number of Input Ports: %d\n', NportsI);
fprintf('Number of Output Ports: %d\n', NportsO);
```

### regression.m Template

The regression file has **port-dependent sections** that scale with `NPORTS_IO`. The number of ports (`NportsI`) is determined from the gen_vectors.m configuration:
- If `TP_API == 0`: `NPORTS_IO = 2^TP_PARALLEL_POWER`
- If `TP_API == 1`: `NPORTS_IO = 2^(TP_PARALLEL_POWER + 1)`

For each port index `0` to `NPORTS_IO-1`, generate:
1. A load line for simulation output: `fft_<N> = load_aiesim('<sim_dir>/data/sig_o_<N>.txt','int',1);`
2. A load line for golden data: `fft_<N>_g = load_aiesim('data/fft_o_<N>.txt','int',1);`
3. An error computation: `err_fft_<N> = fft_<N> - fft_<N>_g(1:numel(fft_<N>));`
4. An error print: `fprintf(1,'Max err fft_o_<N>: %d\n',max(abs(err_fft_<N>)));`
5. A pass/fail check: `max(abs(real(err_fft_<N>))) <= 2 && max(abs(imag(err_fft_<N>))) <= 2`

Below is the template for 8 ports (adapt port count to match NPORTS_IO):

```matlab
%
% Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
% SPDX-License-Identifier: MIT
%

function regression(x86,do_plot)
   if     (nargin == 0) x86 = 1; do_plot = 0;
   elseif (nargin == 1)          do_plot = 0;
   elseif (nargin ~= 2)          error('Incorrect');
   end

   if (x86)
     % Load x86 simulation output for each port (0 to NPORTS_IO-1)
     fft_0 = load_aiesim('x86simulator_output/data/sig_o_0.txt','int',1);
     fft_1 = load_aiesim('x86simulator_output/data/sig_o_1.txt','int',1);
     % ... repeat for all ports up to NPORTS_IO-1 ...
   else
     % Load AIE simulation output for each port
     fft_0 = load_aiesim('aiesimulator_output/data/sig_o_0.txt','int',1);
     fft_1 = load_aiesim('aiesimulator_output/data/sig_o_1.txt','int',1);
     % ... repeat for all ports up to NPORTS_IO-1 ...
   end

   % Load golden reference data for each port
   fft_0_g = load_aiesim('data/fft_o_0.txt','int',1);
   fft_1_g = load_aiesim('data/fft_o_1.txt','int',1);
   % ... repeat for all ports up to NPORTS_IO-1 ...

   if (do_plot == 1)
     if (x86 == 1) tag='x86sim'; else tag='aiesim'; end
     figure;
     A = 2^15*0.6;
     subplot(2,2,1); plot(real(fft_0_g),'b.-'); hold on; plot(real(fft_0),'r.--'); hold off; axis([1,128,-A,A]);
     xlabel('Sample Index'); ylabel('Real');
     title(sprintf('Filter #1 ''%s'' Output',tag));
     legend('Gold','Actual');
     subplot(2,2,3); plot(imag(fft_0_g),'b.-'); hold on; plot(imag(fft_0),'r.--'); hold off; axis([1,128,-A,A]);
     xlabel('Sample Index'); ylabel('Imag');
     legend('Gold','Actual');
     subplot(2,2,[2,4]); plot(abs(fft_1_g),'b.-'); hold on; plot(abs(fft_1),'r.--'); hold off;
     v = axis; axis([1,1024,v(3),v(4)]);
     xlabel('Sample Index'); ylabel('Magnitude');
     title('Spectrum');
     legend('Gold','Actual');
     saveas(gcf,'png/fir1_result.png');
   end

   % Compute error for each port
   err_fft_0 = fft_0 - fft_0_g;
   err_fft_1 = fft_1 - fft_1_g(1:numel(fft_1));
   % ... repeat for all ports up to NPORTS_IO-1 ...

   % Print max error per port
   fprintf(1,'Max err fft_o_0: %d\n',max(abs(err_fft_0)));
   fprintf(1,'Max err fft_o_1: %d\n',max(abs(err_fft_1)));
   % ... repeat for all ports up to NPORTS_IO-1 ...

   % Pass/fail check (tolerance <= 2)
   if ( max(abs(real(err_fft_0))) <= 2 && max(abs(imag(err_fft_0))) <= 2 && ...
        max(abs(real(err_fft_1))) <= 2 && max(abs(imag(err_fft_1))) <= 2 )
        % ... include all ports in this check ...
     fprintf(1,'--- PASSED ---\n');
   else
     fprintf(1,'*** FAILED ***\n');
   end
end

% Load AIE simulation output file
function [data] = load_aiesim( fname, dtype, is_complex )

   fid = fopen(fname,'r');
   done = 0;
   data = [];
   while ( done == 0 )
     line = fgets(fid);
     if ( line == -1 )
       done = 1;
     elseif ( strcmp(line(1),'T') == 0 )
       switch dtype
        case 'int',
         if ( is_complex == 1 )
           [X] = sscanf(line,'%d');
           data = [data;complex(X(1:2:end),X(2:2:end))];
         else
            [val] = sscanf(line,'%d');
            data = [data;val];
         end
        case 'double',
         if ( is_complex == 1 )
            [X] = sscanf(line,'%lf');
            data = [data;complex(X(1:2:end),X(2:2:end))];
         else
            [val] = sscanf(line,'%lf');
            data = [data;val];
         end
        otherwise,
         error(sprintf('Unsupported %s',dtype));
       end
     end
   end
end
```

Place `gen_vectors.m` and `regression.m` under `<ABSOLUTE_PATH>/designs/<IP_NAME>_<ROW_NO>_<throughput_value>/`.

## Step 5f: Build and Simulate

**CRITICAL**: Ask the user to provide the commands to source MATLAB and Vitis tools. Agent must NOT do this on its own.

After receiving the commands from the user, run:
```bash
make gen_vectors x86all
```

This executes:
1. `gen_vectors` — runs MATLAB to generate test vectors in `data/` directory
2. `x86compile` — compiles the AIE graph for x86 simulation
3. `x86sim` — runs x86 simulation
4. `check_sim_output_x86` — runs MATLAB regression to verify results

## Extending to Other IPs

The validation workflow structure (graph code, Makefile, utility scripts) applies to all DSP library IPs. Only the following are FFT-specific:
- `gen_vectors.m` (MATLAB test vector generation)
- `regression.m` (MATLAB simulation result verification)

For other IPs, the test vector generation and verification scripts will need IP-specific implementations. The utility scripts (`extract_aie_resources.py`, `extract_latency.py`, `extract_throughput.py`) are shared across all IPs.
