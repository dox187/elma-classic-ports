# Elasto Mania PlayStation port: CMake build (PSn00bSDK)
#
# Normally driven through the Makefile in this directory, which passes the
# toolchain file and tool locations. Targets:
#   hello       PS-EXE smoke test (hello/main.c)
#   hello-disc  track-1-only CD image of hello (hello.bin / hello.cue)
# The game target lives in elma.cmake (included at the end if present).

cmake_minimum_required(VERSION 3.21)

project(
	elma-psx
	LANGUAGES C CXX ASM
	VERSION   0.1.0
	DESCRIPTION "Elasto Mania PlayStation port"
)

# Optional Sony license data for real hardware, never committed. Pass
# -DPSX_LICENSE_FILE=/path/to/license.dat (Makefile: LICENSE_FILE=...).
set(PSX_LICENSE_FILE "" CACHE FILEPATH "Optional license data file for disc images")
if(PSX_LICENSE_FILE)
	set(PSX_LICENSE_TAG "<license file=\"${PSX_LICENSE_FILE}\" />")
else()
	set(PSX_LICENSE_TAG "")
endif()

psn00bsdk_add_executable(hello GPREL hello/main.c)

psn00bsdk_add_cd_image(
	hello-disc
	hello
	cmake/hello-iso.xml
	DEPENDS hello cmake/system.cnf
)

# Disc test: mounts the second data track and verifies the files on it.
# The disc itself is built by test/cd_test.py (make cd-test / cdtest-disc).
psn00bsdk_add_executable(
	cdtest GPREL
	cdtest/main.c
	src/cd/cdtrack.c
	src/cd/cdfile.c
	src/cd/iso9660.c
	src/psx_file.c
)

include(${CMAKE_CURRENT_SOURCE_DIR}/elma.cmake OPTIONAL)
