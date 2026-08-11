float get_val(float merlin_in[100][100],int i, int j) {
#pragma HLS inline off
   return merlin_in[i][j];
}
void func_top_1(float merlin_in[100][100]) {
  for (int i = 0; i < 100; i++) {
    for (int j = 0; j < 100 - 5 + 1; j++) {
#pragma HLS pipeline II=1
#pragma HLS array_stencil variable=merlin_in
      for (int q = 0; q < 5; q++) 
        float tmp = get_val(merlin_in,i,j + q);
    }
  }
}

int main() {
  static float merlin_in[100][100];
  func_top_1(merlin_in);
  return 0;
}