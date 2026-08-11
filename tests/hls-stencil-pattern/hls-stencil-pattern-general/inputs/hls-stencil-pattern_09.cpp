void func_top_4(int c[514][514][514], int cc[514][514]) {
  int sum;
  for (int i = 1; i < 513; i++) {
    for (int j = 1; j < 513; j++) {
      for (int k = 1; k < 513; k++) {
#pragma HLS pipeline II=1
#pragma HLS array_stencil variable=c
        sum += c[i][j][k] + c[i][j+1][k] + c[i][j-1][k] + c[i+1][j][k] +
          c[i-1][j][k] + c[i][j][k-1] + c[i][j][k+1];
      }
    }
  }
}

int main() {
  int (*c)[514][514] = new int[514][514][514]();
  static int cc[514][514];
  func_top_4(c, cc);
  delete[] c;
  return 0;
}