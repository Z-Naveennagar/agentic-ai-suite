void example(const double *in, const double *in1,
double *out) {
#pragma HLS INTERFACE m_axi port=in bundle=aximm depth = 1026 channel=0
#pragma HLS INTERFACE m_axi port=in1 bundle=aximm depth = 1026 channel=0
#pragma HLS INTERFACE m_axi port=out bundle=aximm depth = 1024 channel=0
for(int i = 0; i < 1024; i++)
   out[i] = in[i] + in1[i];
}

int main() {
  static double in[1026];
  static double in1[1026];
  static double out[1024];
  for (int i = 0; i < 1026; i++) { in[i] = i * 0.5; in1[i] = i; }
  for (int i = 0; i < 1024; i++) out[i] = 0.0;
  example(in, in1, out);
  return 0;
}