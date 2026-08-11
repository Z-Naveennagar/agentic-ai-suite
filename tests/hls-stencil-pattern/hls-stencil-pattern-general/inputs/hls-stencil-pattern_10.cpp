void func_top_1(float *merlin_in, float out[100][100]) {
  for (int i = 0; i < 100; i++) {
    for (int j = 0; j < 100 - 5 + 1; j++) {
#pragma HLS pipeline II=1
#pragma HLS array_stencil variable=merlin_in
      float tmp = 0.0;
      for (int q = 0; q < 5; q++) 
        tmp += merlin_in[i * 100 + j + q];
      out[i][j] = tmp;
    }
  }
}

int main() {
  static float merlin_in[100 * 100];
  static float out[100][100];
  for (int i = 0; i < 100 * 100; i++) merlin_in[i] = (float)i;
  func_top_1(merlin_in, out);
  return 0;
}