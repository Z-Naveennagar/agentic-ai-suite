#define N 10
struct A {
  char color;
  int price;
};
void write(A array[N]) {
  for (int i=0; i<N; i++) {
    array[i].color = i;
    array[i].price = i+3;
  }
}
void dut(A a[N]) {
#pragma HLS dataflow
#pragma HLS interface ap_fifo port=a
  write(a);
}

int main() {
  A a[N];
  dut(a);
  return 0;
}