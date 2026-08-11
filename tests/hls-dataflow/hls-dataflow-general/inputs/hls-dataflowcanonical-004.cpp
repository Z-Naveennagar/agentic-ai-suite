//case 4:
#include<hls_stream.h>
void proc1( int *array, hls::stream<int> &pp)
{
    int sum = 0;
    for( int i = 0; i < 100; i ++){
        array[i+1] += array[i];
        sum+= array[i+1];
    }
    pp.write(sum);
}

void proc2( int &scalar_in_out, hls::stream<int> &s)
{
    scalar_in_out *= s.read();
}

//canonical , no unexpected statmenet in region 
void dataflowFunc( int * mem, int &scalar_in_out)
{
    #pragma HLS dataflow
    hls::stream<int> c;
    proc1( mem, c);
    proc2( scalar_in_out , c);
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