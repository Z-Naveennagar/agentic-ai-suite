# hls-burst-inference_33 — hls-burst-inference Skill Evaluation

A test case demonstrating the value of the `hls-burst-inference` skill.

- **Environment:** Vitis_IDE_26.2 + `claude-opus-4.8` model
- **Case:** `test/hls-burst-inference/hls-burst-inference_33.cpp`

## Prompt 1

> Can HLS burst inference be applied? Please make analysis without running synthesis.

| | Result |
| --- | --- |
| **Expected answer** | No |
| **LLM with skill** | No |
| **LLM without skill** | Yes |

- **With skill:** Further action is correct to make burst happen.

**Summary:** Skill wins.

**How to check**

For expected answer "No", run csynth and you will see the burst fail information in `csynth.rpt`:

```
* All M_AXI Variable Accesses
+--------------+----------+-------------------------------------+-----------+--------------+-----------------+-------------------------------------+------------+------------------------+
| HW Interface | Variable | Access Location                     | Direction | Burst Status | Loop            | Loop Location                       | Resolution | Problem                |
+--------------+----------+-------------------------------------+-----------+--------------+-----------------+-------------------------------------+------------+------------------------+
| m_axi_aximm  | in       | ../hls-burst-inference_33.cpp:24:14 | read      | Fail         | VITIS_LOOP_23_1 | ../hls-burst-inference_33.cpp:23:20 | 214-230    | Stride is incompatible |
| m_axi_aximm0 | out      | ../hls-burst-inference_33.cpp:24:12 | write     | Fail         | VITIS_LOOP_23_1 | ../hls-burst-inference_33.cpp:23:20 | 214-230    | Stride is incompatible |
+--------------+----------+-------------------------------------+-----------+--------------+-----------------+-------------------------------------+------------+------------------------+
```

## Prompt 2

> Can HLS burst inference be applied? If it cannot, please enhance for me.

| | Result | Fix |
| --- | --- | --- |
| **Expected answer** | No | — |
| **LLM with skill** | No | Pass |
| **LLM without skill** | Inconsistent (No, then Yes) | Pass |

- **With skill:** Further action is correct to make burst happen.
- **Without skill:** First run says No, second run says Yes; makes more changes than needed.

**Summary:** Tie — but the skill's answer is consistent.

**How to check**

The failure of burst check is same as `Prompt 1`. And with fix, run csynth and you will see the following successful burst information in `csynth.rpt`:

```
* Inferred Burst Summary
+--------------+-----------+----------+-------+-----------------+-------------------------------------+
| HW Interface | Direction | Length   | Width | Loop            | Loop Location                       |
+--------------+-----------+----------+-------+-----------------+-------------------------------------+
| m_axi_aximm  | read      | variable | 64    | VITIS_LOOP_23_1 | ../hls-burst-inference_33.cpp:23:20 |
| m_axi_aximm0 | write     | variable | 64    | VITIS_LOOP_23_1 | ../hls-burst-inference_33.cpp:23:20 |
+--------------+-----------+----------+-------+-----------------+-------------------------------------+
```