#include <cstdio>

int main() {
    const int m = 4;
    const int n = 8;
    
    float a[m * n];
    float b[m * n];
    float s[m] = {0};
    
    // Initialize arrays
    for (int i = 0; i < m * n; i++) {
        a[i] = 1.0f;
        b[i] = 2.0f;
    }
    
    for (int j=0; j<m; j++) {
        for(int i=j; i<n; i++) {
            s[j] += a[j * n + i] * b[j * n + i];
        }
    }
    
    // Print results
    for (int j = 0; j < m; j++) {
        printf("s[%d] = %f\n", j, s[j]);
    }
    
    return 0;
}