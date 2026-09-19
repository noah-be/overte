function(pico_bind_qt_host_tools consumer)
    foreach(tool moc rcc uic qmake)
        string(TOUPPER "${tool}" upper)
        if(NOT TARGET Qt5::${tool} OR NOT EXISTS "${PICO_QT_${upper}}")
            message(FATAL_ERROR "Missing bound Pico Qt5 host tool: ${tool}")
        endif()
        set_target_properties(Qt5::${tool} PROPERTIES
            IMPORTED_LOCATION "${PICO_QT_${upper}}"
            IMPORTED_LOCATION_DEBUG "${PICO_QT_${upper}}"
            IMPORTED_LOCATION_RELEASE "${PICO_QT_${upper}}"
            IMPORTED_LOCATION_RELWITHDEBINFO "${PICO_QT_${upper}}"
            MAP_IMPORTED_CONFIG_RELWITHDEBINFO "")
    endforeach()
    set_target_properties(${consumer} PROPERTIES AUTOMOC_EXECUTABLE "${PICO_QT_MOC}"
        AUTORCC_EXECUTABLE "${PICO_QT_RCC}" AUTOUIC_EXECUTABLE "${PICO_QT_UIC}")
endfunction()
