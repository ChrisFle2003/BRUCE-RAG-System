set(BRUCE_CPP_SOURCES
    bruce_core.cpp
    state_to_hierarchy.cpp
    hierarchical_guard.cpp
    routing_table.cpp
    ipc_client.cpp
)

add_executable(bruce_core ${BRUCE_CPP_SOURCES})

target_include_directories(bruce_core PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_include_directories(bruce_core PRIVATE ${PostgreSQL_INCLUDE_DIRS})

# libpq + threads are enough for the Sprint 1 scaffold.
target_link_libraries(bruce_core PRIVATE ${PostgreSQL_LIBRARIES} Threads::Threads)
