/* PCdrv file backend: during development the emulator (PCSX-Redux -pcdrv
 * -pcdrvbase DIR) serves the game data from a host directory. Only for
 * emulators and dev cartridges: on a console without PCdrv the break
 * instructions it uses would crash, so the build adds it only on request
 * (ELMA_PSX_PCDRV). */
#include <psxsn.h>

#include "psx_file.h"
#include "psx_pcdrv.h"

static int pcdrv_open(void* context, const char* path, long* size) {
	(void)context;
	const int fd = PCopen(path, PCDRV_MODE_READ);
	if (fd < 0) return -1;
	const int end = PClseek(fd, 0, PCDRV_SEEK_END);
	if (end < 0) {
		PCclose(fd);
		return -1;
	}
	*size = end;
	return fd;
}

static int pcdrv_read(void* context, int handle, long offset, void* buffer, int n) {
	(void)context;
	if (PClseek(handle, (int)offset, PCDRV_SEEK_SET) < 0) return -1;
	return PCread(handle, buffer, (size_t)n);
}

static void pcdrv_close(void* context, int handle) {
	(void)context;
	PCclose(handle);
}

int psx_pcdrv_add_backend(void) {
	if (PCinit() < 0) return -1;
	/* PCdrv cannot list directories. */
	const psx_file_backend backend = {"pcdrv", pcdrv_open, pcdrv_read, pcdrv_close, 0, 0};
	psx_file_add_backend(&backend);
	return 0;
}
