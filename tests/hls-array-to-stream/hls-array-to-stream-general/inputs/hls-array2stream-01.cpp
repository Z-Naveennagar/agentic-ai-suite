#include <cstdio>

#define N 32

void write(int array[N]) {
  for (int i = 0; i < N; i++)
    array[i] = i;
}

void read(int array[N]) {
  for (int i = N - 1; i >= 0; i--)
    printf("array[%d] = %d\n", i, array[i]);
}

void dut() {
#pragma HLS dataflow
  int array[N];
#pragma HLS stream variable=array depth=2
  write(array);
  read(array);
}

int main() {
  dut();
  return 0;
}
