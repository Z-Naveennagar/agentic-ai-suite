void func1(double *out, double *in) {
#pragma HLS inline off
for(int i = 0; i < 100; i++)
   out[i] = in[i];
}
void func2(double *out, double *in) {
#pragma HLS inline off
for(int i = 101; i < 200; i++)
   out[i] = in[i];
}
void example(double *in, double *out) {
#pragma HLS INTERFACE m_axi port=in bundle=aximm depth = 1026
#pragma HLS INTERFACE m_axi port=out bundle=aximm0 depth = 1024
#pragma HLS dataflow
  func1(out, in);
  func2(out, in);
}

int main() {
  static double in[1026];
  static double out[1024];
  for (int i = 0; i < 1026; i++) in[i] = i * 0.5;
  for (int i = 0; i < 1024; i++) out[i] = 0.0;
  example(in, out);
  return 0;
}