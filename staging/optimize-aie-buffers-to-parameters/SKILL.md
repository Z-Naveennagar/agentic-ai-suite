---
name: optimize-aie-buffers-to-parameters
description: >-
  Moves large local arrays (stack-allocated buffers) in AI Engine kernels off the
  stack into class data members registered with REGISTER_PARAMETER. This enables
  explicit placement control via constraints files, reduces stack pressure, and
  allows the compiler to place buffers in specific memory banks for banking
  optimization. Use when: a kernel has large alignas arrays on the stack that
  consume most of the stack allocation, when the user wants placement control over
  working buffers, or when aie.cfg requires excessive stacksize due to local arrays.
  Trigger on: "move buffers off stack", "REGISTER_PARAMETER", "buffer placement",
  "reduce stack size", "memory bank assignment", "parameter placement".
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Optimize AIE: Move Buffers Off Stack to Registered Parameters

Convert large stack-allocated arrays in AIE kernel `run()` methods into class data
members using array references registered with `REGISTER_PARAMETER`. This provides
explicit placement control and reduces stack requirements.

---

## When to Apply

This optimization applies when **any** of the following are true:

1. The kernel `run()` method contains large `alignas` array declarations:
   ```cpp
   void MyKernel::run(...) {
       alignas(32) cfloat buffer[256];  // 2048 bytes on stack!
   }
   ```

2. The `aie.cfg` file requires `stacksize` greater than the default (2048) solely
   to accommodate local working arrays.

3. The user wants **placement control** over working buffers — the ability to
   assign specific memory banks via the `.aiecst` constraints file.

4. Multiple large arrays compete for the same memory banks, causing load/store
   conflicts that increase loop II.

---

## Benefits

| Benefit | Description |
|---------|-------------|
| **Placement control** | Buffers can be assigned to specific memory banks in `.aiecst` |
| **Reduced stack** | Stack returns to default (2048 bytes) |
| **Banking optimization** | Place frequently co-accessed buffers in different banks to avoid conflicts |
| **Visibility** | Buffers appear in the Map Report for resource analysis |

---

## Transformation Pattern

### Before (stack-allocated):

**Kernel header (`KERNEL.h`):**
```cpp
class MyKernel {
public:
    MyKernel(void);
    void run(input_buffer<cfloat>& in, output_buffer<cfloat>& out);
    static void registerKernelClass(void) {
        REGISTER_FUNCTION(MyKernel::run);
    }
};
```

**Kernel source (`KERNEL.cpp`):**
```cpp
MyKernel::MyKernel(void) {
    aie::set_rounding(aie::rounding_mode::conv_even);
    aie::set_saturation(aie::saturation_mode::saturate);
}

void MyKernel::run(input_buffer<cfloat>& in, output_buffer<cfloat>& out) {
    alignas(32) cfloat work_A[256];  // Large buffer on stack
    alignas(32) cfloat work_B[256];  // Another large buffer
    // ... use work_A, work_B ...
}
```

**Graph (`KERNEL_graph.h`):**
```cpp
kk = kernel::create_object<MyKernel>();
```

**Config (`aie.cfg`):**
```
stacksize=4096   # Inflated to fit arrays
```

### After (registered parameters):

**Kernel header (`KERNEL.h`):**
```cpp
class MyKernel {
public:
    // Buffer sizes
    static constexpr unsigned BUF_A_SIZE = 256;
    static constexpr unsigned BUF_B_SIZE = 256;

    // Working buffers as array references (placed in data memory)
    alignas(32) cfloat (&buf_A)[BUF_A_SIZE];
    alignas(32) cfloat (&buf_B)[BUF_B_SIZE];

    // Constructor takes array references
    MyKernel(cfloat (&buf_A_i)[BUF_A_SIZE], cfloat (&buf_B_i)[BUF_B_SIZE]);

    void run(input_buffer<cfloat>& in, output_buffer<cfloat>& out);

    static void registerKernelClass(void) {
        REGISTER_FUNCTION(MyKernel::run);
        REGISTER_PARAMETER(buf_A);
        REGISTER_PARAMETER(buf_B);
    }
};
```

**Kernel source (`KERNEL.cpp`):**
```cpp
MyKernel::MyKernel(cfloat (&buf_A_i)[BUF_A_SIZE],
                   cfloat (&buf_B_i)[BUF_B_SIZE])
    : buf_A(buf_A_i), buf_B(buf_B_i)
{
    aie::set_rounding(aie::rounding_mode::conv_even);
    aie::set_saturation(aie::saturation_mode::saturate);
}

void MyKernel::run(input_buffer<cfloat>& in, output_buffer<cfloat>& out) {
    cfloat* work_A = buf_A;  // Use class member instead of stack
    cfloat* work_B = buf_B;
    // ... use work_A, work_B ...
}
```

**Graph (`KERNEL_graph.h`):**
```cpp
class MyKernel_graph : public graph {
private:
    std::vector<cfloat> buf_A_vec;
    std::vector<cfloat> buf_B_vec;
public:
    MyKernel_graph()
        : buf_A_vec(MyKernel::BUF_A_SIZE),
          buf_B_vec(MyKernel::BUF_B_SIZE)
    {
        kk = kernel::create_object<MyKernel>(buf_A_vec, buf_B_vec);
        // ...
    }
};
```

**Config (`aie.cfg`):**
```
stacksize=2048   # Back to default — arrays no longer on stack
```

---

## Workflow Steps

1. **Identify large stack arrays** in the kernel `run()` method
   - Look for `alignas(N) type array[SIZE]` declarations
   - Calculate total bytes: `SIZE * sizeof(type)`
   - Arrays > 256 bytes are candidates for this optimization

2. **Add buffer size constants** to the kernel class as `static constexpr unsigned`

3. **Declare array references** as class data members with `alignas(32)`

4. **Update constructor** to accept array references and use initializer list

5. **Register parameters** by adding `REGISTER_PARAMETER(buf_name)` for each buffer
   in `registerKernelClass()`

6. **Update graph** to declare `std::vector<type>` private members, initialize them
   in the constructor initializer list, and pass to `kernel::create_object<>()`

7. **Update `run()` method** to use class members instead of stack arrays
   - Replace `alignas(32) type arr[SIZE];` with `type* arr = buf_member;`

8. **Reduce stacksize** in `aie.cfg` back to default (2048)

9. **Verify** by recompiling and running x86sim to ensure functional equivalence

---

## Optional: Placement Control via Constraints

After registering parameters, you can control their memory bank placement in the
`.aiecst` constraints file:

```json
{
    "NodeConstraints": {
        "MyKernel_graph.kk": {
            "parameters": {
                "buf_A": { "bank": 0 },
                "buf_B": { "bank": 2 }
            }
        }
    }
}
```

This places `buf_A` and `buf_B` in different memory banks, eliminating potential
bank conflicts in loops that access both buffers simultaneously.

---

## Decision Points

| Condition | Action |
|-----------|--------|
| Array < 256 bytes | Usually not worth moving — keep on stack |
| Array > 256 bytes AND stacksize inflated | Apply this optimization |
| Multiple arrays accessed in same inner loop | Move both, place in different banks |
| Kernel is multi-instance (graph creates multiple) | Must use this pattern (static arrays would be shared) |
| Array is const/read-only (lookup table) | Use this pattern with `const` qualifier |

---

## Relationship to Other Skills

- **`create-kernel-hpp`**: This skill's "Create LUT Definitions" section defines the
  foundational pattern for array references and `REGISTER_PARAMETER` that this
  optimization extends to mutable working buffers.
- **`create-kernel-graph`**: The "Define LUT Initialization" section shows the
  `std::vector` + `kernel::create_object<>()` pattern used in the graph.
- **`extract-aie-loop-ii`**: Bank conflicts from co-located buffers can increase
  loop II. Use `extract-aie-loop-ii` before/after to measure improvement.
