/* PCdrv file backend, see psx_pcdrv.c. */
#ifndef ELMA_PSX_PCDRV_H
#define ELMA_PSX_PCDRV_H

#ifdef __cplusplus
extern "C" {
#endif

/* Adds the backend; -1 if the host does not answer. */
int psx_pcdrv_add_backend(void);

#ifdef __cplusplus
}
#endif

#endif
