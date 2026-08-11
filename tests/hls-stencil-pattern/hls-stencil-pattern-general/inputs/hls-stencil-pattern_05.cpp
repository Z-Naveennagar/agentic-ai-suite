#include <cstdio>
#include <cstdint>

#define col_size 64
#define row_size 128
#define DTYPE int32_t

void stencil(DTYPE O[row_size][col_size], DTYPE S[row_size*col_size], DTYPE F[9]) {
    DTYPE F_buf[3][3];
    for (int i = 0; i < 3; ++i)
        for (int j = 0; j < 3; ++j)
            F_buf[i][j] = F[i*3 + j];

    int r, c, k1, k2;
    DTYPE temp, mul;
    for (r=0; r<row_size-2; r++) {
        for (c=0; c<col_size-2; c++) {
#pragma HLS pipeline II=1
#pragma HLS array_stencil variable=O
            temp = (DTYPE)0;
            for (k1=0;k1<3;k1++){
                for (k2=0;k2<3;k2++){
                    mul = F_buf[k1][k2] * O[r+k1][c+k2];
                    temp += mul;
                }
            }
            O[r][c] = temp;
            *(S + (r*col_size) + c) = temp;
        }
    }
}

int main() {
    static DTYPE O[row_size][col_size];
    static DTYPE S[row_size*col_size];
    DTYPE F[9] = {1,0,0,0,1,0,0,0,1};
    for (int i = 0; i < row_size; ++i)
        for (int j = 0; j < col_size; ++j)
            O[i][j] = i + j;
    stencil(O, S, F);
    std::printf("%d\n", (int)S[0]);
    return 0;
}