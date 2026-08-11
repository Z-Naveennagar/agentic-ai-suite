#include <cstdio>
#include <stdlib.h>

#define N 32

using din_t  = int;
using dout_t = long long;
using dsel_t = int;

dout_t malloc_removed(din_t din[N], dsel_t width) {

    long long *out_accum = (long long *)malloc(sizeof(long long));
    int *array_local = (int *)malloc(64 * sizeof(int));

    int i, j;

    LOOP_SHIFT:for (i = 0; i < N - 1; i++) {
        if (i < width)
            *(array_local + i) = din[i];
        else
            array_local[i] = din[i] >> 2;
    }

    *out_accum = 0;
    LOOP_ACCUM:for (j = 0; j < N - 1; j++) {
        *out_accum += *(array_local + j);
    }

    dout_t result = *out_accum;

    free(out_accum);
    free(array_local);

    return result;
}

int main()
{
    din_t din[N];
    for (int i = 0; i < N; i++)
        din[i] = i;

    dsel_t width = 16;
    dout_t out = malloc_removed(din, width);

    std::printf("out = %lld\n", out);
    return 0;
}
