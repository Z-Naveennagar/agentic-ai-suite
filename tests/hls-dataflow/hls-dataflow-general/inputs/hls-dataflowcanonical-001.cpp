//case 1:
#include<hls_stream.h>
void proc2( int &scalar_in_out, int *mem)
{
    for( int i = 0 ; i < 10; i++){
        scalar_in_out += mem[i];
    }
}


//no canonica,  dataflow region containing loop statement
void dataflowFunc( int * mem, int &scalar_in_out)
{
    #pragma HLS dataflow
    for( int i = 0; i < 100; i++){
        scalar_in_out += mem[i];
    }
    proc2( scalar_in_out , mem);
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