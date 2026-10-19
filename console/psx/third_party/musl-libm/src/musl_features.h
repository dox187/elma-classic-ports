/* Replaces musl's <features.h> for the few vendored math files. Part of the
 * vendored musl subset, see ../README.md. */
#ifndef MUSL_FEATURES_H
#define MUSL_FEATURES_H
#define hidden __attribute__((__visibility__("hidden")))
#endif
