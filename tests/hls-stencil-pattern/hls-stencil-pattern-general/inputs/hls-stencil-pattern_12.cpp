#include <cstdint>
#define col_size 64
#define row_size 128
#define DTYPE int32_t
void stencil (DTYPE input[row_size][col_size], DTYPE S[row_size*col_size], DTYPE F[9]){
  int r, c, k1, k2;
  DTYPE temp, mul;
  DTYPE F_buf[3][3];
  for (k1=0;k1<3;k1++)
    for (k2=0;k2<3;k2++)
      F_buf[k1][k2] = F[k1*3+k2];
  for (r=0; r<row_size-2; r++) {
#pragma HLS array_stencil variable=input
    for (c=0; c<col_size-2; c++) {
#pragma HLS pipeline II=1
      temp = (DTYPE)0;
      for (k1=0;k1<3;k1++){
        for (k2=0;k2<3;k2++){
          mul = F_buf[k1][k2] * input[r+k1][c+k2];
          temp += mul;
        }
      }
      *(S + (r*col_size) + c) = temp;
    }
  }
}

int main() {
  static DTYPE O[row_size][col_size];
  static DTYPE S[row_size * col_size];
  DTYPE F[9];
  for (int i = 0; i < row_size; i++)
    for (int j = 0; j < col_size; j++)
      O[i][j] = i + j;
  for (int i = 0; i < 9; i++) F[i] = 1;
  stencil(O, S, F);
  return 0;
}