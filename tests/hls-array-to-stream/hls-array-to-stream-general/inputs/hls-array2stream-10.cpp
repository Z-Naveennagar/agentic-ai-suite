#define N 10
struct A {
  char color;
  int price;
};
void write(A array[N]) {
  for (int i=0; i<N; i++) {
    array[i].color = 'a';
    array[i].price = i;
  }
}
void read(A array[N]) {
  for (int i=0; i<N; i++) {
    char color = array[i].color;
    int price = array[i].price;
  }
}
void dut() {
#pragma HLS dataflow
  A array[N];
#pragma HLS stream variable=array depth=2
  write(array);
  read(array);
}

int main() {
  dut();
  return 0;
}
