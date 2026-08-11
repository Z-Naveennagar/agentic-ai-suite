#include <cstdio>

unsigned foo(unsigned m, unsigned n)
{
    if (m == 0) return n;
    if (n == 0) return m;
    return foo(n, m % n);
}

int main()
{
    unsigned a = 48, b = 36;
    std::printf("foo(%u, %u) = %u\n", a, b, foo(a, b));
    return 0;
}
