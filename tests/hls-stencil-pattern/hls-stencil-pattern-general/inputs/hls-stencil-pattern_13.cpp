void func_top_4(int c[514][514], int cc[514][514]) {
  int sum;
  for (int i = 1; i < 513; i++) {
    for (int j = 1; j < 513; j++) {
#pragma HLS pipeline II=1
#pragma HLS array_stencil variable=c
        sum += c[i][j] + c[i][j+1] + c[i][j-1] + c[i+1][j] + c[i-1][j];
    }
  }
}

int main() {
  static int c[514][514];
  static int cc[514][514];
  func_top_4(c, cc);
  return 0;
}