# hls-array2stream-12 — hls-array-to-stream Skill Evaluation

A test case demonstrating the value of the `hls-array-to-stream` skill.

- **Environment:** Vitis_IDE_26.2 + `claude-opus-4.8` model
- **Case:** `test/hls-array-to-stream/hls-array2stream-12/kernel.cpp`

## Prompt 1

> Can array to stream be applied? Please make static analysis without running HLS.

| | Result |
| --- | --- |
| **Expected answer** | No |
| **LLM with skill** | No |
| **LLM without skill** | Yes |

- **Without skill:** It doesn't find the struct copy problem.

**Summary:** Skill wins.

## Prompt 2

> Can array to stream be applied? If it cannot, please enhance for me.

| | Result | Fix |
| --- | --- | --- |
| **Expected answer** | No | — |
| **LLM with skill** | No | Pass |
| **LLM without skill** | No | Pass |

- **With skill:** Answer derived from static analysis, without running HLS.
- **Without skill:** Not sure about the answer in the beginning, but finds the answer after running HLS.
- **Run C synthesis to verify:** 
Running HLS C synthesis (`csynth`) failed with error, confirms the array to stream is not applied
```
ERROR: [HLS 214-244] in function 'A::operator=(A const&)': Failed to implement stream interface on variable 'out'. Each array element of 'out' must: (a) be accessed only once, (b) read or write the whole array element in one operation and (c) be accessed in sequential order. (kernel.cpp:7:5)
ERROR: [HLS 214-244] in function 'A::operator=(A const&)': Failed to implement stream interface on variable 'in'. Each array element of 'in' must: (a) be accessed only once, (b) read or write the whole array element in one operation and (c) be accessed in sequential order. (kernel.cpp:7:15)
```

Running HLS C synthesis (`csynth`) successfully confirms the array to stream is applied