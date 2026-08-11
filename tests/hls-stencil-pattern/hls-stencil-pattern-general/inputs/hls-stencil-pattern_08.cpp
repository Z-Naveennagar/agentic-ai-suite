#define HS 32
#define WS 128
#define FW 2
#define FH 2
void conv2d(float in[HS][WS], float filter[FH][FW], float out[HS-FH+1][WS-FW+1]) {
    float filter_buf[FH][FW];
    for (int p = 0; p < FH; p++)
        for (int q = 0; q < FW; q++)
            filter_buf[p][q] = filter[p][q];
    for (int i = 0; i< HS-FH+1; i+=2)
        for (int j = 0; j< WS-FW+1; j+=2) {
#pragma HLS pipeline II=1
#pragma HLS array_stencil variable=in
            float tmp = 0.0f;
            for (int p = 0; p < FH; p++)
            for (int q = 0; q < FW; q++)
                tmp += in[i+p][j+q] * filter_buf[p][q];
            out[i][j] = tmp;
    }
  }

int main() {
  static float in[HS][WS];
  static float filter[FH][FW];
  static float out[HS - FH + 1][WS - FW + 1];
  for (int i = 0; i < HS; i++)
    for (int j = 0; j < WS; j++)
      in[i][j] = (float)(i + j);
  for (int p = 0; p < FH; p++)
    for (int q = 0; q < FW; q++)
      filter[p][q] = 1.0f;
  conv2d(in, filter, out);
  return 0;
}