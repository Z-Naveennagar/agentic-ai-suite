#include <iostream>

int main() {
    int i, j;
    int acc = 0;
    int A[20];
    int B[20];

    for (int k = 0; k < 20; ++k) {
        A[k] = k + 1;
    }

    for (i = 0; i < 20; i++) {
    LOOP_J:
        for (j = 0; j < 20; j++) {
            if (j == 0)
                acc = 0;
            acc += A[j] * j;
            if (j == 19) {
                if (i % 2 == 0)
                    B[i] = acc / 20;
                else
                    B[i] = 0;
            }
        }
    }

    for (int k = 0; k < 20; ++k) {
        std::cout << "B[" << k << "] = " << B[k] << '\n';
    }

    return 0;
}