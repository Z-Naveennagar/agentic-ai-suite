#define M 10
#define N 10
int foo(int i, int s) {
#pragma HLS inline off
return i / s;
}
int kernel(int a[N][M], int b[N][M], int s) {
int r = 0;
L1:
for (int i = 0; i < N; ++i) {
    r += foo(i, s);
L2:
    for (int j = 0; j < M; ++j) {
#pragma HLS LOOP_FLATTEN
#pragma HLS pipeline
        a[i][j] += b[i][j];
    }
}
return r;
}
