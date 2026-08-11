/*
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
*/
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <cassert>

constexpr int kInputDepth = 1026;
constexpr int kOutputDepth = 1024;
constexpr int kMaxSize = 1023;
constexpr double kInputScale = 0.5;
constexpr double kTolerance = 1e-12;
constexpr int kMaxPrintErrors = 5;

void example(const double *in, double *out, int size) {
#pragma HLS INTERFACE m_axi port=in bundle=aximm depth=1026
#pragma HLS INTERFACE m_axi port=out bundle=aximm0 depth=1024
#pragma HLS INTERFACE s_axilite port=size
#pragma HLS INTERFACE s_axilite port=return
  assert(size <= kMaxSize);
  for (int i = size; i > 1; --i) {
    out[i] = in[i - 1];
  }

}

void example_sw(const double *in, double *out, int size) {
  assert(size <= kMaxSize);
  for (int i = size; i > 1; --i) {
    out[i] = in[i - 1];
  }
}

int main() {
  const int num_elems = kMaxSize;
  static double in_buf[kInputDepth];
  static double out_buf[kOutputDepth];
  static double in_swbuf[kInputDepth];
  static double out_swbuf[kOutputDepth];

  for (int i = 0; i < kInputDepth; ++i) {
    in_buf[i] = static_cast<double>(i) * kInputScale;
    in_swbuf[i] = static_cast<double>(i) * kInputScale;
  }

  for (int i = 0; i < kOutputDepth; ++i) {
    out_buf[i] = -1.0;
    out_swbuf[i] = -1.0;
  }

  example(in_buf, out_buf, num_elems);
  example_sw(in_swbuf, out_swbuf, num_elems);

  int errors = 0;
  for (int i = 0; i < num_elems; ++i) {
    if (std::fabs(out_buf[i] - out_swbuf[i]) > kTolerance) {
      if (errors < kMaxPrintErrors) {
        std::printf("Mismatch at %d: got %f, expected %f\n", i, out_buf[i], out_swbuf[i]);
      }
      ++errors;
    }
  }

  if (errors == 0) {
    std::printf("PASS\n");
    return 0;
  }
  std::printf("FAIL: %d mismatches\n", errors);
  return 1;
}