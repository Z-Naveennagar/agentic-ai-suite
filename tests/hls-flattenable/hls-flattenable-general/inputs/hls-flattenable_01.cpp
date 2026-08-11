#include <stdio.h>

int main() {
    int i, j;
    int acc;
    int A[20];
    int B[20];

    // Initialize A
    for (i = 0; i < 20; i++) {
        A[i] = i + 1;
    }

    for (i = 0; i < 20; i++) {
        acc = 0;
        for (j = 0; j < 20; j++) {
            acc += A[j] * j;
        }
        if (i % 2 == 0)
            B[i] = acc / 20;
        else
            B[i] = 0;
    }

    // Print results
    for (i = 0; i < 20; i++) {
        printf("B[%d] = %d\n", i, B[i]);
    }

    return 0;
}