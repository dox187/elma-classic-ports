# The game: the original core of src/ with the PlayStation platform layer of
# src/ here. Included by CMakeLists.txt. Output: elma.exe and elma.map.

# The data of the current (Steam) release is the registered one; OFF for the
# shareware elma.res, as the desktop option of the same name.
option(ELMA_PSX_REGISTERED "Build the registered version; needs the registered game data" ON)

set(ELMA_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..)

# The core files of the desktop builds (CMakeLists.txt at the top), with the
# silent sound of the terminal version. SZURO.CPP (picture filters for the
# desktop zoom) is replaced by src/psx_szuro.cpp. The editor's files are
# listed as on the handhelds (where only its menu entry is hidden,
# ELMA_HANDHELD); src/mem/mem.cmake leaves them out.
set(ELMA_PSX_CORE
	ABC8.CPP ADATOK.CPP ANIM.CPP BEALLIT.CPP BESTTIME.CPP
	CUSTOM.CPP DIALOG.CPP DIALOG32.CPP DIGIT.CPP DISPLAY.CPP DOBOZ.CPP
	D_PIC.CPP ECSET.CPP EDITHELP.CPP EDITMENU.CPP EDITPLAY.CPP EDITTOLT.CPP
	EDITTOOL.CPP EDITUJ.CPP ED_CHECK.CPP FOGOCSKA.CPP GOLYKISZ.CPP GYUJTEM.CPP
	GOLYOK.CPP GOLYUTK.CPP GRAPH.CPP GYURU.CPP H_WAV.CPP JATEKOS.CPP
	KIRAJ320.CPP KISKEP.CPP KOVETO.CPP KOZOS.CPP LEJATSZO.CPP LEPTET.CPP
	LGRFILE.CPP LOAD.CPP MAIN.CPP MAINMENU.CPP MENUKEP.CPP NEWUJ.CPP
	OPTIONS.CPP PEXTMENU.CPP PIC8.CPP PICLIST.CPP PLAY.CPP
	QOPEN.CPP README.CPP RECORDER.CPP SKIP.CPP SPRITE.CPP
	STATE.CPP SZAKASZ.CPP TELJES.CPP TOPOL.CPP UPGRADE.CPP UTKOZES.CPP
	UTKOZES2.CPP VALASZT2.CPP VEKT2.CPP
	H_DUMMY.CPP
)
list(TRANSFORM ELMA_PSX_CORE PREPEND ${ELMA_ROOT}/src/)

# Each subsystem of the port (src/<part>/<part>.cmake) may add sources to
# ELMA_PSX_EXTRA_SOURCES and name core files it replaces (relative to src/ of
# the repository, e.g. H_DUMMY.CPP) in ELMA_PSX_REPLACED.
set(ELMA_PSX_EXTRA_SOURCES "")
set(ELMA_PSX_REPLACED "")
foreach(part phys gpu sound memcard mem)
	include(${CMAKE_CURRENT_SOURCE_DIR}/src/${part}/${part}.cmake OPTIONAL)
endforeach()
list(TRANSFORM ELMA_PSX_REPLACED PREPEND ${ELMA_ROOT}/src/)
if(ELMA_PSX_REPLACED)
	list(REMOVE_ITEM ELMA_PSX_CORE ${ELMA_PSX_REPLACED})
endif()

# The sources include headers by lower case names (all.h); forward them to
# the upper case files, as the top CMakeLists.txt does.
set(ELMA_PSX_HEADER_DIR ${CMAKE_CURRENT_BINARY_DIR}/lowercase_headers)
file(GLOB ELMA_PSX_HEADERS RELATIVE ${ELMA_ROOT}/src ${ELMA_ROOT}/src/*.H)
foreach(header ${ELMA_PSX_HEADERS})
	string(TOLOWER ${header} lower)
	set(forward "#include \"${ELMA_ROOT}/src/${header}\"\n")
	set(current "")
	if(EXISTS ${ELMA_PSX_HEADER_DIR}/${lower})
		file(READ ${ELMA_PSX_HEADER_DIR}/${lower} current)
	endif()
	if(NOT current STREQUAL forward)
		file(WRITE ${ELMA_PSX_HEADER_DIR}/${lower} "${forward}")
	endif()
endforeach()

file(GLOB ELMA_PSX_LIBM ${CMAKE_CURRENT_SOURCE_DIR}/third_party/musl-libm/src/*.c)

# Everything but the platform layer is built once for both programs:
#   elma     reads the game files from the host through PCdrv (emulator)
#   elma-cd  reads them from the disc (track 2, else track 1)
psn00bsdk_add_library(elma_core OBJECT
	${ELMA_PSX_CORE}
	src/psx_files.cpp
	src/psx_szuro.cpp
	src/psx_file.c
	src/psx_libc.c
	src/cd/cdtrack.c
	src/cd/cdfile.c
	src/cd/iso9660.c
	${ELMA_PSX_LIBM}
	${ELMA_PSX_EXTRA_SOURCES}
)
set_target_properties(elma_core PROPERTIES PSN00BSDK_TARGET_TYPE EXECUTABLE_GPREL)

function(elma_psx_settings target)
	# The libc additions come before the SDK's headers (they include them
	# with #include_next).
	target_include_directories(${target} BEFORE PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src/include)
	target_include_directories(${target} PRIVATE
		${CMAKE_CURRENT_SOURCE_DIR}/src
		${ELMA_ROOT}/src
		${ELMA_ROOT}/desktop
		${ELMA_PSX_HEADER_DIR}
		${CMAKE_CURRENT_SOURCE_DIR}/third_party/musl-libm/src
	)
	target_compile_definitions(${target} PRIVATE ELMA_PSX ELMA_HANDHELD
		$<$<BOOL:${ELMA_PSX_REGISTERED}>:ELMA_REGISTERED>)
	# As in the desktop builds: the code was written for x86 (signed char,
	# wrapping signed integers, reads through pointers of other types), and
	# floating point contraction would change the physics results.
	target_compile_options(${target} PRIVATE
		-fsigned-char -fwrapv -fno-strict-aliasing -ffp-contract=off
		$<$<COMPILE_LANGUAGE:CXX>:-fpermissive -std=gnu++11>
		$<$<COMPILE_LANGUAGE:C>:-std=gnu11>
	)
endfunction()

elma_psx_settings(elma_core)
set_source_files_properties(${ELMA_PSX_CORE} ${ELMA_PSX_LIBM} PROPERTIES COMPILE_OPTIONS "-w")

psn00bsdk_add_executable(elma GPREL src/psx_platform.cpp src/psx_pcdrv.c $<TARGET_OBJECTS:elma_core>)
elma_psx_settings(elma)
target_compile_definitions(elma PRIVATE ELMA_PSX_PCDRV)

psn00bsdk_add_executable(elma-cd GPREL src/psx_platform.cpp $<TARGET_OBJECTS:elma_core>)
elma_psx_settings(elma-cd)
