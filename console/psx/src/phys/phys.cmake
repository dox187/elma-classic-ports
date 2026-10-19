# The fixed point physics (see fixphys.h), included by elma.cmake. It
# replaces the double physics of LEPTET.CPP and the files only it calls
# (BEALLIT.CPP, UTKOZES.CPP, UTKOZES2.CPP).
set(ELMA_PSX_PHYS_DIR ${CMAKE_CURRENT_LIST_DIR})
list(APPEND ELMA_PSX_EXTRA_SOURCES
	${ELMA_PSX_PHYS_DIR}/fixphys.c
	${ELMA_PSX_PHYS_DIR}/phys_glue.cpp
	${ELMA_PSX_PHYS_DIR}/phys_api.cpp
)
list(APPEND ELMA_PSX_REPLACED LEPTET.CPP BEALLIT.CPP UTKOZES.CPP UTKOZES2.CPP)

# The check that the PlayStation computes the same bits as the host
# (test/phys_check.c, run by test/phys_test.py --ps1).
file(GLOB ELMA_PSX_PHYS_LIBM ${CMAKE_CURRENT_SOURCE_DIR}/third_party/musl-libm/src/*.c)
psn00bsdk_add_executable(physcheck GPREL
	${CMAKE_CURRENT_SOURCE_DIR}/test/phys_check.c
	${ELMA_PSX_PHYS_DIR}/fixphys.c
	${ELMA_PSX_PHYS_LIBM}
)
target_include_directories(physcheck BEFORE PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src/include)
target_include_directories(physcheck PRIVATE ${ELMA_PSX_PHYS_DIR}
	${CMAKE_CURRENT_SOURCE_DIR}/third_party/musl-libm/src)
target_compile_definitions(physcheck PRIVATE ELMA_PSX)
target_compile_options(physcheck PRIVATE -fwrapv -fno-strict-aliasing -ffp-contract=off -std=gnu11)
set_source_files_properties(${ELMA_PSX_PHYS_LIBM} TARGET_DIRECTORY physcheck PROPERTIES COMPILE_OPTIONS "-w")
