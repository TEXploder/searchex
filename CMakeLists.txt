cmake_minimum_required(VERSION 3.21)
project(searchex LANGUAGES CXX)

find_package(pybind11 CONFIG REQUIRED)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Native extension module name:
pybind11_add_module(searchex_native src/cpp/cpp.cpp)

if(MSVC)
  target_compile_options(searchex_native PRIVATE /EHsc /bigobj /utf-8 /permissive-)
endif()

# Install into the Python package 'searchex' inside the wheel:
install(TARGETS searchex_native
  LIBRARY DESTINATION searchex
  RUNTIME DESTINATION searchex
  ARCHIVE DESTINATION searchex
)
