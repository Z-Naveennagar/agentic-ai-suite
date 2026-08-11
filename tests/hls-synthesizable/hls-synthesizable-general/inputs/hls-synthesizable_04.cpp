#include <cstdio>

unsigned foo(unsigned n)
{
    if (n == 0 || n == 1) return 1;
    return (foo(n - 2) + foo(n - 1));
}

int main()
{
    for (unsigned n = 0; n < 10; n++)
        std::printf("foo(%u) = %u\n", n, foo(n));
    return 0;
}
