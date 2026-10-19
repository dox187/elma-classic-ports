# Memory card saves: included by elma.cmake.
list(APPEND ELMA_PSX_EXTRA_SOURCES
	${CMAKE_CURRENT_LIST_DIR}/memcard.c
	${CMAKE_CURRENT_LIST_DIR}/mclz.c
	${CMAKE_CURRENT_LIST_DIR}/psx_memcard_glue.cpp
)
