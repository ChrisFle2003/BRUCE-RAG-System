cmake_minimum_required(VERSION 3.16)
project(BRUCE_RAG CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3 -march=native -g")

# Dependencies
find_package(PostgreSQL REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(Threads REQUIRED)

add_subdirectory(src/cpp)
