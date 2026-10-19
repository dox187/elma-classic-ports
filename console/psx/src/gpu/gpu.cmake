# Video of the PlayStation version: included by elma.cmake.
#
#   ELMA_PSX_GPU          the game view is drawn by the GPU (gpu_draw.cpp):
#                         level polygons, pictures, objects and the bike from
#                         textures in VRAM; the core's software renderer
#                         (KIRAJ320.CPP, ECSET.CPP) is left out. OFF: the
#                         original software renderer draws the view.
#   ELMA_PSX_GPU_COMPARE  both renderers in one program, switched at run time
#                         by gpu_render_soft (test/gpu_compare_test.py).
#
# Always: the menus are presented by changed rectangles (gpu_menukep.cpp in
# place of MENUKEP.CPP) and memcpy is a word copy (gpu_memcpy.c).
option(ELMA_PSX_GPU "Draw the game view with the GPU" ON)
option(ELMA_PSX_GPU_COMPARE "Keep the software renderer next to the GPU one (tests)" OFF)

list(APPEND ELMA_PSX_EXTRA_SOURCES
	${CMAKE_CURRENT_LIST_DIR}/gpu_memcpy.c
	${CMAKE_CURRENT_LIST_DIR}/gpu_video.cpp
	${CMAKE_CURRENT_LIST_DIR}/gpu_menukep.cpp
)
list(APPEND ELMA_PSX_REPLACED MENUKEP.CPP)
# A copy of core code, compiled as the core is:
set_source_files_properties(${CMAKE_CURRENT_LIST_DIR}/gpu_menukep.cpp PROPERTIES COMPILE_OPTIONS "-w")

# The targets of the game are defined after this file, in the same directory:
add_link_options(-Wl,--wrap=memcpy)

if(ELMA_PSX_GPU OR ELMA_PSX_GPU_COMPARE)
	add_compile_definitions(ELMA_PSX_GPU)
	list(APPEND ELMA_PSX_EXTRA_SOURCES
		${CMAKE_CURRENT_LIST_DIR}/gpu_lgr.cpp
		${CMAKE_CURRENT_LIST_DIR}/gpu_traps.c
		${CMAKE_CURRENT_LIST_DIR}/gpu_level.cpp
		${CMAKE_CURRENT_LIST_DIR}/gpu_draw.cpp
	)
	if(ELMA_PSX_GPU_COMPARE)
		# The software renderer stays under other names; gpu_draw.cpp and
		# gpu_level.cpp call it when gpu_render_soft is set.
		add_compile_definitions(ELMA_PSX_GPU_COMPARE)
		set_source_files_properties(${ELMA_ROOT}/src/KIRAJ320.CPP PROPERTIES
			COMPILE_DEFINITIONS "kirajzol320=soft_kirajzol320")
		set_source_files_properties(${ELMA_ROOT}/src/ECSET.CPP PROPERTIES
			COMPILE_DEFINITIONS "betoltecseteket=soft_betoltecseteket")
	else()
		list(APPEND ELMA_PSX_REPLACED KIRAJ320.CPP ECSET.CPP)
	endif()
endif()
