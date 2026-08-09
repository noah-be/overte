#pragma once

inline bool areOpenXrHandTrackingFunctionsReady(
        bool createLoaded, bool destroyLoaded, bool locateLoaded) {
    return createLoaded && destroyLoaded && locateLoaded;
}

inline bool isOpenXrOptionalFunctionReady(
        bool loadSucceeded, bool pointerIsNonNull) {
    return loadSucceeded && pointerIsNonNull;
}

inline bool areOpenXrXDevFunctionsReady(
        bool createListReady,
        bool enumerateReady,
        bool propertiesReady,
        bool destroyListReady,
        bool createSpaceReady) {
    return createListReady && enumerateReady && propertiesReady &&
        destroyListReady && createSpaceReady;
}

enum class OpenXrHandTrackerPairState {
    None,
    Partial,
    Complete,
};

inline OpenXrHandTrackerPairState openXrHandTrackerPairState(
        bool leftValid, bool rightValid) {
    if (leftValid && rightValid) {
        return OpenXrHandTrackerPairState::Complete;
    }
    if (leftValid || rightValid) {
        return OpenXrHandTrackerPairState::Partial;
    }
    return OpenXrHandTrackerPairState::None;
}
