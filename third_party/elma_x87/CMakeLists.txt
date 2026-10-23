cmake_minimum_required(VERSION 3.13)
project(elma_classic_x87 LANGUAGES CXX)
add_library(elma-classic-x87 STATIC
    elma_x87.cpp
    upstream/bochs/cpu/softfloat3e/extF80_to_f128.cc
    upstream/bochs/cpu/softfloat3e/extF80_to_f64.cc
    upstream/bochs/cpu/softfloat3e/f128_addsub.cc
    upstream/bochs/cpu/softfloat3e/f128_div.cc
    upstream/bochs/cpu/softfloat3e/f128_mul.cc
    upstream/bochs/cpu/softfloat3e/f128_mul_by_extF80.cc
    upstream/bochs/cpu/softfloat3e/f128_round.cc
    upstream/bochs/cpu/softfloat3e/f128_to_extF80.cc
    upstream/bochs/cpu/softfloat3e/f64_to_extF80.cc
    upstream/bochs/cpu/softfloat3e/s_addMagsF128.cc
    upstream/bochs/cpu/softfloat3e/8086-SSE/s_commonNaNToExtF80UI.cc
    upstream/bochs/cpu/softfloat3e/8086-SSE/s_commonNaNToF128UI.cc
    upstream/bochs/cpu/softfloat3e/8086-SSE/s_commonNaNToF64UI.cc
    upstream/bochs/cpu/softfloat3e/s_normRoundPackToF128.cc
    upstream/bochs/cpu/softfloat3e/s_normSubnormalExtF80Sig.cc
    upstream/bochs/cpu/softfloat3e/s_normSubnormalF128Sig.cc
    upstream/bochs/cpu/softfloat3e/s_normSubnormalF64Sig.cc
    upstream/bochs/cpu/softfloat3e/s_packToExtF80.cc
    upstream/bochs/cpu/softfloat3e/8086-SSE/s_propagateNaNExtF80UI.cc
    upstream/bochs/cpu/softfloat3e/8086-SSE/s_propagateNaNF128UI.cc
    upstream/bochs/cpu/softfloat3e/s_roundPackToExtF80.cc
    upstream/bochs/cpu/softfloat3e/s_roundPackToF128.cc
    upstream/bochs/cpu/softfloat3e/s_roundPackToF64.cc
    upstream/bochs/cpu/softfloat3e/s_shiftRightJam128.cc
    upstream/bochs/cpu/softfloat3e/s_shiftRightJam128Extra.cc
    upstream/bochs/cpu/softfloat3e/s_subMagsF128.cc
    upstream/bochs/cpu/fpu/fsincos.cc
    upstream/bochs/cpu/fpu/f128_67.cc
)
target_compile_features(elma-classic-x87 PUBLIC cxx_std_11)
target_include_directories(elma-classic-x87
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/shim
            ${CMAKE_CURRENT_SOURCE_DIR}/upstream/bochs/cpu
            ${CMAKE_CURRENT_SOURCE_DIR}/upstream/bochs/cpu/softfloat3e/include)
target_compile_definitions(elma-classic-x87 PRIVATE
    SOFTFLOAT_FAST_INT64 INLINE_LEVEL=5
    SOFTFLOAT_FAST_DIV32TO16 SOFTFLOAT_FAST_DIV64TO32)
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(elma-classic-x87 PRIVATE
        -fno-fast-math -ffp-contract=off -fsigned-char -fwrapv
        -fno-strict-aliasing -ffunction-sections -fdata-sections)
endif()
option(ELMA_X87_BUILD_TESTS "Build standalone adapter regressions" OFF)
if(ELMA_X87_BUILD_TESTS)
    enable_testing()
    add_executable(elma-x87-endpoint-test tests/endpoint.cpp)
    target_link_libraries(elma-x87-endpoint-test PRIVATE elma-classic-x87)
    add_test(NAME elma-x87-endpoint COMMAND elma-x87-endpoint-test)
endif()
