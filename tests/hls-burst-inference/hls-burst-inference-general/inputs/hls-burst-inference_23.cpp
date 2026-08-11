void dut(const double *in, 
double *out, int size) {
for(int i = 0; i < size; i++)
   out[i] = in[i];
}

int main() {
  static double in[1026];
  static double out[1024];
  for (int i = 0; i < 1026; i++) in[i] = i * 0.5;
  for (int i = 0; i < 1024; i++) out[i] = 0.0;
  dut(in, out, 1024);
  return 0;
}