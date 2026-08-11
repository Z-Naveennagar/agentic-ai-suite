#include <cstdio>
#include <cstdlib>
#include <cmath>

void dut(const double *in,
         double *out, int size) {
#pragma HLS INTERFACE m_axi port=in  bundle=aximm0 depth = 1026
#pragma HLS INTERFACE m_axi port=out bundle=aximm1 depth = 1024
#pragma HLS INTERFACE s_axilite port=size
#pragma HLS INTERFACE s_axilite port=return
    for (int i = 0; i < size; i++)
        out[i] = in[i];
}

int main() {
    const int N = 1024;
    static double in_buf[1026];
    static double out_buf[1024];

    for (int i = 0; i < 1026; ++i) {
        in_buf[i] = static_cast<double>(i) * 0.5;
    }

    dut(in_buf, out_buf, N);

    int errors = 0;
    for (int i = 0; i < N; ++i) {
        if (std::fabs(out_buf[i] - in_buf[i]) > 1e-12) {
            if (errors < 5) {
                std::printf("Mismatch at %d: got %f, expected %f\n",
                            i, out_buf[i], in_buf[i]);
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