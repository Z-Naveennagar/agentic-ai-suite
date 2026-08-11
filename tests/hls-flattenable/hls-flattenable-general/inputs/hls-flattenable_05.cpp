#include <cstdio>

#define N 8
#define M 4

void kernel(int a[N][M], int b[N][M]) {
L1:
  for (unsigned int i = 0; i < N; ++i) {
  L2:
    for (unsigned int j = 0; j < M; j += 3) {
#pragma HLS pipeline
      a[i][j] += b[i][j] + i;
      if (j + 1 >= M)
        break;
      a[i][j + 1] += b[i][j + 1] + i;
      if (j + 2 >= M)
        break;
      a[i][j + 2] += b[i][j + 2] + i;
    }
  }
}

int main() {
  int a[N][M];
  int b[N][M];

  for (unsigned int i = 0; i < N; ++i) {
    for (unsigned int j = 0; j < M; ++j) {
      a[i][j] = 0;
      b[i][j] = i + j;
    }
  }

  kernel(a, b);

  for (unsigned int i = 0; i < N; ++i) {
    for (unsigned int j = 0; j < M; ++j)
      printf("%d ", a[i][j]);
    printf("\n");
  }

  return 0;
}