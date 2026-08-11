#define N 1024

struct mytype {
  int R;
  int G;
  int B;
};

typedef struct mytype MyType;

void example(MyType a[N], MyType b[N]) {
  #pragma HLS INTERFACE m_axi port = a depth = N
  #pragma HLS INTERFACE m_axi port = b depth = N
  MyType buff[N];

  for (int i = 0; i < N; ++i)
    buff[i] = a[i];

  for (int i = 0; i < N; ++i) {
    buff[i].R += 50;
    buff[i].G += 10;
    buff[i].B += 1;
  }

  for (int i = 0; i < N; ++i)
    b[i] = buff[i];
}

int main() {
  static MyType a[N];
  static MyType b[N];
  for (int i = 0; i < N; ++i) { a[i].R = i; a[i].G = i; a[i].B = i; }
  example(a, b);
  return 0;
}