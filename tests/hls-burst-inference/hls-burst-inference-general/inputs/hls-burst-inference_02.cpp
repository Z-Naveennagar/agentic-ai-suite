#include <cstdio>
#include <cstdlib>
#include <cstring>

#define N 256

struct mytype {
  char R;
  char G;
  char B;
} __attribute__((packed, aligned(4)));
typedef struct mytype MyType;

void example(MyType a[N]) {
#pragma HLS INTERFACE m_axi port=a bundle=a
  int i;
  MyType buff[N];
  for (i = 0; i != N; ++i) {
#pragma HLS pipeline
    buff[i].R = a[i].R;
    buff[i].G = a[i].G;
    buff[i].B = a[i].B;
    a[i].R = a[i].R + 100;
    a[i].G = a[i].G + 10;
    a[i].B = a[i].B + 1;
  }
}

int main() {
    static MyType a[N];
    static MyType ref[N];

    for (int i = 0; i < N; ++i) {
        a[i].R = static_cast<char>(i);
        a[i].G = static_cast<char>(i + 1);
        a[i].B = static_cast<char>(i + 2);
        ref[i] = a[i];
    }

    example(a);

    int errors = 0;
    for (int i = 0; i < N; ++i) {
        char exp_R = static_cast<char>(ref[i].R + 100);
        char exp_G = static_cast<char>(ref[i].G + 10);
        char exp_B = static_cast<char>(ref[i].B + 1);
        if (a[i].R != exp_R || a[i].G != exp_G || a[i].B != exp_B) {
            if (errors < 5) {
                std::printf("Mismatch at %d: got (%d,%d,%d) expected (%d,%d,%d)\n",
                            i, a[i].R, a[i].G, a[i].B, exp_R, exp_G, exp_B);
            }
            ++errors;
        }
    }

    if (errors == 0) {
        std::printf("PASS\n");
        return 0;
    }
    std::printf("FAIL: %d mismatches\n", errors);
    return 1;
}