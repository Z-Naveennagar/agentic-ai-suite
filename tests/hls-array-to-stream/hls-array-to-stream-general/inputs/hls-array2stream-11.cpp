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
    tmp.color = 'a';
    tmp.price = i; // set tmp element field individually
    array[i] = tmp; // write array element in entirety
  }
}
void read(A array[N]) {
  for (int i=0; i<N; i++) {
    A tmp = array[i]; // load array element in entirety into a tmp local one
    int price = tmp.price; // access field from tmp local one
    char color = tmp.color;
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
