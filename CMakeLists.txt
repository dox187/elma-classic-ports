cmake_minimum_required(VERSION 3.13)
project(elma_classic LANGUAGES CXX)

option(ELMA_REGISTERED "Build the registered version; needs the registered game data" OFF)
set(ELMA_PLATFORM "desktop" CACHE STRING
    "Target device: desktop, handheld (SDL 2 handhelds such as the RGB30) or miyoomini")
set_property(CACHE ELMA_PLATFORM PROPERTY STRINGS desktop handheld miyoomini)

# The Miyoo Mini only ships SDL 1.2, everything else uses SDL 2.
if(ELMA_PLATFORM STREQUAL "miyoomini")
    set(ELMA_SDL_MODULE sdl)
elseif(ELMA_PLATFORM STREQUAL "desktop" OR ELMA_PLATFORM STREQUAL "handheld")
    set(ELMA_SDL_MODULE sdl2)
else()
    message(FATAL_ERROR "Unknown ELMA_PLATFORM: ${ELMA_PLATFORM}")
endif()

# Handheld systems ship different C++ runtimes; linking it in lets one binary
# run on all of them. The terminal version is only built for desktops.
if(ELMA_PLATFORM STREQUAL "desktop")
    set(ELMA_STATIC_RUNTIME_DEFAULT OFF)
    set(ELMA_BUILD_CLI_DEFAULT ON)
else()
    set(ELMA_STATIC_RUNTIME_DEFAULT ON)
    set(ELMA_BUILD_CLI_DEFAULT OFF)
endif()
option(ELMA_STATIC_RUNTIME "Link the C++ runtime statically" ${ELMA_STATIC_RUNTIME_DEFAULT})
option(ELMA_BUILD_CLI "Build the terminal version (elma-cli)" ${ELMA_BUILD_CLI_DEFAULT})

find_package(PkgConfig REQUIRED)
# On desktops SDL is optional: without it only the silent terminal version is
# built.
if(ELMA_PLATFORM STREQUAL "desktop")
    pkg_check_modules(SDL IMPORTED_TARGET ${ELMA_SDL_MODULE})
else()
    pkg_check_modules(SDL REQUIRED IMPORTED_TARGET ${ELMA_SDL_MODULE})
endif()

set(ELMA_CORE
    ABC8.CPP ADATOK.CPP ANIM.CPP BEALLIT.CPP BESTTIME.CPP
    CUSTOM.CPP DIALOG.CPP DIALOG32.CPP DIGIT.CPP DISPLAY.CPP DOBOZ.CPP
    D_PIC.CPP ECSET.CPP EDITHELP.CPP EDITMENU.CPP EDITPLAY.CPP EDITTOLT.CPP
    EDITTOOL.CPP EDITUJ.CPP ED_CHECK.CPP FOGOCSKA.CPP GOLYKISZ.CPP
    GOLYOK.CPP GOLYUTK.CPP GRAPH.CPP GYURU.CPP H_WAV.CPP JATEKOS.CPP
    KIRAJ320.CPP KISKEP.CPP KOVETO.CPP KOZOS.CPP LEJATSZO.CPP LEPTET.CPP
    LGRFILE.CPP LOAD.CPP MAIN.CPP MAINMENU.CPP MENUKEP.CPP NEWUJ.CPP
    OPTIONS.CPP PEXTMENU.CPP PIC8.CPP PICLIST.CPP PLAY.CPP
    QOPEN.CPP README.CPP RECORDER.CPP SKIP.CPP SPRITE.CPP
    STATE.CPP SZAKASZ.CPP TELJES.CPP TOPOL.CPP UPGRADE.CPP UTKOZES.CPP
    UTKOZES2.CPP VALASZT2.CPP VEKT2.CPP
)
list(TRANSFORM ELMA_CORE PREPEND src/)

# The sources include headers by lowercase names (all.h) while the files are
# upper case (ALL.H). Generate lowercase forwarding headers so the build also
# works on case-sensitive file systems such as Linux. They are only rewritten
# when their content changes, so reconfiguring does not rebuild everything.
set(ELMA_HEADER_DIR ${CMAKE_CURRENT_BINARY_DIR}/lowercase_headers)
file(GLOB ELMA_HEADERS RELATIVE ${CMAKE_CURRENT_SOURCE_DIR}/src ${CMAKE_CURRENT_SOURCE_DIR}/src/*.H)
foreach(header ${ELMA_HEADERS})
    string(TOLOWER ${header} lower)
    set(forward "#include \"${CMAKE_CURRENT_SOURCE_DIR}/src/${header}\"\n")
    set(current "")
    if(EXISTS ${ELMA_HEADER_DIR}/${lower})
        file(READ ${ELMA_HEADER_DIR}/${lower} current)
    endif()
    if(NOT current STREQUAL forward)
        file(WRITE ${ELMA_HEADER_DIR}/${lower} "${forward}")
    endif()
endforeach()

function(elma_target target)
    target_include_directories(${target} PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src ${CMAKE_CURRENT_SOURCE_DIR}/desktop ${ELMA_HEADER_DIR})
    # The code was written for x86, where char is signed, and for compilers
    # that let signed integers wrap around instead of optimizing on their
    # overflow. Floating point contraction (fused multiply-add on ARM) would
    # change the physics results, so replays stay the same on every platform.
    target_compile_options(${target} PRIVATE -fpermissive -fsigned-char -fwrapv -ffp-contract=off)
    if(ELMA_REGISTERED)
        target_compile_definitions(${target} PRIVATE ELMA_REGISTERED)
    endif()
    if(ELMA_STATIC_RUNTIME)
        target_link_libraries(${target} PRIVATE -static-libstdc++ -static-libgcc)
    endif()
    set_target_properties(${target} PROPERTIES CXX_STANDARD 11 CXX_STANDARD_REQUIRED ON)
endfunction()

set(ELMA_SDL_SOUND desktop/F_SDL/SDL_SOUND.CPP desktop/F_SDL/SDL_HHIGH.CPP)

if(SDL_FOUND)
    add_executable(elma ${ELMA_CORE} desktop/F_SDL/SDL_PLATFORM.CPP ${ELMA_SDL_SOUND})
    elma_target(elma)
    target_link_libraries(elma PRIVATE PkgConfig::SDL)
    if(NOT ELMA_PLATFORM STREQUAL "desktop")
        target_compile_definitions(elma PRIVATE ELMA_HANDHELD)
    endif()
    if(ELMA_PLATFORM STREQUAL "miyoomini")
        target_compile_definitions(elma PRIVATE ELMA_MIYOO)
    endif()
else()
    message(STATUS "SDL 2 not found: the windowed version is skipped")
endif()

# The terminal version uses SDL only for the sound; without SDL it is silent.
if(ELMA_BUILD_CLI)
    set(ELMA_CLI_SOURCES
        desktop/F_CLI/CLI_PLATFORM.CPP desktop/F_CLI/CLI_TERM.CPP desktop/F_CLI/CLI_RENDER.CPP)
    if(SDL_FOUND)
        add_executable(elma-cli ${ELMA_CORE} ${ELMA_CLI_SOURCES} ${ELMA_SDL_SOUND})
        target_link_libraries(elma-cli PRIVATE PkgConfig::SDL)
    else()
        add_executable(elma-cli ${ELMA_CORE} ${ELMA_CLI_SOURCES} src/H_DUMMY.CPP)
    endif()
    elma_target(elma-cli)
    target_compile_definitions(elma-cli PRIVATE ELMA_CLI)
endif()
