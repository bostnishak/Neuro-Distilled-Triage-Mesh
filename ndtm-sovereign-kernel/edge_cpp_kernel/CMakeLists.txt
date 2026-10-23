cmake_minimum_required(VERSION 3.20)
project(NDTM_Edge_Cpp_Kernel VERSION 2.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Optimization & Compiler Flags
if(MSVC)
    add_compile_options(/O2 /W4 /permissive- /Zc:__cplusplus /utf-8)
else()
    add_compile_options(-O3 -Wall -Wextra -Wpedantic -pthread)
    if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64")
        add_compile_options(-msse4.2 -mavx2)
    endif()
endif()

include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Core Edge DSP & Shared Memory Library
add_library(ndtm_edge_core STATIC
    src/shm_zero_copy_arena.cpp
    src/radix2_fft_spectrogram.cpp
    src/laplacian_simd_optics.cpp
    src/grpc_telemetry_bridge.cpp
    src/seqlock_epoch_arena.cpp
    src/deadman_lease_watchdog.cpp
)

# Edge Daemon Executable
add_executable(edge_daemon
    src/edge_daemon_main.cpp
)
target_link_libraries(edge_daemon PRIVATE ndtm_edge_core)

# C++ Invariant Test Suite
add_executable(test_cpp_kernel_invariants
    tests/test_cpp_kernel_invariants.cpp
)
target_link_libraries(test_cpp_kernel_invariants PRIVATE ndtm_edge_core)

enable_testing()
add_test(NAME CppKernelInvariants COMMAND test_cpp_kernel_invariants)
