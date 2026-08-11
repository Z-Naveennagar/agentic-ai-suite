---
name: convert-aie-to-test-harness
description: Convert and build AIE designs for AMD Test Harness on Versal platforms (VCK190/VEK280/VEK385). Creates Python/C++/MATLAB test clients, configures PLIO interfaces, builds xclbin packages. Optionally deploys to hardware when server IP address provided.
author: Faisal El-Shabani
---

# Convert AIE Design to Test Harness

Converts AIE designs to run on Test Harness hardware platform.

## Terminology & Scope

**Understanding User Intent:**

1. **Convert/Build** - User requests "convert to Test Harness" or "build for Test Harness":
   - Create Test Harness variant files (graph, client, Makefile)
   - Run `make all TARGET=hw` to compile and package xclbin
   - Verify build success (xclbin created, no errors)
   - **DO NOT** attempt hardware deployment
   - **Success = xclbin exists with no build errors**

2. **Deploy/Test** - User requests "deploy" or "test" AND provides board IP address:
   - Perform all Convert/Build steps above
   - Construct SERVER_IP_PORT from user's IP: `SERVER_IP_PORT=<user_ip>:8080`
   - Source XRT environment on workstation/host
   - Connect client to running Test Harness server on board
   - Execute test client with SERVER_IP_PORT
   - Validate results match golden data
   - Report performance metrics
   - **Success = hardware test passes with matching results**

**Important:** User provides IP address only (e.g., `192.168.1.100`). Agent must append port `:8080` to form complete `SERVER_IP_PORT=192.168.1.100:8080`.

**Key Definitions:**

| Term | Meaning | Output |
|------|---------|--------|
| **Convert** | Create Test Harness files from original design | Modified graph.h, client/tb.*, Makefile |
| **Build/Compile** | Run `make all TARGET=hw` | xclbin package in `pkg.hw.*/` |
| **Deploy** | Run on actual hardware (requires server) | Execution logs, performance metrics |
| **Test/Validate** | Verify outputs match golden reference | Pass/Fail + max error report |

**When to Deploy:**
- ✅ User provides board IP address (e.g., `192.168.1.100`)
- ✅ User says "test on hardware", "run on board", "deploy to VEK385"
- ✅ Agent must construct `SERVER_IP_PORT=<IP>:8080` (port 8080 is always used)
- ❌ User only says "convert" or "build"
- ❌ No IP address provided
- ❌ Build is the only requirement stated

## Key Concept

**CRITICAL:** Always start by copying a Test Harness example. Never create custom Makefiles from scratch. The Test Harness build infrastructure (common.mk, scripts, configurations) is tested and required.

**Why copying is mandatory:**
- Test Harness `common.mk` provides tested build infrastructure
- Ensures GCC 9+ is used (required for C++17 support)
- Provides proper XRT library paths and compiler flags
- Handles platform-specific configuration automatically
- Includes tested build targets and package structure

## Platform Constraints

| Platform | Part Number | Input PLIOs | Output PLIOs |
|----------|-------------|-------------|--------------|
| VCK190 | xcvc1902-vsva2197-2MP-e-S | 36 | 36 |
| VEK280 | xcve2802-vsvh1760-2MP-e-S | 16 | 16 |
| VEK385 | xc2ve3858-ssva2112-2MP-e-S | 16 | 16 |

**Test Harness Requirements:**
- PLIO width: `plio_128_bits` (mandatory)
- PLIO frequency: 312.5 MHz
- PLIO naming: `PLIO_01_TO_AIE`, `PLIO_02_TO_AIE`, ... (inputs); `PLIO_01_FROM_AIE`, `PLIO_02_FROM_AIE`, ... (outputs)
- Number format: Zero-padded two digits (01, 02, not 1, 2)

## Prerequisites

Before starting conversion, ensure:

### For Build (Always Required)

1. **Environment Setup:**
   - `XILINX_VITIS` set (verify with `v++ --version`)
   - Vitis version matches Test Harness version

2. **Test Harness Repository:**
   ```bash
   # If not already available:
   git clone https://github.com/Xilinx/AI-Engine-Test-Harness
   export TEST_HARNESS_PATH=$(pwd)/AI-Engine-Test-Harness
   
   # Match Vitis version (e.g., 2025.2):
   cd $TEST_HARNESS_PATH
   git checkout v2025.2
   ```

3. **User Input Required:**
   - Target platform: VCK190, VEK280, or VEK385
   - Client type: **C++**, **MATLAB**, or **Python** (choose ONE)

4. **Python Environment (For Python Clients):**
   - Python 3 with numpy installed
   - **Option 1 - Virtual environment (recommended):**
     ```bash
     source /path/to/venv/bin/activate
     python3 -c "import numpy; print('numpy OK')"
     ```
   - **Option 2 - System-wide installation:**
     ```bash
     pip3 install numpy
     ```
   - **Note:** Test Harness Python APIs also require numpy for data handling

### For Deployment (Only When Testing on Hardware)

**Additional requirements when user requests deployment/testing:**

5. **XRT Environment:**
   - XRT must be sourced before running client
   - Source command: `source $XILINX_VITIS/settings64.sh`
   - **Note:** If XRT is not available, client will fail at runtime with library errors

6. **Test Harness Server:**
   - Board IP address provided by user (e.g., `192.168.1.100`)
   - Agent constructs full SERVER_IP_PORT: `192.168.1.100:8080` (port 8080 is standard)
   - Network connectivity to board verified: `ping -c 3 192.168.1.100` (use IP only, not port)
   - **Note:** Server must be running on board (setup is board administrator's responsibility)

**If deployment prerequisites not met:** Complete build only and inform user how to deploy manually.


## Step 1: Analyze Original Design

### Count I/O Ports

Search for PLIO declarations in user's graph files (`.cpp`, `.h`):

```cpp
// Count these patterns:
input_plio::create("name", width, "file")
output_plio::create("name", width, "file")

// Also check for arrays:
std::array<input_plio, 3> inputs;  // 3 inputs
```

**GMIO ports:** Convert to PLIO (GMIO not supported on Test Harness).

### Validate Against Platform

```
if num_inputs > platform_max_inputs:
    ERROR: "Design requires {num_inputs} inputs but {platform} supports {platform_max_inputs}"
```

### Find User Files

Identify all files needed from original design:
- Kernel headers: `*_kernel.h`
- Kernel implementations: `*_kernel.cpp`
- Graph headers: `*_graph.h`
- Graph application: `*_app.cpp` or `graph.cpp`
- Data files: `data/*.txt` or generation scripts (`gen_vectors.m`, `gen_vectors.py`)

### Extract Design Iteration Count

**Before creating the Test Harness client, determine the original design's iteration count from the graph application.**

**Find and analyze graph application file:**
```bash
# Common patterns: *_app.cpp, graph_app.cpp, graph.cpp, main.cpp
grep -r "\.run(" *.cpp
```

**Extract iteration count from .run() call:**
```cpp
// Example patterns:
dut.run(4);              // Use: 4 iterations
aie_dut.run(4);          // Use: 4 iterations  
gr.run(iterations);      // Use: 1 (or trace variable if clear)
graph.run(N);            // Use: N iterations
```

**Record as DESIGN_ITERATIONS:**
- Hardcoded value: Use that number
- Variable: Trace definition if simple, otherwise default to 1
- This value will be used for `--iterations` default in Test Harness client

**Cross-check with gen_vectors script (optional):**

If `gen_vectors.m`, `gen_vectors.py`, or `gen_vectors.ipynb` exists, look for iteration parameters:
```python
# Python/Jupyter patterns:
num_iterations = 4
iterations = 4
N_ITER = 4
```
```matlab
% MATLAB patterns:
num_iterations = 4;
iterations = 4;
```

The gen_vectors iteration count should match graph_app.cpp .run(N) for consistency, but this is user's responsibility.

## Step 2: Select Test Harness Example

### Available Examples

**C++ Client Examples:**
- `examples/vck190/adder_perf` - VCK190, single I/O
- `examples/vck190/channelizer` - VCK190, multi I/O
- `examples/vek280/adder_perf` - VEK280, single I/O
- `examples/vek385/adder_perf` - VEK385, single I/O

**MATLAB Client Examples:**
- `examples/matlab/vck190/adder` - VCK190, single I/O

**Python Client Examples:**
- `examples/python/vck190/adder` - VCK190, single I/O

### Selection Strategy

1. **Match client type** (C++, MATLAB, or Python based on user preference)
2. **Match platform** if exact example exists
3. **If no exact match:** Use closest available example
   - Example: For MATLAB + VEK280, use `matlab/vck190/adder` and change `DEVICE=vek280`
4. **Prefer simpler examples** for single I/O designs (adder over channelizer)

**Example Selection Logic:**
```
Client=MATLAB, Platform=VCK190 → examples/matlab/vck190/adder (exact match)
Client=MATLAB, Platform=VEK280 → examples/matlab/vck190/adder (adapt DEVICE)
Client=C++, Platform=VCK190, 1 I/O → examples/vck190/adder_perf
Client=C++, Platform=VCK190, 4+ I/O → examples/vck190/channelizer
```

## Step 3: Create Test Harness Design

### Copy Example (MANDATORY)

```bash
# Create output directory
mkdir Test_Harness_Design_Variant
cd Test_Harness_Design_Variant

# Copy selected example (example for C++/VCK190):
cp -r ${TEST_HARNESS_PATH}/examples/vck190/adder_perf/* .

# Verify structure:
ls -lh  # Should see: aie/ client/ data/ Makefile run_script.sh
```

**DO NOT:**
- Create custom Makefiles from scratch
- Modify Test Harness build infrastructure (common.mk)
- Change directory structure (_x_temp, pkg patterns)

### Replace AIE Design Files

```bash
# Remove example AIE files:
rm aie/*.cpp aie/*.h aie/*.cc

# Copy user's AIE files:
cp ../original_design/*_kernel.h aie/
cp ../original_design/*_kernel.cpp aie/
cp ../original_design/*_graph.h aie/

# Rename user's graph application to graph.cpp (required name):
cp ../original_design/user_app.cpp aie/graph.cpp
```

**Note:** Test Harness Makefiles expect `aie/graph.cpp` as the main AIE file.

## Step 4: Modify Graph for Test Harness

### Update PLIO Declarations

Change in `aie/graph.cpp` (or wherever PLIOs are declared):

**Single I/O Example:**
```cpp
// BEFORE:
sig_i[0] = input_plio::create("PLIO_i_0", plio_64_bits, "data/sig_i.txt");
sig_o[0] = output_plio::create("PLIO_o_0", plio_64_bits, "data/sig_o.txt");

// AFTER (Test Harness):
sig_i[0] = input_plio::create("PLIO_01_TO_AIE", plio_128_bits, "data/sig_i.txt");
sig_o[0] = output_plio::create("PLIO_01_FROM_AIE", plio_128_bits, "data/sig_o.txt");
```

**Multi-I/O Example (3 inputs, 2 outputs):**
```cpp
// Inputs:
sig_i[0] = input_plio::create("PLIO_01_TO_AIE", plio_128_bits, "data/in_0.txt");
sig_i[1] = input_plio::create("PLIO_02_TO_AIE", plio_128_bits, "data/in_1.txt");
sig_i[2] = input_plio::create("PLIO_03_TO_AIE", plio_128_bits, "data/in_2.txt");

// Outputs:
sig_o[0] = output_plio::create("PLIO_01_FROM_AIE", plio_128_bits, "data/out_0.txt");
sig_o[1] = output_plio::create("PLIO_02_FROM_AIE", plio_128_bits, "data/out_1.txt");
```

**Key Changes:**
1. Names: `PLIO_01_TO_AIE`, `PLIO_02_TO_AIE`, ... (inputs); `PLIO_01_FROM_AIE`, ... (outputs)
2. Width: Always `plio_128_bits`
3. Sequential numbering: 01, 02, 03, ... (zero-padded)

**Note on Data File Paths:**
The file paths in PLIO declarations (e.g., `"data/sig_i.txt"`) are **compilation placeholders only**. At runtime:
- **All clients (C++, MATLAB, Python):** Data is transferred programmatically via Test Harness APIs
- The actual data files are NOT read by hardware - clients send/receive data through network connection to Test Harness server
- You can use any placeholder path; it just needs to be syntactically valid for compilation

### Convert GMIO to PLIO

```cpp
// BEFORE (GMIO):
port<input> gmio_in;
port<output> gmio_out;

// AFTER (PLIO):
input_plio gmio_in = input_plio::create("PLIO_01_TO_AIE", plio_128_bits, "data/in.txt");
output_plio gmio_out = output_plio::create("PLIO_01_FROM_AIE", plio_128_bits, "data/out.txt");
```

## Step 5: Update Makefile Variables

### MANDATORY: Fix TEST_HARNESS_PATH Support

**Problem:** Test Harness example Makefiles auto-detect repository path using `${MK_PATH%/examples/*}` which ONLY works when Makefile is inside `examples/` directory. When you copy the example outside the Test Harness repo, this auto-detection fails.

**Solution:** Add TEST_HARNESS_PATH environment variable support at the top of Makefile:

```makefile
# Find these lines near top of Makefile:
MK_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
export TEST_HARNESS_REPO_PATH ?= $(shell bash -c 'export MK_PATH=$(MK_PATH); echo $${MK_PATH%/examples/*}')

# REPLACE with:
ifdef TEST_HARNESS_PATH
export TEST_HARNESS_REPO_PATH := $(TEST_HARNESS_PATH)
else
MK_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
export TEST_HARNESS_REPO_PATH ?= $(shell bash -c 'export MK_PATH=$(MK_PATH); echo $${MK_PATH%/examples/*}')
endif
```

This allows the Makefile to work both inside and outside the Test Harness repository.

### Optional: Update Platform

```makefile
# If platform needs changing (e.g., using VCK190 example for VEK280 design):
DEVICE ?= vek280  # Change from vck190 to vek280 or vek385
```

**DO NOT MODIFY:**
- `include ${TEST_HARNESS_REPO_PATH}/test_harness/common.mk` line
- Build targets (all, package, clean)
- TEMP_DIR, PKG_DIR, XCLBIN paths
- AIE_CXX_FLAGS, HOST_CXX_FLAGS definitions

## Step 6: Handle Test Data

### When User Requests "Leverage Existing I/O Files"

**If user says "use existing ./data files" or "leverage existing I/O files":**
									   
							   
						  

**Agent Actions:**
1. **Load ALL data from files** - do not truncate or subset
2. **Use DESIGN_ITERATIONS** from graph_app.cpp for default `--iterations` value  
3. **Set run_script.sh** to use `--iterations {DESIGN_ITERATIONS}`
4. **Do NOT calculate or validate per-iteration sample counts** - this is user's responsibility

**User Responsibilities:**
- Ensure data files in `./data/` contain correct number of samples for the design
- Match data file iterations with graph_app.cpp .run(N)
- If using gen_vectors script, ensure iteration parameter matches design

**Implementation Pattern (Python):**
```python
def main(args):
    # Design parameters
    NSAMP = 1024
    NNODES = 64
    DESIGN_ITERATIONS = 4  # From graph_app.cpp: dut.run(4)
    
    # Load ALL data from files (no calculation, no truncation)
    data_i_uint32 = load_bfloat16_data("../../data/data_i.txt")
    data_o_expected_uint32 = load_bfloat16_data("../../data/data_o.txt")
    
    # Create output buffer matching expected output size
    data_o_uint32 = np.zeros(len(data_o_expected_uint32), dtype=np.uint32)
    
    print(f"INFO: Loaded {len(data_i_uint32)} input uint32 values from file")
    print(f"INFO: Loaded {len(data_o_expected_uint32)} output uint32 values from file")
    print(f"INFO: Running with {args.iterations} iterations")
    
    # Setup Test Harness arguments (use actual loaded sizes)
    targs = []
    targs.append(test_harness_args(channel_index.PLIO_01_TO_AIE, 
                                  len(data_i_uint32) * 4,  # All loaded data
                                  1, 1, data_i_uint32))
    targs.append(test_harness_args(channel_index.PLIO_01_FROM_AIE, 
                                  len(data_o_uint32) * 4,  # All loaded data
                                  1, 1, data_o_uint32))
    
    # Run with requested iterations
    mgr.runAIEGraph(0, args.iterations)
    mgr.runTestHarness(mode, targs)
```

### When Generating Synthetic Data

**For designs without existing data files, generate random data scaled by iterations:**

```python
# Python example - scale by iterations
num_values = 65536 * args.iterations  # Total for all iterations
data = np.random.randint(-65536, 65536, num_values, dtype=np.int32)
```

```cpp
// C++ example - scale by iterations  
int num_values = 65536 * num_iterations;
std::vector<int32_t> data(num_values);
for (int i = 0; i < num_values; i++) {
    data[i] = rand() % 131072 - 65536;
}
```

### Optional: Create Data Files for Simulation

**Note:** Data file paths in PLIO declarations are only used for AIE simulation, not Test Harness execution.

**For 128-bit PLIOs** (required by Test Harness), use 4 samples per line for int32/float datatypes:

**Example (int32 data):**
```
# data/sig_i.txt (4 int32 values per line = 128 bits):
1 2 3 4
5 6 7 8
9 10 11 12
```

**Example (cint16 data - 2 values real/imag):**
```
# data/sig_i.txt (4 cint16 values per line = 128 bits):
1 2 3 4 5 6 7 8
# (real0 imag0 real1 imag1 real2 imag2 real3 imag3)
```

## Step 7: Verify and Understand run_script.sh

**CRITICAL:** The `run_script.sh` file copied from the Test Harness example is the proper way to run your design on hardware. **Do NOT create custom run scripts** - use the pattern from the example.

### What run_script.sh Does

`run_script.sh` is executed **on your host workstation** (not on the board) and:
1. Sets the `SERVER_IP_PORT` environment variable (board IP address)
2. Calls the client test bench with the xclbin file

**Test Harness Architecture:**
- **Server:** Runs on VEK385/VCK190/VEK280 board via `test_harness_mgr --xclbin <file>.xclbin`
- **Client:** Runs on your workstation via `run_script.sh` (connects to server over network)

### Standard Pattern

**All run_script.sh files follow this pattern:**

```bash
# Check if SERVER_IP_PORT is set
if [ -z "$SERVER_IP_PORT" ]; then
    # Set default value 127.0.0.1:8080 (localhost)
    export SERVER_IP_PORT=127.0.0.1:8080
fi

# Call client with xclbin (format varies by client type - see below)
<client_command> <xclbin_name> <optional_args>
```

### Client-Specific Format

The `run_script.sh` structure **differs by client type**:

#### Python Client Example (VCK190/VEK280/VEK385)

```bash
if [ -z "$SERVER_IP_PORT" ]; then
    export SERVER_IP_PORT=127.0.0.1:8080
fi
python3 ./client/tb.py vck190_test_harness.xclbin --iterations 4 --function --performance
```

**Note:** Change `vck190_test_harness.xclbin` to `vek280_test_harness.xclbin` or `vek385_test_harness.xclbin` based on platform.

#### C++ Client Example (VCK190/VEK280/VEK385)

```bash
if [ -z "$SERVER_IP_PORT" ]; then
    export SERVER_IP_PORT=127.0.0.1:8080
fi
./client_exe vek385_test_harness.xclbin 1 1 0
return_code=$?
if [ $return_code -ne 0 ]; then
    echo "ERROR: TEST FAILED, RC=$return_code"
    exit $return_code
else
    echo "INFO: TEST PASSED, RC=0"
fi
exit $return_code
```

**C++ clients often include:**
- Return code checking
- Pass/fail reporting
- Command-line arguments for test configuration

#### MATLAB Client Example (VCK190/VEK280/VEK385)

```bash
if [ -z "$SERVER_IP_PORT" ]; then
    export SERVER_IP_PORT=127.0.0.1:8080
fi
matlab -batch "run('./client/tb.m')"
```

### How to Use run_script.sh

**Purpose:** `run_script.sh` is the deployment script that launches the client testbench with the correct environment and server configuration.

#### Server Setup (Required for Hardware Deployment Only)

**Before deploying to hardware:**

1. **Ensure Test Harness server is running on the board**
   - Server must be started by board administrator or user with board access
   - Server loads xclbin and listens on port 8080
   - **Note:** Server setup/management is outside the scope of client-side deployment

2. **Obtain board IP address from board administrator**
   - User provides: `192.168.1.100`
   - Agent constructs: `SERVER_IP_PORT=192.168.1.100:8080`
   - Port 8080 is the standard Test Harness server port

**Server setup is board-specific and typically done once by system administrators. Consult Test Harness documentation or board administrator for server installation and management.**

#### Client Execution (Workstation Side)

**On your workstation (client side):**
```bash
# Required environment variables
export TEST_HARNESS_REPO_PATH=$TEST_HARNESS_PATH  # Required for Python/MATLAB clients
export SERVER_IP_PORT=192.168.1.100:8080          # Required for server connection

# Activate Python environment (if using Python client with virtual environment)
source /path/to/venv/bin/activate

# Optional: Source XRT environment (may be needed for some configurations)
# source $XILINX_VITIS/settings64.sh

# Run the test
./run_script.sh
```

**Required environment variables:**
- `SERVER_IP_PORT`: Board IP address with port (e.g., `192.168.1.100:8080`)
- `TEST_HARNESS_REPO_PATH`: Path to Test Harness repository (required for Python/MATLAB clients to find APIs)

**Default behavior:** If `SERVER_IP_PORT` is not set, it defaults to `127.0.0.1:8080` (localhost).

#### Verifying Network Connectivity

**Before attempting deployment, verify network connectivity:**

```bash
# Test network connectivity to board (IP only, not port)
ping -c 3 192.168.1.100
```

**Note:** You cannot verify server status remotely without board access. If the client connects and runs successfully, the server is operational. Connection failures will be reported by the Test Harness client at runtime.

### Customization Guidelines

**DO NOT MODIFY:**
- The `SERVER_IP_PORT` check pattern
- The basic structure (environment setup + client call)

**YOU CAN MODIFY:**
- Client arguments (e.g., `--iterations`, test parameters)
- Return code handling (for C++ clients)
- Additional environment variables specific to your design

### Packaging run_script.sh

The `run_script.sh` **must be packaged** with your design for hardware deployment. Update your Makefile's package target:

```makefile
package: $(RUN_DEPS) ${PKG_DIR}
	@echo "Copying package to ${PKG_DIR}..."
	cp -r ${XCLBIN} client data ${PKG_DIR}/
	cp run_script.sh ${PKG_DIR}/
	chmod +x ${PKG_DIR}/run_script.sh
	@echo "Package complete: ${PKG_DIR}/"
```

This ensures `run_script.sh` is included in the deployment package (`pkg.hw.*/`).

## Step 8: Adapt Client Testbench

Modify `client/tb.*` (`.cpp`, `.m`, or `.py`) for your I/O configuration.

### Understanding Client Arguments

**CRITICAL:** The arguments passed in `run_script.sh` after the xclbin filename are received by the client testbench code. Your client must be designed to accept and parse these arguments.

**Example from run_script.sh:**
```bash
python3 ./client/tb.py vck190_test_harness.xclbin --iterations 4 --function
#                      ^^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#                      Required argument         Optional arguments parsed by client
```

The client code (`client/tb.py`) must use argument parsing to receive these values:
- Positional: xclbin path (always required)
- Optional: iterations, test modes, custom parameters (client-specific)

### C++ Client (`client/tb.cpp`)

**Update channel assignments and graph name:**
```cpp
// Update PLIO channels (example for 2 inputs, 1 output):
std::vector<test_harness_args> targs;
targs.push_back(test_harness_args(channel_index::PLIO_01_TO_AIE, input_bytes, 1, 1, in_data_0));
targs.push_back(test_harness_args(channel_index::PLIO_02_TO_AIE, input_bytes, 1, 1, in_data_1));
targs.push_back(test_harness_args(channel_index::PLIO_01_FROM_AIE, output_bytes, 1, 1, out_data));

// Update graph name (must match class name in graph.h):
test_harness_mgr mgr(xclbin_path, {"your_graph_name"}, "vck190");
```

**Accept command-line arguments using argc/argv:**
```cpp
int main(int argc, char** argv) {
    // Required: xclbin path
    std::string xclbin_path(argv[1]);
    
    // Optional: parse additional arguments with defaults
    auto num_iterations = (argc >= 3) ? atoi(argv[2]) : 1;
    auto num_repetitions = (argc >= 4) ? atoi(argv[3]) : 1;
    auto num_delay = (argc >= 5) ? atoi(argv[4]) : 0;
    
    // Your test harness code here...
}
```

**Corresponding run_script.sh:**
```bash
./client_exe vck190_test_harness.xclbin 4 1 0
#            ^^^^^^^^^^^^^^^^^^^^^^^^^ ^ ^ ^
#            argv[1]                   | | argv[4] (num_delay)
#                                      | argv[3] (num_repetitions)
#                                      argv[2] (num_iterations)
```

### MATLAB Client (`client/tb.m`)

**Update channels and graph name:**
```matlab
% Update channels:
targs = [];
targs = [targs test_harness_args(channel_index.PLIO_01_TO_AIE, in_bytes, 1, 1, in_data)];
targs = [targs test_harness_args(channel_index.PLIO_01_FROM_AIE, out_bytes, 1, 1, out_data)];

% Update graph name:
mgr = test_harness_mgr(xclbin_path, {'your_graph_name'}, 'vck190');
```

**Accept arguments using function parameters:**
```matlab
function tb(xclbin_path, num_iterations)
    arguments
        xclbin_path (1, 1) string
        num_iterations (1, 1) {mustBeInteger, mustBePositive} = 1
    end
    
    % Your test harness code here...
end
```

**Corresponding run_script.sh:**
```bash
matlab -batch "tb('vck190_test_harness.xclbin', 4)"
#                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  ^
#                  First argument (required)      Second argument (optional, defaults to 1)
```

**Note:** MATLAB `run_script.sh` examples often omit the second argument, using the default value.

### Python Client (`client/tb.py`)

**Update channels and graph name:**
```python
# Update channels:
targs = []
targs.append(test_harness_args(channel_index.PLIO_01_TO_AIE, in_bytes, 1, 1, in_data))
targs.append(test_harness_args(channel_index.PLIO_01_FROM_AIE, out_bytes, 1, 1, out_data))

# Update graph name:
mgr = test_harness_mgr(xclbin_path, ['your_graph_name'], 'vck190')
```

**Accept arguments using argparse:**
```python
import argparse

def main(args):
    # Use args.xclbin, args.iterations, etc.
    xclbin_path = args.xclbin
    num_iterations = args.iterations
    
    # Your test harness code here...

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test Harness Client')
    parser.add_argument('xclbin', type=str, help='Path to xclbin file')
    parser.add_argument('--iterations', type=int, default=1, help='Number of iterations')
    parser.add_argument('--function', action='store_true', help='Run in function mode')
    parser.add_argument('--performance', action='store_true', help='Run in performance mode')
    args = parser.parse_args()
    main(args)
```

**Corresponding run_script.sh:**
```bash
python3 ./client/tb.py vck190_test_harness.xclbin --iterations 4 --function --performance
#                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#                      Positional (required)          Optional flags parsed by argparse
```

**Common Python Arguments:**
- `xclbin` - Required positional: path to xclbin file
- `--iterations` - Optional: number of test iterations (default: use DESIGN_ITERATIONS from graph_app.cpp)
- `--function` - Optional flag: enable functional mode testing
- `--performance` - Optional flag: enable performance mode testing
- `--pipeline` - Optional flag: enable pipelined execution mode

**Data format:** Convert to uint32 arrays (Test Harness requirement).

**When using existing data files, implement simplified loading pattern:**

```python
def main(args):
    # Design parameters (from design headers)
    NSAMP = 1024
    NNODES = 64
    DESIGN_ITERATIONS = 4  # From graph_app.cpp: dut.run(4)
    
    # Paths
    data_i_path = "../../data/data_i.txt"
    data_o_path = "../../data/data_o.txt"
    
    if not os.path.exists(data_i_path):
        print(f"ERROR: Input data file {data_i_path} not found")
        sys.exit(1)
    
    # Load ALL data (no size calculation or truncation)
    print(f"INFO: Loading input data from {data_i_path}")
    data_i_uint32 = load_bfloat16_data(data_i_path)
    
    print(f"INFO: Loading expected output from {data_o_path}")
    data_o_expected_uint32 = load_bfloat16_data(data_o_path)
    
    # Create output buffer (same size as expected)
    data_o_uint32 = np.zeros(len(data_o_expected_uint32), dtype=np.uint32)
    
    # Information only (no validation)
    print(f"INFO: Input: {len(data_i_uint32)} uint32 values "
          f"({len(data_i_uint32)*2} values total)")
    print(f"INFO: Output: {len(data_o_uint32)} uint32 values "
          f"({len(data_o_uint32)*2} values total)")
    print(f"INFO: Iterations: {args.iterations}")
    
    # Test Harness setup
    mgr = test_harness_mgr(xclbin_path, ['gr'], 'vek385')
    
    # ... test mode selection ...
    
    for mode in test_modes:
        # Setup using actual loaded sizes
        targs = []
        targs.append(test_harness_args(channel_index.PLIO_01_TO_AIE, 
                                      len(data_i_uint32) * 4,
                                      1, 1, data_i_uint32))
        targs.append(test_harness_args(channel_index.PLIO_01_FROM_AIE, 
                                      len(data_o_uint32) * 4,
                                      1, 1, data_o_uint32))
        
        mgr.runAIEGraph(0, args.iterations)
        mgr.runTestHarness(mode, targs)
        mgr.waitForRes()
        mgr.printPerf()
        
        # Validation uses all loaded data
        if mgr.isResultValid():
            hw_output = extract_data(data_o_uint32)
            expected = extract_data(data_o_expected_uint32)
            # Compare and check errors...
```

**Set default iterations from design analysis:**
```python
# At bottom of tb.py
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test Harness Client')
    parser.add_argument('xclbin', type=str, help='Path to xclbin file')
    parser.add_argument('--iterations', type=int, 
                       default=4,  # From graph_app.cpp: dut.run(4)
                       help='Number of iterations to run')
    parser.add_argument('--function', action='store_true', help='Run in function mode')
    parser.add_argument('--performance', action='store_true', help='Run in performance mode')
    args = parser.parse_args()
    main(args)
```

**Update run_script.sh to match DESIGN_ITERATIONS:**
```bash
python3 ./client/tb.py vek385_test_harness.xclbin --iterations 4 --function --performance
#                                                              ^
#                                                              From graph_app.cpp
```

### Test Modes: Functional vs Performance

**CRITICAL:** Both FUNC_MODE and PERF_MODE should perform functional verification when `isResultValid()` returns true. The difference is in data buffering strategy and performance.

#### Understanding Test Modes

| Mode | Data Buffer | Speed | Result Validity | Use Case |
|------|-------------|-------|-----------------|----------|
| **FUNC_MODE** | DDR | Slower | Always valid | Guarantee correctness, comprehensive testing |
| **PERF_MODE** | URAM | Faster | Valid if data fits | Measure true performance, large datasets |

**Key differences:**
- **FUNC_MODE (Functional Mode):**
  - Uses DDR memory for data buffering (larger capacity)
  - Always captures complete results → `isResultValid()` always returns `True`
  - Slower performance due to DDR overhead
  - **Purpose:** Guarantee functional correctness

- **PERF_MODE (Performance Mode):**
  - Uses URAM for data buffering (limited capacity)
  - Results valid only if test data fits in URAM
  - Faster performance, shows true throughput
  - **Purpose:** Measure accurate performance without DDR overhead

**URAM Capacity Limits (per platform):**
- VCK190: 4096 samples per channel
- VEK280/VEK385: 8192 samples per channel

If test data exceeds URAM capacity, `isResultValid()` returns `False` in PERF_MODE.

#### Implementing Verification in Both Modes

**Pattern (applies to all client types):**
```
For each test mode (FUNC_MODE, PERF_MODE):
    1. Run hardware: runTestHarness(mode, targs)
    2. Wait for completion: waitForRes()
    3. Check validity: is_valid = isResultValid()
    4. If is_valid == True:
           Perform functional verification (compare hw vs golden)
       Else:
           Skip verification with INFO message (not a failure)
    5. Print performance: printPerf()
```

#### C++ Example

```cpp
std::vector<TestMode> modes = {FUNC_MODE, PERF_MODE};
for (auto mode : modes) {
    std::cout << "Testing " << (mode == FUNC_MODE ? "Function" : "Performance") << " mode." << std::endl;
    
    mgr.runAIEGraph(0, num_iterations);
    mgr.runTestHarness(mode, targs);
    mgr.waitForRes(0);
    mgr.printPerf();
    
    auto is_valid = mgr.isResultValid();
    if (!is_valid) {
        printf("[INFO] Result checking not valid - test size exceeds URAM capacity.\n");
    } else {
        // Perform functional verification
        for (int i = 0; i < num_values; i++) {
            auto golden = compute_golden(input[i]);
            if (output[i] != golden) {
                errorCount++;
                std::cout << "ERROR: output[" << i << "] != golden" << std::endl;
            }
        }
    }
}
```

#### Python Example

```python
test_modes = []
if args.function:
    test_modes.append(test_mode.FUNC_MODE)
if args.performance:
    test_modes.append(test_mode.PERF_MODE)

for mode in test_modes:
    mode_str = "functional" if mode == test_mode.FUNC_MODE else "performance"
    print(f"Running in {mode_str} mode")
    
    mgr.runAIEGraph(0, num_iterations)
    mgr.runTestHarness(mode, targs)
    mgr.waitForRes(10000)
    
    is_valid = mgr.isResultValid()
    if not is_valid:
        print(f"[INFO] Result checking not valid - test size exceeds URAM capacity")
    else:
        # Perform functional verification
        hw_output = extract_output_data(output_buffer)
        diff = np.abs(hw_output - golden_output)
        if np.max(diff) > tolerance:
            print(f"ERROR: Functional verification failed")
            errors += 1
        else:
            print(f"PASS: All samples within tolerance")
    
    mgr.printPerf()
```

#### MATLAB Example

```matlab
modes = [];
if run_func_mode
    modes = [modes, test_mode.FUNC_MODE];
end
if run_perf_mode
    modes = [modes, test_mode.PERF_MODE];
end

for mode = modes
    if mode == test_mode.FUNC_MODE
        disp('Testing Function mode');
    else
        disp('Testing Performance mode');
    end
    
    mgr.runAIEGraph(0, num_iterations);
    mgr.runTestHarness(mode, targs);
    mgr.waitForRes(0);
    mgr.printPerf();
    
    is_valid = mgr.isResultValid();
    if ~is_valid
        disp('[INFO] Result checking not valid - test size exceeds URAM capacity');
    else
        % Perform functional verification
        errors = sum(output_data ~= golden_data);
        if errors > 0
            fprintf('ERROR: %d mismatches found\n', errors);
        else
            disp('PASS: All samples match');
        end
    end
end
```

#### Best Practices

1. **Always check `isResultValid()` before verification** - Don't assume results are valid
2. **Test both modes when possible** - FUNC_MODE guarantees correctness, PERF_MODE shows true performance
3. **Handle URAM overflow gracefully** - Print INFO message, not ERROR, when `isResultValid()` returns false
4. **Design test size wisely:**
   - For guaranteed verification: Keep data < URAM capacity OR use only FUNC_MODE
   - For performance measurement: PERF_MODE is preferred (faster, no DDR overhead)
5. **Understand the tradeoff:**
   - Small datasets: Both modes work, use both for comprehensive testing
   - Large datasets: FUNC_MODE for correctness, PERF_MODE for performance (may not verify)

## Step 9: Build and Package

```bash
# Set environment (if not already set):
export TEST_HARNESS_PATH=/path/to/AI-Engine-Test-Harness

# Build:
make all  # Builds AIE, packages xclbin, compiles client (if C++)

# Or step-by-step:
make download_xsa  # Download platform XSA
make package       # Build AIE + package xclbin
```

**Build artifacts:**
- AIE compiled: `_x_temp.hw.*/libadf.a`
- Hardware package: `_x_temp.hw.*/vck190_test_harness.xclbin`
- Client executable (C++ only): `_x_temp.hw.*/client_exe`
- Package directory: `pkg.hw.*/` (ready to copy to board)

## Examples

### Example 1: Single I/O, MATLAB Client, VCK190

**Original:** 1 input PLIO (64-bit, int32), 1 output PLIO (64-bit, int32)

**Steps:**
```bash
# 1. Copy MATLAB example:
cp -r ${TEST_HARNESS_PATH}/examples/matlab/vck190/adder/* .

# 2. Replace AIE files:
rm aie/*.{cpp,h,cc}
cp ../user_design/*_kernel.* aie/
cp ../user_design/graph.h aie/
cp ../user_design/graph.cpp aie/

# 3. Edit aie/graph.cpp - change PLIOs:
#    "PLIO_i_0", plio_64_bits  →  "PLIO_01_TO_AIE", plio_128_bits
#    "PLIO_o_0", plio_64_bits  →  "PLIO_01_FROM_AIE", plio_128_bits

# 4. Update data for 128-bit (4 int32 per line):
#    data/sig_i.txt: "1 2 3 4\n5 6 7 8\n..."

# 5. Build:
make all
```

### Example 2: Multi-I/O, C++ Client, VCK190

**Original:** 3 input PLIOs, 2 output PLIOs

**Steps:**
```bash
# 1. Copy C++ multi-I/O example:
cp -r ${TEST_HARNESS_PATH}/examples/vck190/channelizer/* .

# 2. Replace AIE files (same as Example 1)

# 3. Edit graph.cpp - map PLIOs:
#    Input 0 → "PLIO_01_TO_AIE", plio_128_bits
#    Input 1 → "PLIO_02_TO_AIE", plio_128_bits
#    Input 2 → "PLIO_03_TO_AIE", plio_128_bits
#    Output 0 → "PLIO_01_FROM_AIE", plio_128_bits
#    Output 1 → "PLIO_02_FROM_AIE", plio_128_bits

# 4. Edit client/tb.cpp - add channels:
#    targs.push_back(...PLIO_01_TO_AIE...)
#    targs.push_back(...PLIO_02_TO_AIE...)
#    targs.push_back(...PLIO_03_TO_AIE...)
#    targs.push_back(...PLIO_01_FROM_AIE...)
#    targs.push_back(...PLIO_02_FROM_AIE...)

# 5. Build:
make all
```

### Example 3: Python Client, VEK280

**Original:** Single I/O, needs VEK280 platform

**Steps:**
```bash
# 1. Copy Python VCK190 example (no VEK280 Python example exists):
cp -r ${TEST_HARNESS_PATH}/examples/python/vck190/adder/* .

# 2. Change platform in Makefile:
#    DEVICE ?= vek280  (change from vck190)

# 3. Replace AIE files and update PLIOs (same as Example 1)

# 4. Edit client/tb.py - update graph name and platform:
#    mgr = test_harness_mgr(xclbin_path, ['your_graph'], 'vek280')

# 5. Build:
make all
```

## Troubleshooting

### Build Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `ERROR: Source file does not exist: Work/libadf.a` | Wrong libadf.a path in custom Makefile | Use Test Harness example Makefile (path is `_x_temp.*/libadf.a`) |
| `ERROR: Platform version X not supported by tool version Y` | Vitis/XSA version mismatch | Load matching Vitis, or checkout matching Test Harness tag |
| `CRITICAL-WARNING: Could not find node instance 'PLIO_XX_...'` | Constraint file defines all 36 PLIOs, design uses fewer | **Expected** - safe to ignore if design uses < max PLIOs |
| `ERROR: Design has X inputs but platform supports Y` | Design exceeds platform limits | Use VCK190 (36 PLIOs) or reduce I/O count |
| PLIO naming error during compilation | Wrong naming format | Use `PLIO_01_TO_AIE` not `PLIO_1_TO_AIE` (zero-padded) |
| `make: *** No rule to make target 'libadf.a'` | Custom Makefile structure | **Delete and recopy Test Harness example** |
| `python3-config: command not found` (Python lib build) | Virtual environment missing `python3-config` | Create wrapper in `$VENV/bin/python3-config` using Python's sysconfig module |
| Build succeeds but no xclbin created | Wrong package target or path | Check `pkg.hw.*/vck190_test_harness.xclbin` exists |

### Deployment/Runtime Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Segmentation fault when running client | XRT not sourced | Source XRT: `source $XILINX_VITIS/settings64.sh` |
| `ImportError: undefined symbol: ...filesystem...` | Python library missing `-lstdc++fs` on GCC < 9 | Rebuild Test Harness: `cd $TEST_HARNESS_PATH/test_harness && make python` |
| Client hangs or connection timeout | Server not running, network issue, **OR data/iterations mismatch** | Verify board is pingable, contact administrator. **If persists, verify data files in ./data/ match design requirements for N iterations. Check graph_app.cpp .run(N) matches data expectations. Regenerate data using gen_vectors if needed.** |
| `Connection refused` to server | Wrong IP/port or server not running | Verify `SERVER_IP_PORT` is correct, contact board administrator |
| Test fails with large data in PERF_MODE | URAM overflow | Use FUNC_MODE or reduce data size. Check `isResultValid()` before PERF test |
| `waitForRes()` timeout during test | Possible data size/iterations mismatch | User must verify: data files contain correct samples for `--iterations N`. Check graph_app.cpp .run(N) and regenerate data if mismatch suspected |

## Common Mistakes to Avoid

### Build-Related

1. ❌ Creating custom Makefiles instead of copying Test Harness examples
2. ❌ Modifying Test Harness build infrastructure (common.mk)
3. ❌ Using non-128-bit PLIOs (`plio_64_bits` won't work)
4. ❌ Wrong PLIO naming (`PLIO_1_TO_AIE` should be `PLIO_01_TO_AIE`)
5. ❌ Not matching Vitis and Test Harness versions
6. ❌ Creating all three client types (only create ONE: C++, MATLAB, or Python)

### Data-Related

7. ❌ Truncating loaded file data to calculated size (may lose iterations)
8. ❌ Not checking graph_app.cpp for iteration count when setting `--iterations`
9. ❌ Hardcoding `--iterations` without considering original design intent from graph_app.cpp
10. ❌ Attempting to calculate/validate per-iteration sample counts (user's responsibility)
11. ✅ **DO:** Load complete data files, use graph_app.cpp .run(N) for default iterations, trust user to provide correct data

### Deployment-Related

7. ❌ Reporting "success" after build without testing hardware when deployment was requested
8. ❌ Attempting hardware deployment when user only requested conversion/build
9. ❌ Not verifying server connectivity before reporting deployment success
10. ❌ Forgetting to source XRT environment before running client
11. ❌ Not checking `isResultValid()` before attempting PERF_MODE tests
12. ❌ Assuming localhost (127.0.0.1) when user provided different server IP

## Success Criteria

### Build Success (Required for All Conversions)

After successful build, verify:

- [ ] `_x_temp.hw.*/libadf.a` exists (AIE compiled)
- [ ] `_x_temp.hw.*/vck190_test_harness.xclbin` exists (packaged)
- [ ] `pkg.hw.*/` directory contains client files and xclbin
- [ ] No ERRORs in build log (CRITICAL-WARNINGs about unused PLIOs are OK)
- [ ] Client executable built (C++ only) or script copied (MATLAB/Python)

**Report to user:**
```
✅ Build successful
✅ xclbin created: _x_temp.hw.vck190/vck190_test_harness.xclbin
✅ Client ready: client/tb.py

To deploy on hardware:
  export SERVER_IP_PORT=<board_ip>:8080
  ./run_script.sh
```

### Deployment Success (Only When Server IP Provided)

**Prerequisites:**
- [ ] User provided board IP address (e.g., `192.168.1.100`)
- [ ] Test Harness server confirmed running on board (by administrator)
- [ ] XRT environment sourced: `source $XILINX_VITIS/settings64.sh`
- [ ] Agent constructs SERVER_IP_PORT: `SERVER_IP_PORT=<ip>:8080`

**After hardware execution, verify:**

- [ ] Client connects to server successfully
- [ ] FUNC_MODE test completes without errors
- [ ] PERF_MODE test completes (if `isResultValid()` returns true)
- [ ] Output validation passes (max error within tolerance)
- [ ] Performance metrics reported (MB/s)

**Report to user:**
```
✅ Hardware deployment successful
✅ FUNC_MODE: All outputs match (max error: 5.96e-08)
✅ PERF_MODE: All outputs match (max error: 5.96e-08)
📊 Performance: 4764 MB/s input, 4767 MB/s output
```

**If deployment was NOT requested:**
```
⚠️  Note: Build completed successfully, but hardware test was not performed.
    User did not request deployment or provide server IP address.
```

## References

- [Test Harness Repository](https://github.com/Xilinx/AI-Engine-Test-Harness)
- [Test Harness Documentation](https://xilinx.github.io/AI-Engine-Test-Harness/)
- Constraint files: `${TEST_HARNESS_PATH}/cfg/*.json`
- Example designs: `${TEST_HARNESS_PATH}/examples/`

---

**Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.**  
**SPDX-License-Identifier: MIT**
