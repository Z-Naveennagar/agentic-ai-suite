#include <cstdio>

#define HS 32
#define WS 128
#define FW 2
#define FH 2

void conv2d(float in[HS][WS], float filter[FH][FW], float out[HS-FH+1][WS-FW+1]) {
    float filter_buf[FH][FW];
    for (int p = 0; p < FH; p++)
        for (int q = 0; q < FW; q++)
            filter_buf[p][q] = filter[p][q];

    for (int i = 0; i< HS-FH+1; i++)
        for (int j = 0; j< WS-FW+1; j++) {
#pragma HLS pipeline II=1
#pragma HLS array_stencil variable=filter_buf
            float tmp = 0.0f;
            for (int p = 0; p < FH; p++)
            for (int q = 0; q < FW; q++)
                tmp += in[i+p][j+q] * filter_buf[p][q];
            out[i][j] = tmp;
        }
}

int main() {
    static float in_buf[HS][WS];
    static float flt[FH][FW] = {{1, 0}, {0, 1}};
    static float out_buf[HS-FH+1][WS-FW+1];
    for (int i = 0; i < HS; ++i)
        for (int j = 0; j < WS; ++j)
            in_buf[i][j] = static_cast<float>(i + j);
    conv2d(in_buf, flt, out_buf);
    std::printf("%f\n", out_buf[0][0]);
    return 0;
}