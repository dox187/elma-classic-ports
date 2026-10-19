# The memory of the PlayStation version: included by elma.cmake.
#
# psx_mem.c is the heap (in place of the SDK's malloc, see there). The level
# editor is left out: its menu entry is hidden (ELMA_HANDHELD) and
# psx_noeditor.cpp keeps the few things of EDITUJ.CPP the game uses.
list(APPEND ELMA_PSX_EXTRA_SOURCES
	${CMAKE_CURRENT_LIST_DIR}/psx_mem.c
	${CMAKE_CURRENT_LIST_DIR}/psx_noeditor.cpp
)
list(APPEND ELMA_PSX_REPLACED
	EDITHELP.CPP EDITMENU.CPP EDITPLAY.CPP EDITTOLT.CPP EDITTOOL.CPP EDITUJ.CPP ED_CHECK.CPP
)
# A copy of core code, compiled as the core is:
set_source_files_properties(${CMAKE_CURRENT_LIST_DIR}/psx_noeditor.cpp PROPERTIES COMPILE_OPTIONS "-w")
