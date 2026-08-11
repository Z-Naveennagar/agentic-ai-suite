#include <cstdio>
#include <cmath>

void example(const double *in, const double *in1,
double *out) {
#pragma HLS INTERFACE m_axi port=in bundle=aximm depth = 1026 channel=0
#pragma HLS INTERFACE m_axi port=in1 bundle=aximm depth = 1026 channel=0
#pragma HLS INTERFACE m_axi port=out bundle=aximm0 depth = 1024
for(int i = 0; i < 1024; i++)
   out[i] = in[i] + in1[i];
}

int main() {
    const int N = 1024;
    static double in_buf[1026];
    static double in1_buf[1026];
    static double out_buf[1024];

    for (int i = 0; i < 1026; ++i) {
        in_buf[i]  = static_cast<double>(i) * 0.25;
        in1_buf[i] = static_cast<double>(i) * 0.75;
    }

    example(in_buf, in1_buf, out_buf);

    int errors = 0;
    for (int i = 0; i < N; ++i) {
        double expected = in_buf[i] + in1_buf[i];
        if (std::fabs(out_buf[i] - expected) > 1e-12) {
            if (errors < 5) {
                std::printf("Mismatch at %d: got %f, expected %f\n",
                            i, out_buf[i], expected);
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