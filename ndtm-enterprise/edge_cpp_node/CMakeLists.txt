cmake_minimum_required(VERSION 3.20)
project(ndtm_edge_cpp_node VERSION 2.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Aggressive compiler optimization for zero-latency edge signal processing
if(MSVC)
    add_compile_options(/O2 /W4 /std:c++20 /permissive-)
else()
    add_compile_options(-O3 -march=native -Wall -Wextra -Wpedantic -pthread)
endif()

find_package(Threads REQUIRED)

include_directories(
    ${PROJECT_SOURCE_DIR}/include
)

set(SOURCES
    src/acoustic_fft_analyzer.cpp
    src/onnx_edge_runner.cpp
    src/grpc_edge_client.cpp
    src/main_edge_node.cpp
)

add_executable(edge_cpp_node ${SOURCES})

target_link_libraries(edge_cpp_node
    PRIVATE
        Threads::Threads
)

# Installation target
install(TARGETS edge_cpp_node DESTINATION bin)
