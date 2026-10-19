// The fixed point physics with the interface of LEPTET.CPP (phys_glue.cpp).
#ifndef PHYS_GLUE_H
#define PHYS_GLUE_H

struct motorst;

void fxg_resetleptet( motorst* pmot );
void fxg_leptet( motorst* pmot, double most, double dt, int gaz, int fek,
				 int ugrik1, int ugrik2 );
int fxg_vizsgalat( motorst* pmot );
double fxg_kiszamolsurlodast( void );
// The next step reads the whole state from the double fields of motorst
// (for tests that set it).
void fxg_reimport( motorst* pmot );
// Frees the converted level (the next step converts the level again).
void fxg_unload_level( void );

#endif
