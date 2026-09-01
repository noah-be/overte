set(TARGET_NAME ov-map-connector)
setup_hifi_project(Core Network)
setup_memory_debugger()
setup_thread_debugger()

target_sources(${TARGET_NAME} PRIVATE
    ${CMAKE_SOURCE_DIR}/assignment-client/src/entities/EntityTreeHeadlessViewer.cpp
    ${CMAKE_SOURCE_DIR}/assignment-client/src/entities/EntityTreeHeadlessViewer.h
    ${CMAKE_SOURCE_DIR}/assignment-client/src/octree/OctreeHeadlessViewer.cpp
    ${CMAKE_SOURCE_DIR}/assignment-client/src/octree/OctreeHeadlessViewer.h
)

target_include_directories(${TARGET_NAME} PRIVATE
    ${CMAKE_SOURCE_DIR}/assignment-client/src/entities
    ${CMAKE_SOURCE_DIR}/assignment-client/src/octree
    ${CMAKE_SOURCE_DIR}/libraries/entities/src
    ${CMAKE_BINARY_DIR}/libraries/entities/src
    ${CMAKE_SOURCE_DIR}/libraries/platform/src
)

link_hifi_libraries(
    avatars octree entities networking shared script-engine
    model-serializers hfm animation graphics gpu shaders image
    material-networking model-networking ktx
)
