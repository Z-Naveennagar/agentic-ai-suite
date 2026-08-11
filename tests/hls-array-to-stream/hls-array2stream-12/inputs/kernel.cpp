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

void dut(A in[N], A out[N]) {
#pragma HLS dataflow
#pragma HLS interface axis port=in
#pragma HLS interface axis port=out
  for (int i=0; i<N; i++) {
    out[i]= in[i];
  }
}

int main() {
  A in[N], out[N];
  for (int i = 0; i < N; i++) {
    in[i].color = 'a' + i;
    in[i].price = i * 10;
  }
 
  dut(in, out);
  return 0;
}