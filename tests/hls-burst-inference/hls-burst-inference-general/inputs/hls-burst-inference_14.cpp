#include <cassert>

void example(double *in, double *out, int var, int step) {
#pragma HLS INTERFACE m_axi port=in bundle=aximm depth = 1026
#pragma HLS INTERFACE m_axi port=out bundle=aximm0 depth = 1024
   int i = 0;
   while (i != var) {
   assert(var < 1024);
   assert(step == 1);

     out[i] = in[i];
     i+=step;
   }
}

int main() {
  static double in[1026];
  static double out[1024];
  for (int i = 0; i < 1026; i++) in[i] = i * 0.5;
  for (int i = 0; i < 1024; i++) out[i] = 0.0;
  example(in, out, 16, 1);
  return 0;
}
