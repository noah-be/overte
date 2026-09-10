add_library(discord-rpc::discord-rpc INTERFACE IMPORTED)
set_target_properties(
    discord-rpc::discord-rpc
    PROPERTIES
        INTERFACE_INCLUDE_DIRECTORIES "${CMAKE_CURRENT_LIST_DIR}"
)
set(discord-rpc_FOUND TRUE)
