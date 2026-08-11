#include <cstdio>

#define N 8
#define M 4

void kernel(int a[N][M]) {
L1:
  for (unsigned int i = 0; i < N; ++i) {
    int val = 0;
    if (i % 4 == 0)
      val = i;
    else if (i % 4 == 1)
      val = i + 1;
    else if (i % 4 == 2)
      val = i + 2;
    else if (i % 4 == 3)
      val = i + 3;
  L2:
    for (unsigned int j = 0; j < M; ++j) {
#pragma HLS pipeline
      a[i][j] += val + i;
    }
  }
}

int main() {
  int a[N][M];

  for (unsigned int i = 0; i < N; ++i)
    for (unsigned int j = 0; j < M; ++j)
      a[i][j] = 0;

  kernel(a);

  for (unsigned int i = 0; i < N; ++i) {
    for (unsigned int j = 0; j < M; ++j)
      printf("%d ", a[i][j]);
    printf("\n");
  }

  return 0;
}