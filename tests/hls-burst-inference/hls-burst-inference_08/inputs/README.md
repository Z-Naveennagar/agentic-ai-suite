# hls-burst-inference_08 — hls-burst-inference Skill Evaluation

A test case demonstrating the value of the `hls-burst-inference` skill.

- **Environment:** Vitis_IDE_26.2 + gpt-5.2 model
- **Case:** `test/hls-burst-inference/hls-burst-inference_08/hls-burst-inference_08.cpp`

## Analysis Prompt

> can burst inference applied? Please make static analysis without running HLS.

| | Result |
| --- | --- |
| **Expected answer** | No |
| **LLM with skill** | No |
| **LLM without skill** | Yes |

- **With skill:** burst inference cannot be applied as written, because the accessed data type on the M-AXI ports is MyType, whose width is 96 bits (3×32-bit int), and 96 is not a power of 2 (fails Precondition 3)

- **Summary:** Skill wins.

## Prompt 2

> can burst inference applied? If the answer is yes, do nothing; if the answer is no, fix it

| | Result | Fix |
| --- | --- | --- |
| **Expected answer** | No | — |
| **LLM with skill** | No | Pass |
| **LLM without skill** | Yes | Failed |

- **With skill:** find the issue and fix it.
- **Without skill:** can't find the issue.
- **Summary:** Skill wins.

- **Run C synthesis to verify:** 
Running HLS C synthesis (`csynth`) successfully with log below confirms burst inference is applied
```
INFO: [HLS 214-115] Multiple burst reads of length 256 and bit width 512 has been inferred on bundle 'gmem'. These burst requests might be further partitioned into multiple requests during RTL generation, based on max_read_burst_length or max_write_burst_length settings. (hls-burst-inference_08.cpp:19:20)
INFO: [HLS 214-115] Multiple burst writes of length 256 and bit width 512 has been inferred on bundle 'gmem'. These burst requests might be further partitioned into multiple requests during RTL generation, based on max_read_burst_length or max_write_burst_length settings. (hls-burst-inference_08.cpp:28:20)
```
Running HLS C synthesis (`csynth`) without log above confirms burst inference is not applied
