//case 3:
#include<hls_stream.h>
void proc1( int *array, int *pp)
{
    for( int i = 0; i < 99; i ++){
        array[i+1] += array[i];
    }
    *pp = array[100];
}

void proc2( int &scalar_in_out, int &c)
{
    scalar_in_out *= c;
}

//canonical , no unexpected statement in dataflow region 
void dataflowFunc( int * mem, int &scalar_in_out)
{
    int c;
    #pragma HLS dataflow
    proc1( mem, &c);
    proc2( scalar_in_out , c);
}

void dut( hls::stream<int> &instream, hls::stream<int> &outstream)
{
    #pragma HLS top
    #pragma HLS interface axis  port =  instream,outstream
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
