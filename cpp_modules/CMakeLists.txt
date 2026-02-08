cmake_minimum_required(VERSION 3.15)
project(adas_cpp_modules)

# C++17 required
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Optimization flags
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3 -march=native -Wall -Wextra")
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -DNDEBUG")

# Find dependencies
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 REQUIRED)
find_package(OpenCV REQUIRED)

# Include directories
include_directories(${OpenCV_INCLUDE_DIRS})
include_directories(${Python3_INCLUDE_DIRS})

# ============================================
# Module 1: renderer.so
# ============================================
pybind11_add_module(renderer
    renderer/overlay.cpp
    renderer/bindings.cpp
)

target_link_libraries(renderer PRIVATE ${OpenCV_LIBS})
target_compile_options(renderer PRIVATE -mavx2)  # Enable AVX2 SIMD

# Install to parent build/lib directory
install(TARGETS renderer LIBRARY DESTINATION ${CMAKE_SOURCE_DIR}/../build/lib)

# ============================================
# HLS ENCODER MODULE
# ============================================
find_package(PkgConfig REQUIRED)
pkg_check_modules(FFMPEG REQUIRED
    libavcodec
    libavformat
    libavutil
    libswscale
)

pybind11_add_module(hlsenc
    hlsenc/encoder.cpp
    hlsenc/bindings.cpp
)

target_include_directories(hlsenc PRIVATE ${FFMPEG_INCLUDE_DIRS})
target_link_directories(hlsenc PRIVATE ${FFMPEG_LIBRARY_DIRS})
target_link_libraries(hlsenc PRIVATE ${FFMPEG_LIBRARIES})
target_compile_options(hlsenc PRIVATE -O3 -Wall)

install(TARGETS hlsenc LIBRARY DESTINATION ${CMAKE_SOURCE_DIR}/../build/lib)

# ============================================
# VIDEO DECODER MODULE (TODO - Phase 3B)
# ============================================
# Placeholder for videodec.so

# ============================================
# Tests (optional)
# ============================================
# enable_testing()
# add_subdirectory(tests)
