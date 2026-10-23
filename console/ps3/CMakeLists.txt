cmake_minimum_required(VERSION 3.16)
project(elma_ps3 LANGUAGES C CXX)
set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type")
option(ELMA_REGISTERED "Use registered game data" ON)
option(ELMA_CLASSIC_X87 "Experimental original 1.11a x87 physics profile" OFF)
get_filename_component(ELMA_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
if(ELMA_CLASSIC_X87)
    add_subdirectory("${ELMA_ROOT}/third_party/elma_x87" "elma-x87")
    target_compile_options(elma-classic-x87 PRIVATE -g -O2 -mcpu=cell -mhard-float)
endif()
# Keep exactly the same engine translation units as desktop.
file(READ "${ELMA_ROOT}/CMakeLists.txt" ROOT_CMAKE)
string(REGEX MATCH "set\\(ELMA_CORE[^)]*\\)" CORE_DECL "${ROOT_CMAKE}")
string(REGEX REPLACE "^set\\(ELMA_CORE|\\)$" "" CORE_NAMES "${CORE_DECL}")
separate_arguments(CORE_NAMES UNIX_COMMAND "${CORE_NAMES}")
set(CORE_SOURCES)
foreach(name IN LISTS CORE_NAMES)
    list(APPEND CORE_SOURCES "${ELMA_ROOT}/src/${name}")
endforeach()
file(GLOB HEADERS "${ELMA_ROOT}/src/*.H")
foreach(header IN LISTS HEADERS)
    get_filename_component(name "${header}" NAME)
    string(TOLOWER "${name}" lower)
    set(forward "#include \"${header}\"\n")
    set(current "")
    if(EXISTS "${CMAKE_CURRENT_BINARY_DIR}/headers/${lower}")
        file(READ "${CMAKE_CURRENT_BINARY_DIR}/headers/${lower}" current)
    endif()
    if(NOT current STREQUAL forward)
        file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/headers/${lower}" "${forward}")
    endif()
endforeach()
add_library(hqx STATIC "${ELMA_ROOT}/third_party/hqx/init.c"
    "${ELMA_ROOT}/third_party/hqx/hq2x.c" "${ELMA_ROOT}/third_party/hqx/hq3x.c"
    "${ELMA_ROOT}/third_party/hqx/hq4x.c")
# Match desktop glibc transcendental rounding; only this isolated libm code
# permits FMA contraction. The original physics translation units forbid it.
add_library(elma-math STATIC
    "${ELMA_ROOT}/third_party/elma_libm/s_sin.c"
    "${ELMA_ROOT}/third_party/elma_libm/branred.c"
    "${ELMA_ROOT}/third_party/elma_libm/sincostab.c"
    "${ELMA_ROOT}/third_party/elma_libm/ps3_math.c")
target_include_directories(elma-math PRIVATE "${ELMA_ROOT}/third_party/elma_libm")
target_compile_options(elma-math PRIVATE -g -O2 -fno-fast-math -fno-strict-aliasing
    -ffp-contract=fast -mcpu=cell -mhard-float)
set_source_files_properties("${ELMA_ROOT}/third_party/elma_libm/branred.c"
    PROPERTIES COMPILE_OPTIONS -ffp-contract=off)
add_library(ps3-sdl2 STATIC IMPORTED)
set_target_properties(ps3-sdl2 PROPERTIES IMPORTED_LOCATION "${PS3DEV}/portlibs/ppu/lib/libSDL2.a")
add_executable(elma ${CORE_SOURCES}
    "${ELMA_ROOT}/desktop/F_SDL/SDL_PLATFORM.CPP"
    "${ELMA_ROOT}/desktop/F_SDL/SDL_SETTINGS.CPP"
    "${ELMA_ROOT}/desktop/F_SDL/SDL_SOUND.CPP"
    "${ELMA_ROOT}/desktop/F_SDL/SDL_HHIGH.CPP"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/PS3_CONTROLS.CPP"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/PS3_MEMORY.CPP"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/PS3_PLATFORM.CPP")
set_target_properties(elma PROPERTIES OUTPUT_NAME elma SUFFIX .elf CXX_STANDARD 11 CXX_STANDARD_REQUIRED ON)
file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/VERSION" ELMA_PS3_VERSION LIMIT_COUNT 1)
target_compile_definitions(elma PRIVATE ELMA_PS3_VERSION="${ELMA_PS3_VERSION}" ELMA_PS3 _GLIBCXX11_USE_C99_STDIO)
if(ELMA_REGISTERED)
    target_compile_definitions(elma PRIVATE ELMA_REGISTERED)
endif()
foreach(target elma hqx)
    target_compile_options(${target} PRIVATE -g -mcpu=cell -mhard-float -O2
        -fsigned-char -fwrapv -fno-strict-aliasing -ffp-contract=off -fno-fast-math
        -ffunction-sections -fdata-sections)
endforeach()
target_compile_options(elma PRIVATE -fpermissive)
target_include_directories(elma PRIVATE "${ELMA_ROOT}/src" "${ELMA_ROOT}/desktop"
    "${ELMA_ROOT}/third_party" "${CMAKE_CURRENT_BINARY_DIR}/headers"
    "${CMAKE_CURRENT_SOURCE_DIR}/src" "${ELMA_ROOT}/desktop/F_SDL"
    "${PS3DEV}/portlibs/ppu/include/SDL2" "${PS3DEV}/ppu/include")
target_link_directories(elma PRIVATE "${PS3DEV}/portlibs/ppu/lib" "${PS3DEV}/ppu/lib")
target_link_options(elma PRIVATE -mcpu=cell -Wl,--gc-sections "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/elma.map")
target_link_options(elma PRIVATE -Wl,--wrap=rsxMemalign -Wl,--wrap=rsxMalloc -Wl,--wrap=rsxFree)
target_link_libraries(elma PRIVATE hqx elma-math ps3-sdl2 gcm_sys rsx sysutil io audio rt lv2 m)

# Compare original-engine trajectories against a desktop build of this fixture.
add_executable(physics-trace EXCLUDE_FROM_ALL test/physics_trace.cpp
    "${ELMA_ROOT}/src/LEPTET.CPP" "${ELMA_ROOT}/src/BEALLIT.CPP"
    "${ELMA_ROOT}/src/UTKOZES.CPP" "${ELMA_ROOT}/src/UTKOZES2.CPP"
    "${ELMA_ROOT}/src/SZAKASZ.CPP" "${ELMA_ROOT}/src/VEKT2.CPP")
set_target_properties(physics-trace PROPERTIES SUFFIX .elf CXX_STANDARD 11 CXX_STANDARD_REQUIRED ON)
target_include_directories(physics-trace PRIVATE "${ELMA_ROOT}/src" "${ELMA_ROOT}/desktop"
    "${CMAKE_CURRENT_BINARY_DIR}/headers" "${PS3DEV}/ppu/include")
target_compile_definitions(physics-trace PRIVATE ELMA_PS3)
target_compile_options(physics-trace PRIVATE -mcpu=cell -mhard-float -O2 -fpermissive
    -fsigned-char -fwrapv -fno-strict-aliasing -ffp-contract=off -fno-fast-math
    -ffunction-sections -fdata-sections)
target_link_options(physics-trace PRIVATE -mcpu=cell -Wl,--gc-sections)
target_link_directories(physics-trace PRIVATE "${PS3DEV}/ppu/lib")
target_link_libraries(physics-trace PRIVATE elma-math sysutil io rt lv2 m)

add_executable(endian-test EXCLUDE_FROM_ALL "${ELMA_ROOT}/tests/little_endian.cpp" test/file_shim.cpp)
set_target_properties(endian-test PROPERTIES SUFFIX .elf CXX_STANDARD 11 CXX_STANDARD_REQUIRED ON)
target_include_directories(endian-test PRIVATE "${ELMA_ROOT}/src" "${ELMA_ROOT}/desktop"
    "${CMAKE_CURRENT_BINARY_DIR}/headers" "${PS3DEV}/ppu/include")
target_compile_definitions(endian-test PRIVATE ELMA_PS3)
target_compile_options(endian-test PRIVATE -mcpu=cell -fpermissive -fsigned-char
    -fwrapv -fno-strict-aliasing -ffp-contract=off -fno-fast-math)
target_link_directories(endian-test PRIVATE "${PS3DEV}/ppu/lib")
target_link_libraries(endian-test PRIVATE rt lv2 m)

add_executable(math-parity EXCLUDE_FROM_ALL "${ELMA_ROOT}/tests/math_parity.c")
set_target_properties(math-parity PROPERTIES SUFFIX .elf)
target_compile_options(math-parity PRIVATE -mcpu=cell -O2 -fno-fast-math -ffp-contract=off)
target_link_directories(math-parity PRIVATE "${PS3DEV}/ppu/lib")
target_link_libraries(math-parity PRIVATE elma-math rt lv2 m)

add_executable(files-test EXCLUDE_FROM_ALL test/files_test.cpp "${ELMA_ROOT}/src/KOZOS.CPP")
set_target_properties(files-test PROPERTIES SUFFIX .elf CXX_STANDARD 11)
target_include_directories(files-test PRIVATE "${ELMA_ROOT}/src" "${ELMA_ROOT}/desktop"
    "${CMAKE_CURRENT_BINARY_DIR}/headers" "${PS3DEV}/ppu/include")
target_compile_definitions(files-test PRIVATE ELMA_PS3)
target_compile_options(files-test PRIVATE -mcpu=cell -O2 -fpermissive -fsigned-char
    -fwrapv -fno-strict-aliasing -ffp-contract=off -ffunction-sections -fdata-sections)
target_link_options(files-test PRIVATE -Wl,--gc-sections)
target_link_directories(files-test PRIVATE "${PS3DEV}/ppu/lib")
target_link_libraries(files-test PRIVATE rt lv2 m)

add_executable(sdl-test EXCLUDE_FROM_ALL test/sdl_test.cpp)
set_target_properties(sdl-test PROPERTIES SUFFIX .elf CXX_STANDARD 11)
target_include_directories(sdl-test PRIVATE "${PS3DEV}/ppu/include" "${PS3DEV}/portlibs/ppu/include/SDL2")
target_compile_options(sdl-test PRIVATE -mcpu=cell -O2)
target_link_directories(sdl-test PRIVATE "${PS3DEV}/portlibs/ppu/lib" "${PS3DEV}/ppu/lib")
target_link_libraries(sdl-test PRIVATE ps3-sdl2 gcm_sys rsx sysutil io audio rt lv2 m)

add_executable(lgr-budget-test EXCLUDE_FROM_ALL "${ELMA_ROOT}/tests/lgr_budget.cpp")
set_target_properties(lgr-budget-test PROPERTIES SUFFIX .elf CXX_STANDARD 11)
target_include_directories(lgr-budget-test PRIVATE "${ELMA_ROOT}/src" "${PS3DEV}/ppu/include")
target_compile_definitions(lgr-budget-test PRIVATE ELMA_PS3)
target_compile_options(lgr-budget-test PRIVATE -mcpu=cell -O2 -fsigned-char -fwrapv -fno-strict-aliasing -ffp-contract=off)
target_link_directories(lgr-budget-test PRIVATE "${PS3DEV}/ppu/lib")
target_link_libraries(lgr-budget-test PRIVATE rt lv2 m)

add_executable(sprite-rotation-test EXCLUDE_FROM_ALL "${ELMA_ROOT}/tests/sprite_rotation.cpp"
    "${ELMA_ROOT}/src/DOBOZ.CPP" "${ELMA_ROOT}/src/VEKT2.CPP" "${ELMA_ROOT}/src/KISKEP.CPP")
set_target_properties(sprite-rotation-test PROPERTIES SUFFIX .elf CXX_STANDARD 11)
target_include_directories(sprite-rotation-test PRIVATE "${ELMA_ROOT}/src" "${ELMA_ROOT}/desktop"
    "${CMAKE_CURRENT_BINARY_DIR}/headers" "${PS3DEV}/ppu/include")
target_compile_definitions(sprite-rotation-test PRIVATE ELMA_PS3)
target_compile_options(sprite-rotation-test PRIVATE -mcpu=cell -O2 -fpermissive -fsigned-char
    -fwrapv -fno-strict-aliasing -ffp-contract=off -ffunction-sections -fdata-sections)
target_link_options(sprite-rotation-test PRIVATE -Wl,--gc-sections)
target_link_directories(sprite-rotation-test PRIVATE "${PS3DEV}/ppu/lib")
target_link_libraries(sprite-rotation-test PRIVATE elma-math rt lv2 m)

add_executable(atomic-file-test EXCLUDE_FROM_ALL "${ELMA_ROOT}/tests/atomic_file.cpp")
set_target_properties(atomic-file-test PROPERTIES SUFFIX .elf CXX_STANDARD 11)
target_include_directories(atomic-file-test PRIVATE "${ELMA_ROOT}/src" "${PS3DEV}/ppu/include")
target_compile_definitions(atomic-file-test PRIVATE ELMA_PS3)
target_compile_options(atomic-file-test PRIVATE -mcpu=cell -O2 -fsigned-char -fwrapv -fno-strict-aliasing -ffp-contract=off)
target_link_directories(atomic-file-test PRIVATE "${PS3DEV}/ppu/lib")
target_link_libraries(atomic-file-test PRIVATE rt lv2 m)

get_target_property(ELMA_TRACE_SOURCES physics-trace SOURCES)
list(REMOVE_ITEM ELMA_TRACE_SOURCES test/physics_trace.cpp)
add_executable(physics-multiplayer EXCLUDE_FROM_ALL test/physics_multiplayer.cpp
    ${ELMA_TRACE_SOURCES} "${ELMA_ROOT}/src/FOGOCSKA.CPP")
set_target_properties(physics-multiplayer PROPERTIES SUFFIX .elf CXX_STANDARD 11 CXX_STANDARD_REQUIRED ON)
foreach(property INCLUDE_DIRECTORIES COMPILE_OPTIONS COMPILE_DEFINITIONS LINK_OPTIONS LINK_DIRECTORIES LINK_LIBRARIES)
    get_target_property(ELMA_TRACE_PROPERTY physics-trace ${property})
    set_property(TARGET physics-multiplayer PROPERTY ${property} "${ELMA_TRACE_PROPERTY}")
endforeach()

add_executable(state-file-test EXCLUDE_FROM_ALL "${ELMA_ROOT}/tests/state_file.cpp" "${ELMA_ROOT}/src/STATE.CPP")
set_target_properties(state-file-test PROPERTIES SUFFIX .elf CXX_STANDARD 11)
target_include_directories(state-file-test PRIVATE "${ELMA_ROOT}/src" "${ELMA_ROOT}/desktop"
    "${CMAKE_CURRENT_BINARY_DIR}/headers" "${PS3DEV}/ppu/include")
target_compile_definitions(state-file-test PRIVATE ELMA_PS3 ELMA_PS3_NATIVE_TEST)
target_compile_options(state-file-test PRIVATE -mcpu=cell -O2 -fpermissive -fsigned-char
    -fwrapv -fno-strict-aliasing -ffp-contract=off -ffunction-sections -fdata-sections)
target_link_options(state-file-test PRIVATE -Wl,--gc-sections)
target_link_directories(state-file-test PRIVATE "${PS3DEV}/ppu/lib")
target_link_libraries(state-file-test PRIVATE rt lv2 m)

add_executable(replay-file-test EXCLUDE_FROM_ALL "${ELMA_ROOT}/tests/replay_file.cpp"
    "${ELMA_ROOT}/src/RECORDER.CPP" "${ELMA_ROOT}/src/VEKT2.CPP")
set_target_properties(replay-file-test PROPERTIES SUFFIX .elf CXX_STANDARD 11)
target_include_directories(replay-file-test PRIVATE "${ELMA_ROOT}/src" "${ELMA_ROOT}/desktop"
    "${CMAKE_CURRENT_BINARY_DIR}/headers" "${PS3DEV}/ppu/include")
target_compile_definitions(replay-file-test PRIVATE ELMA_PS3 ELMA_PS3_NATIVE_TEST)
target_compile_options(replay-file-test PRIVATE -mcpu=cell -O2 -fpermissive -fsigned-char
    -fwrapv -fno-strict-aliasing -ffp-contract=off -ffunction-sections -fdata-sections)
target_link_options(replay-file-test PRIVATE -Wl,--gc-sections)
target_link_directories(replay-file-test PRIVATE "${PS3DEV}/ppu/lib")
target_link_libraries(replay-file-test PRIVATE rt lv2 m)

add_executable(level-file-test EXCLUDE_FROM_ALL "${ELMA_ROOT}/tests/level_file.cpp"
    "${ELMA_ROOT}/src/TOPOL.CPP" "${ELMA_ROOT}/src/GYURU.CPP" "${ELMA_ROOT}/src/VEKT2.CPP")
add_executable(sprite-stream-test EXCLUDE_FROM_ALL "${ELMA_ROOT}/tests/sprite_stream.cpp")
set_target_properties(sprite-stream-test PROPERTIES SUFFIX .elf CXX_STANDARD 11)
target_include_directories(sprite-stream-test PRIVATE "${ELMA_ROOT}/src")
target_compile_definitions(sprite-stream-test PRIVATE ELMA_PS3)
target_compile_options(sprite-stream-test PRIVATE -mcpu=cell -O2 -fsigned-char -fwrapv -fno-strict-aliasing -ffp-contract=off)
target_link_directories(sprite-stream-test PRIVATE "${PS3DEV}/ppu/lib")
target_link_libraries(sprite-stream-test PRIVATE rt lv2 m)

add_executable(screenshot-file-test EXCLUDE_FROM_ALL "${ELMA_ROOT}/tests/screenshot_file.cpp"
    "${ELMA_ROOT}/src/PIC8.CPP")
foreach(native_file_test level-file-test screenshot-file-test)
    set_target_properties(${native_file_test} PROPERTIES SUFFIX .elf CXX_STANDARD 11)
    foreach(property INCLUDE_DIRECTORIES COMPILE_OPTIONS COMPILE_DEFINITIONS LINK_OPTIONS LINK_DIRECTORIES LINK_LIBRARIES)
        get_target_property(native_file_property replay-file-test ${property})
        set_property(TARGET ${native_file_test} PROPERTY ${property} "${native_file_property}")
    endforeach()
endforeach()

# Decode canonical little-endian original Windows motor snapshots on native PPU.
add_executable(windows-ppu-compare EXCLUDE_FROM_ALL test/windows_ppu_compare.cpp ${ELMA_TRACE_SOURCES})
set_target_properties(windows-ppu-compare PROPERTIES SUFFIX .elf CXX_STANDARD 11 CXX_STANDARD_REQUIRED ON)
foreach(property INCLUDE_DIRECTORIES COMPILE_OPTIONS COMPILE_DEFINITIONS LINK_OPTIONS LINK_DIRECTORIES LINK_LIBRARIES)
    get_target_property(ELMA_TRACE_PROPERTY physics-trace ${property})
    set_property(TARGET windows-ppu-compare PROPERTY ${property} "${ELMA_TRACE_PROPERTY}")
endforeach()

# Scope the profile to shared engine/vector callers, never global libm wrapping.
# Include every fixture that compiles VEKT2 so each target is internally coherent.
if(ELMA_CLASSIC_X87)
    foreach(target elma physics-trace physics-multiplayer windows-ppu-compare
                   sprite-rotation-test replay-file-test level-file-test)
        target_compile_definitions(${target} PRIVATE ELMA_CLASSIC_X87)
        target_link_libraries(${target} PRIVATE elma-classic-x87)
    endforeach()
endif()
