#pragma once

inline bool areOpenXrHandTrackingFunctionsReady(
        bool createLoaded, bool destroyLoaded, bool locateLoaded) {
    return createLoaded && destroyLoaded && locateLoaded;
}

inline bool isOpenXrOptionalFunctionReady(
        bool loadSucceeded, bool pointerIsNonNull) {
    return loadSucceeded && pointerIsNonNull;
}

inline bool isOpenXrPathReady(
        bool conversionSucceeded, bool pathIsNonNull) {
    return conversionSucceeded && pathIsNonNull;
}

inline bool areOpenXrRequiredHandPathsReady(
        bool leftConversionSucceeded,
        bool leftPathIsNonNull,
        bool rightConversionSucceeded,
        bool rightPathIsNonNull) {
    return isOpenXrPathReady(
               leftConversionSucceeded, leftPathIsNonNull) &&
        isOpenXrPathReady(
               rightConversionSucceeded, rightPathIsNonNull);
}

inline bool areOpenXrDebugMessengerFunctionsReady(
        bool createReady, bool destroyReady) {
    return createReady && destroyReady;
}

inline bool areOpenXrRefreshRateFunctionsReady(
        bool enumerateReady, bool getReady, bool requestReady) {
    return enumerateReady && getReady && requestReady;
}

inline bool areOpenXrFoveationFunctionsReady(
        bool createReady, bool destroyReady, bool updateReady) {
    return createReady && destroyReady && updateReady;
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

enum class OpenXrBodyTrackingBackend {
    None,
    Mndx,
    Vive,
};

inline OpenXrBodyTrackingBackend selectOpenXrBodyTrackingBackend(
        bool viveExtensionSupported,
        bool viveEnumerationFunctionReady,
        bool mndxCapabilityReady) {
    if (viveExtensionSupported && viveEnumerationFunctionReady) {
        return OpenXrBodyTrackingBackend::Vive;
    }
    return mndxCapabilityReady ? OpenXrBodyTrackingBackend::Mndx
                               : OpenXrBodyTrackingBackend::None;
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
