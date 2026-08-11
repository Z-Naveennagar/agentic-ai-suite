#include <cstdio>

using din_t  = int;
using dint_t = int;
using dout_t = int;

void sumsub_func(din_t *A, din_t *B, dint_t *apb, dint_t *amb)
{
    if (!A || !B || !apb || !amb) return;
    *apb = *A + *B;
    *amb = *A - *B;
}

int shift_func(dint_t *in1, dint_t *in2, dout_t *outA, dout_t *outB)
{
    if (!in1 || !in2 || !outA || !outB) return -1;
    *outA = *in1 >> 1;
    *outB = *in2 >> 2;
    return 0;
}

void hier_func4(din_t A, din_t B, dout_t *C, dout_t *D)
{
    dint_t apb = 0, amb = 0;
    sumsub_func(&A, &B, &apb, &amb);

#ifndef __SYNTHESIS__
    FILE *fp1; // The following code is ignored for synthesis
    char filename[255];
    std::snprintf(filename, sizeof(filename), "Out_apb_%03d.dat", apb);
    fp1 = std::fopen(filename, "w");
    if (fp1) {
        std::fprintf(fp1, "%d\n", apb);
        std::fclose(fp1);
    }
#endif

    shift_func(&apb, &amb, C, D);
}

int main()
{
    din_t A = 10, B = 6;
    dout_t C = 0, D = 0;
    hier_func4(A, B, &C, &D);
    return 0;
}