# Cross build for the Miyoo Mini (Plus) inside the Onion OS toolchain
# container (aemiii91/miyoomini-toolchain), whose sysroot has the SDL 1.2 of
# the device.
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR armv7l)
set(MIYOO_TOOLCHAIN /opt/miyoomini-toolchain)
set(CMAKE_C_COMPILER ${MIYOO_TOOLCHAIN}/bin/arm-linux-gnueabihf-gcc)
set(CMAKE_CXX_COMPILER ${MIYOO_TOOLCHAIN}/bin/arm-linux-gnueabihf-g++)
set(CMAKE_SYSROOT ${MIYOO_TOOLCHAIN}/arm-linux-gnueabihf/libc)
set(CMAKE_CXX_FLAGS_INIT "-marm -mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(ENV{PKG_CONFIG_SYSROOT_DIR} ${CMAKE_SYSROOT})
set(ENV{PKG_CONFIG_LIBDIR} ${CMAKE_SYSROOT}/usr/lib/pkgconfig)
