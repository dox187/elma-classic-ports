#include <stdio.h>
#include <unistd.h>
FILE* elma_fopen(const char* path, const char* mode) { return fopen(path, mode); }
int elma_access(const char* path, int mode) { return access(path, mode); }
