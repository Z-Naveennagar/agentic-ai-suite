#define N 10
struct A {
  char color;
  int price;
  A& operator=(const A& a) {
    color = a.color;
    price = a.price;
    return *this;
  }
};
void write(A array[N]) {
  for (int i=0; i<N; i++) {
    A tmp; // define a tmp array element first
    tmp.color = i;
    tmp.price = i+3;
    array[i] = tmp; // write array element in entirety
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