void example(double *in, double *out, int var) {
#pragma HLS INTERFACE m_axi port=in bundle=aximm depth = 1026
#pragma HLS INTERFACE m_axi port=out bundle=aximm0 depth = 1024
  for(int i = 0; i<1024; i++) {
    if (i%var == 0)
      out[i] = in[i+var];
    else
      out[i] = in[i];
  }
}

int main() {
  static double in[1026];
  static double out[1024];
  for (int i = 0; i < 1026; i++) in[i] = i * 0.5;
  for (int i = 0; i < 1024; i++) out[i] = 0.0;
  example(in, out, 2);
  return 0;
}
