# hls-stencil-pattern_03 — hls-stencil-pattern Skill Evaluation
A test case demonstrating the value of the `hls-stencil-pattern` skill.

Environment: Vitis_IDE_26.1 + gpt-5.2 model

**Case:** `test/hls-stencil-pattern/hls-stencil-pattern_03.cpp`

## Prompt 1

> can stencil pattern optimization applied? Please make static analysis without running HLS.

| | Result |
| --- | --- |
| **Expected answer** | No |
| **LLM with skill** | No |
| **LLM without skill** | Yes |

- **With skill:** find the real issue: the output loop for (r=0; r < var; r++) does not have a constant trip count because var is not constant.

**Summary:** Skill wins.

## Prompt 2

> can stencil pattern optimization applied? if the answer is Yes, do nothing; if the answer is No, fix it

| | Result | Fix |
| --- | --- | --- |
| **Expected answer** | No | - |
| **LLM with skill** | No | Pass |
| **LLM without skill** | Yes | Failed |

- **With skill:** find the issue and fix it.
- **Without skill:** guess without rules, try without effective solution
- **Summary:** Skill wins

- **Run C synthesis to verify:** 
Running HLS C synthesis (`csynth`) successfully with log below confirms stencil pattern optimization is not applied
```
WARNING: [HLS 214-333] Cannot apply array stencil optimization to variable 'O' in loop 'VITIS_LOOP_21_4' because of unknown trip count of loop 'VITIS_LOOP_20_3' (hls-stencil-pattern_03.cpp:12:0)
```
Running HLS C synthesis (`csynth`) without log below confirms stencil pattern optimization is applied
```
INFO: [HLS 214-330] Applying 3x3 array stencil optimization to variable 'O'...
```