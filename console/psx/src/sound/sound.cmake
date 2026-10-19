# Sound on the SPU: included by elma.cmake. SDL_HHIGH.CPP is the original
# mixer (no SDL dependency); psx_sound.cpp replaces SDL_SOUND.CPP and
# H_DUMMY.CPP provides the silent stubs that are no longer wanted.
list(APPEND ELMA_PSX_EXTRA_SOURCES
	${ELMA_ROOT}/desktop/F_SDL/SDL_HHIGH.CPP
	${CMAKE_CURRENT_LIST_DIR}/psx_sound.cpp
	${CMAKE_CURRENT_LIST_DIR}/spu_stream.c
	${CMAKE_CURRENT_LIST_DIR}/spu_adpcm.c
)
list(APPEND ELMA_PSX_REPLACED H_DUMMY.CPP)
set_source_files_properties(${ELMA_ROOT}/desktop/F_SDL/SDL_HHIGH.CPP PROPERTIES COMPILE_OPTIONS "-w")
