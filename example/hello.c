#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <limits.h>

void echo_args(int argc, char *argv[]) {
    printf("Echoing %d arguments:\n", argc-1);
    for (int i = 1; i < argc; ++i)
        puts(argv[i]);
}

long int get_ret_code(char *str) {
    /* set errno to 0 before calling strtol,
     * if the func fails, this is the only way
     * to know it for sure
     * */
    errno = 0;
    long int val = strtol(str, NULL, 10);

    /* Check if we parsed the string correctly,
     * if not, just discard the number.
     * */
    if ((errno == ERANGE && (val == LONG_MAX || val == LONG_MIN))
            || (errno != 0 && val == 0)) {
        /* invalid string, move on */
        val = 0;
    }

    return val;
}

int main(int argc, char *argv[]) {
    puts("Hello world!\n");
    if (argc > 1) {
        echo_args(argc, argv);

        /* I wonder, what would happen if val is outside
         * of the range that an 'int' can represent.
         * */
        int val = get_ret_code(argv[1]);

        return val;
    }

    return 0;
}
