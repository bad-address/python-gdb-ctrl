// gcc -o glad glad.c -lpthread

#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>

#define CORES 4

int warm_neurotoxins() {
    int temperature = 0;
    while (temperature < 60) {
        sleep(1);
        temperature += 10;
    }

    return 0;
}

void* release_neurotoxins(void* ctx) {
    if (ctx) return NULL;

    printf("Warming neurotoxins, please wait.\n");
    warm_neurotoxins();
    printf("Releasing neurotoxins. Have a nice day.\n");
    exit(1);
    return NULL;
}

int incinerate(int *cores, int core_num) {
    cores[core_num] = 0;
    printf("Core number %d incinerated.\n", core_num);
    return 0;
}

int chk_system_health(int *cores) {
    for (int i = 0; i < CORES; i++) {
        if (cores[i])
            return 0; // good
    }

    return -1; //bad
}

int party() {
    printf("Have a piece of cake. Have fun\n");
    return 0;
}

int main(int argc, char *argv[]) {
    pthread_t th;
    pthread_create(&th, NULL, release_neurotoxins, NULL);

    int cores[CORES] = {1};

    for (int i = 1; i < argc; ++i) {
        int core_num = strtol(argv[i], NULL, 10);
        if (core_num <= 0 || core_num >= 10) {
            printf("You'll miss the party -- %s\n", argv[i]);
            continue;
        }

        incinerate(cores, core_num);
        if (chk_system_health(cores) != 0) {
            printf("System error.\n");
            return 0;
        }
    }

    sleep(9999);
    return 1;
}
