//case 5:
#include<hls_stream.h>
int sum = 0;
void proc1( int *array, hls::stream<int> &c, int i){
    c.write( array[i]);
}

void proc2( int &scalar_in_out, hls::stream<int> &c)
{
    scalar_in_out *= c.read();
}

void dataflowFunc( int * mem, int &scalar_in_out)
{
    #pragma HLS dataflow
    hls::stream<int> c;
    for( int i = 0; i < 100; i++){
      #pragma HLS dataflow
      proc1( mem, c, i);
      proc2( scalar_in_out, c);
    }
}

void dut( hls::stream<int> &instream, hls::stream<int> &outstream)
{
    #pragma HLS top
    #pragma HLS interface axis  port =  instream, outstream
    int scalar_in_out = 0; 
    for (int i = 0; i < 100; i++){ 
        scalar_in_out += instream.read(); 
    }
    int mem[100];
    for( int i = 0; i < 100; i++ ){ 
        mem[i] = instream.read(); 
    }
    dataflowFunc(mem, scalar_in_out); 
    for( int i = 0; i < 100; i++){ 
        outstream.write(scalar_in_out + mem[i]);
    }
}