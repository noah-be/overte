//
// Overte OpenXR Plugin
//
// Copyright 2024 Lubosz Sarnecki
// Copyright 2024 Overte e.V.
//
// SPDX-License-Identifier: Apache-2.0
//

#include "OpenXrContext.h"
#include "OpenXrDebugPolicy.h"
#include "OpenXrEventPolicy.h"
#include "OpenXrExtensionPolicy.h"
#include "OpenXrGraphicsPolicy.h"
#include "OpenXrSpacePolicy.h"
#include <QLoggingCategory>
#include <QString>
#include <QStringList>
#include <QGuiApplication>

#if defined(Q_OS_LINUX) && !defined(Q_OS_ANDROID)
#include <QOpenGLContext>
#include <QtPlatformHeaders/QGLXNativeContext>
#endif

#if defined(HAVE_VULKAN)
#include <QMessageBox>
#endif

#include <cmath>
#include <sstream>
#include <vector>

Q_DECLARE_LOGGING_CATEGORY(xr_context_cat)
Q_LOGGING_CATEGORY(xr_context_cat, "openxr.context")

#if defined(Q_OS_ANDROID)
extern "C" JavaVM* overtePicoOpenXRJavaVm();
extern "C" jobject overtePicoOpenXRActivity();
#endif

// Checks XrResult, returns false on errors and logs the error as qCritical.
bool xrCheck(XrInstance instance, XrResult result, const char* message) {
    if (XR_SUCCEEDED(result))
        return true;

    char errorName[XR_MAX_RESULT_STRING_SIZE];
    if (instance != XR_NULL_HANDLE) {
        xrResultToString(instance, result, errorName);
    } else {
        sprintf(errorName, "%d", result);
    }

    qCCritical(xr_context_cat, "%s: %s", errorName, message);

    return false;
}

XRAPI_ATTR static XrBool32 XRAPI_CALL debugMessageCallback(
    XrDebugUtilsMessageSeverityFlagsEXT severity,
    XrDebugUtilsMessageTypeFlagsEXT type,
    const XrDebugUtilsMessengerCallbackDataEXT* data,
    void*
) {
    auto level = openXrDebugLogLevel(
        severity,
        XR_DEBUG_UTILS_MESSAGE_SEVERITY_VERBOSE_BIT_EXT,
        XR_DEBUG_UTILS_MESSAGE_SEVERITY_INFO_BIT_EXT,
        XR_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT,
        XR_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT);
    if (level == OpenXrDebugLogLevel::Debug) {
        qCDebug(xr_context_cat, "%s: %s", data->functionName, data->message);
    } else if (level == OpenXrDebugLogLevel::Info) {
        qCInfo(xr_context_cat, "%s: %s", data->functionName, data->message);
    } else if (level == OpenXrDebugLogLevel::Warning) {
        qCWarning(xr_context_cat, "%s: %s", data->functionName, data->message);
    } else {
        qCCritical(xr_context_cat, "%s: %s", data->functionName, data->message);
    }

    return XR_FALSE;
}

// Extension functions must be loaded with xrGetInstanceProcAddr
static PFN_xrGetOpenGLGraphicsRequirementsKHR pfnGetOpenGLGraphicsRequirementsKHR = nullptr;

static bool loadXrFunction(XrInstance instance, const char* name, PFN_xrVoidFunction* out) {
    auto result = xrGetInstanceProcAddr(instance, name, out);

    if (result != XR_SUCCESS) {
        qCCritical(xr_context_cat) << "Failed to load OpenXR function '" << name << "'";
        return false;
    }

    return true;
}

OpenXrContext::OpenXrContext() {
#if defined(HAVE_VULKAN)
    _isSupported = false;
    qCCritical(xr_context_cat, "OpenXR is not supported on the Vulkan backend yet.");
    QMessageBox::critical(nullptr, "OpenXR", "OpenXR is not supported on the Vulkan backend yet.");
#else
    _isSupported = initPreGraphics();
    if (!_isSupported) {
        qCWarning(xr_context_cat, "OpenXR is not supported.");
    }
#endif
}

OpenXrContext::~OpenXrContext() {
    if (_instance == XR_NULL_HANDLE) {
        return;
    }
    if (_debugMessenger != XR_NULL_HANDLE && xrDestroyDebugUtilsMessengerEXT) {
        xrCheck(
            _instance,
            xrDestroyDebugUtilsMessengerEXT(_debugMessenger),
            "Failed to destroy OpenXR debug messenger");
    }
    _debugMessenger = XR_NULL_HANDLE;
    XrResult res = xrDestroyInstance(_instance);
    if (res != XR_SUCCESS) {
        qCCritical(xr_context_cat, "Failed to destroy OpenXR instance");
    }
    _instance = XR_NULL_HANDLE;
    qCDebug(xr_context_cat, "Destroyed instance.");
}

bool OpenXrContext::initInstance() {
#if defined(HAVE_VULKAN)
    // VKTODO
    return false;
#else
    uint32_t extensionCapacity = 0;
    XrResult result = xrEnumerateInstanceExtensionProperties(
        nullptr, 0, &extensionCapacity, nullptr);

    // Since this is the first OpenXR call we do, check here if RUNTIME_UNAVAILABLE is returned.
    if (result == XR_ERROR_RUNTIME_UNAVAILABLE) {
        qCCritical(xr_context_cat, "XR_ERROR_RUNTIME_UNAVAILABLE: Is XR_RUNTIME_JSON set correctly?");
        return false;
    }

    if (!xrCheck(XR_NULL_HANDLE, result, "Failed to enumerate number of extensions."))
        return false;

    std::vector<XrExtensionProperties> properties;
    for (uint32_t i = 0; i < extensionCapacity; i++) {
        XrExtensionProperties props = { .type = XR_TYPE_EXTENSION_PROPERTIES };
        properties.push_back(props);
    }

    uint32_t returnedExtensionCount = 0;
    if (extensionCapacity > 0) {
        result = xrEnumerateInstanceExtensionProperties(
            nullptr, extensionCapacity, &returnedExtensionCount,
            properties.data());
    }
    if (extensionCapacity > 0 &&
            !xrCheck(XR_NULL_HANDLE, result, "Failed to enumerate extensions."))
        return false;
    if (!isOpenXrExtensionEnumerationCountWithinCapacity(
            extensionCapacity, returnedExtensionCount)) {
        qCCritical(xr_context_cat,
                   "Runtime returned inconsistent extension count: %u of %u",
                   returnedExtensionCount, extensionCapacity);
        return false;
    }
    properties.resize(returnedExtensionCount);

    bool openglSupported = false;
    bool userPresenceSupported = false;
    bool odysseyControllerSupported = false;
    bool handTrackingSupported = false;
    bool palmPoseSupported = false;
    bool BD_controllerInteractionSupported = false;
    bool MNDX_xdevSpaceSupported = false;
    bool HTCX_viveTrackerInteractionSupported = false;
    bool MNDX_eglEnableSupported = false;
    bool EXT_debugUtilsSupported = false;
#if defined(Q_OS_ANDROID)
    bool androidCreateInstanceSupported = false;
    bool displayRefreshRateSupported = false;
    bool swapchainUpdateStateSupported = false;
    bool foveationSupported = false;
    bool foveationConfigurationSupported = false;
#endif

    qCInfo(xr_context_cat, "Runtime supports %zu extensions:", properties.size());
    for (const auto& property : properties) {
        qCInfo(xr_context_cat, "%s v%d", property.extensionName, property.extensionVersion);
        if (strcmp(XR_KHR_OPENGL_ENABLE_EXTENSION_NAME, property.extensionName) == 0) {
            openglSupported = true;
#if defined(Q_OS_ANDROID)
        } else if (strcmp(XR_KHR_ANDROID_CREATE_INSTANCE_EXTENSION_NAME, property.extensionName) == 0) {
            androidCreateInstanceSupported = true;
        } else if (strcmp(XR_FB_DISPLAY_REFRESH_RATE_EXTENSION_NAME, property.extensionName) == 0) {
            displayRefreshRateSupported = true;
        } else if (strcmp(XR_FB_SWAPCHAIN_UPDATE_STATE_EXTENSION_NAME, property.extensionName) == 0) {
            swapchainUpdateStateSupported = true;
        } else if (strcmp(XR_FB_FOVEATION_EXTENSION_NAME, property.extensionName) == 0) {
            foveationSupported = true;
        } else if (strcmp(XR_FB_FOVEATION_CONFIGURATION_EXTENSION_NAME, property.extensionName) == 0) {
            foveationConfigurationSupported = true;
#endif
        } else if (strcmp(XR_EXT_USER_PRESENCE_EXTENSION_NAME, property.extensionName) == 0) {
            userPresenceSupported = true;
        } else if (strcmp(XR_EXT_SAMSUNG_ODYSSEY_CONTROLLER_EXTENSION_NAME, property.extensionName) == 0) {
            odysseyControllerSupported = true;
        } else if (strcmp(XR_EXT_HAND_TRACKING_EXTENSION_NAME, property.extensionName) == 0) {
            handTrackingSupported = true;
        } else if (strcmp(XR_MNDX_XDEV_SPACE_EXTENSION_NAME, property.extensionName) == 0) {
            MNDX_xdevSpaceSupported = true;
        } else if (strcmp(XR_HTCX_VIVE_TRACKER_INTERACTION_EXTENSION_NAME, property.extensionName) == 0) {
            HTCX_viveTrackerInteractionSupported = true;
        } else if (strcmp(XR_EXT_PALM_POSE_EXTENSION_NAME, property.extensionName) == 0) {
            palmPoseSupported = true;
        } else if (strcmp(XR_BD_CONTROLLER_INTERACTION_EXTENSION_NAME, property.extensionName) == 0) {
            BD_controllerInteractionSupported = true;
#if defined(XR_USE_PLATFORM_EGL)
        } else if (strcmp(XR_MNDX_EGL_ENABLE_EXTENSION_NAME, property.extensionName) == 0) {
            MNDX_eglEnableSupported = true;
#endif
        } else if (strcmp(XR_EXT_DEBUG_UTILS_EXTENSION_NAME, property.extensionName) == 0) {
            EXT_debugUtilsSupported = true;
        }
    }

    if (!openglSupported) {
        qCCritical(xr_context_cat, "Runtime does not support OpenGL!");
        return false;
    }

    std::vector<const char*> enabled = {XR_KHR_OPENGL_ENABLE_EXTENSION_NAME};

#if defined(Q_OS_ANDROID)
    if (!androidCreateInstanceSupported) {
        qCCritical(xr_context_cat, "Runtime does not support XR_KHR_android_create_instance!");
        return false;
    }
    enabled.push_back(XR_KHR_ANDROID_CREATE_INSTANCE_EXTENSION_NAME);

    if (displayRefreshRateSupported) {
        enabled.push_back(XR_FB_DISPLAY_REFRESH_RATE_EXTENSION_NAME);
        _displayRefreshRateSupported = true;
    }

    if (swapchainUpdateStateSupported && foveationSupported && foveationConfigurationSupported) {
        enabled.push_back(XR_FB_SWAPCHAIN_UPDATE_STATE_EXTENSION_NAME);
        enabled.push_back(XR_FB_FOVEATION_EXTENSION_NAME);
        enabled.push_back(XR_FB_FOVEATION_CONFIGURATION_EXTENSION_NAME);
        _foveationSupported = true;
    }
#endif

    if (userPresenceSupported) {
        enabled.push_back(XR_EXT_USER_PRESENCE_EXTENSION_NAME);
        _userPresenceAvailable = true;
    }

    if (odysseyControllerSupported) {
        enabled.push_back(XR_EXT_SAMSUNG_ODYSSEY_CONTROLLER_EXTENSION_NAME);
    }

    if (handTrackingSupported) {
        enabled.push_back(XR_EXT_HAND_TRACKING_EXTENSION_NAME);
        _handTrackingSupported = true;
    }

    if (MNDX_xdevSpaceSupported) {
        enabled.push_back(XR_MNDX_XDEV_SPACE_EXTENSION_NAME);
        _MNDX_xdevSpaceSupported = true;
    }

    if (HTCX_viveTrackerInteractionSupported) {
        enabled.push_back(XR_HTCX_VIVE_TRACKER_INTERACTION_EXTENSION_NAME);
        _HTCX_viveTrackerInteractionSupported = true;
    }

    if (palmPoseSupported) {
        enabled.push_back(XR_EXT_PALM_POSE_EXTENSION_NAME);
        _palmPoseSupported = true;
    }

    if (BD_controllerInteractionSupported) {
        enabled.push_back(XR_BD_CONTROLLER_INTERACTION_EXTENSION_NAME);
        _BD_controllerInteractionSupported = true;
    }

#if defined(XR_USE_PLATFORM_EGL)
    if (MNDX_eglEnableSupported) {
        enabled.push_back(XR_MNDX_EGL_ENABLE_EXTENSION_NAME);
        _MNDX_eglEnableSupported = true;
    }
#endif

    if (EXT_debugUtilsSupported) {
        enabled.push_back(XR_EXT_DEBUG_UTILS_EXTENSION_NAME);
        _EXT_debugUtilsSupported = true;
    }

    XrInstanceCreateInfo info = {
        .type = XR_TYPE_INSTANCE_CREATE_INFO,
        .applicationInfo = {
            .applicationName = "Overte",
            .applicationVersion = 1,
            .engineName = "Overte",
            .engineVersion = 0,
            .apiVersion = XR_API_VERSION_1_0,
        },
        .enabledExtensionCount = (uint32_t)enabled.size(),
        .enabledExtensionNames = enabled.data(),
    };

#if defined(Q_OS_ANDROID)
    XrInstanceCreateInfoAndroidKHR androidInfo {
        XR_TYPE_INSTANCE_CREATE_INFO_ANDROID_KHR,
        nullptr,
        overtePicoOpenXRJavaVm(),
        overtePicoOpenXRActivity()
    };
    if (!androidInfo.applicationVM || !androidInfo.applicationActivity) {
        qCCritical(xr_context_cat, "Android OpenXR loader context is unavailable.");
        return false;
    }
    info.next = &androidInfo;
#endif

    result = xrCreateInstance(&info, &_instance);

    if (result == XR_ERROR_RUNTIME_FAILURE) {
        qCCritical(xr_context_cat, "XR_ERROR_RUNTIME_FAILURE: Is the OpenXR runtime up and running?");
        return false;
    }

    if (!xrCheck(XR_NULL_HANDLE, result, "Failed to create OpenXR instance."))
        return false;

#if defined(Q_OS_ANDROID)
    const char* graphicsRequirementsFunction = "xrGetOpenGLESGraphicsRequirementsKHR";
#else
    const char* graphicsRequirementsFunction = "xrGetOpenGLGraphicsRequirementsKHR";
#endif
    if (!loadXrFunction(_instance, graphicsRequirementsFunction, (PFN_xrVoidFunction*)&pfnGetOpenGLGraphicsRequirementsKHR)) {
        qCCritical(xr_context_cat) << "Failed to get OpenGL graphics requirements function!";
        return false;
    }

#if defined(Q_OS_ANDROID)
    if (_foveationSupported) {
        const bool createLoaded = loadXrFunction(
            _instance, "xrCreateFoveationProfileFB",
            (PFN_xrVoidFunction*)&xrCreateFoveationProfileFB);
        const bool destroyLoaded = loadXrFunction(
            _instance, "xrDestroyFoveationProfileFB",
            (PFN_xrVoidFunction*)&xrDestroyFoveationProfileFB);
        const bool updateLoaded = loadXrFunction(
            _instance, "xrUpdateSwapchainFB",
            (PFN_xrVoidFunction*)&xrUpdateSwapchainFB);
        _foveationSupported = areOpenXrFoveationFunctionsReady(
            isOpenXrOptionalFunctionReady(
                createLoaded, xrCreateFoveationProfileFB != nullptr),
            isOpenXrOptionalFunctionReady(
                destroyLoaded, xrDestroyFoveationProfileFB != nullptr),
            isOpenXrOptionalFunctionReady(
                updateLoaded, xrUpdateSwapchainFB != nullptr));
        if (!_foveationSupported) {
            xrCreateFoveationProfileFB = nullptr;
            xrDestroyFoveationProfileFB = nullptr;
            xrUpdateSwapchainFB = nullptr;
            qCWarning(xr_context_cat) << "OpenXR foveation API is incomplete; disabling foveation.";
        }
        qCInfo(xr_context_cat) << "PICO_FOVEATION_SUPPORTED" << _foveationSupported;
    }
#endif

    const bool leftHandPathConverted = xrCheck(
        _instance,
        xrStringToPath(_instance, "/user/hand/left", &_handPaths[0]),
        "Failed to create left-hand OpenXR path");
    const bool rightHandPathConverted = xrCheck(
        _instance,
        xrStringToPath(_instance, "/user/hand/right", &_handPaths[1]),
        "Failed to create right-hand OpenXR path");
    if (!areOpenXrRequiredHandPathsReady(
            leftHandPathConverted, _handPaths[0] != XR_NULL_PATH,
            rightHandPathConverted, _handPaths[1] != XR_NULL_PATH)) {
        _handPaths[0] = XR_NULL_PATH;
        _handPaths[1] = XR_NULL_PATH;
        qCCritical(xr_context_cat,
                   "Required OpenXR hand paths are unavailable");
        return false;
    }

    const bool viveControllerPathConverted = xrCheck(
        _instance,
        xrStringToPath(
            _instance, "/interaction_profiles/htc/vive_controller",
            &_viveControllerPath),
        "Failed to create optional Vive controller path");
    if (!isOpenXrPathReady(
            viveControllerPathConverted,
            _viveControllerPath != XR_NULL_PATH)) {
        _viveControllerPath = XR_NULL_PATH;
    }

    return true;
#endif
}

bool OpenXrContext::initSystem() {
    XrSystemGetInfo info = {
        .type = XR_TYPE_SYSTEM_GET_INFO,
        .formFactor = XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY,
    };

    XrResult result = xrGetSystem(_instance, &info, &_systemId);
    if (!xrCheck(_instance, result, "Failed to get system for HMD form factor."))
        return false;

    XrSystemProperties props = {
        .type = XR_TYPE_SYSTEM_PROPERTIES,
        .next = nullptr,
    };

    XrSystemHandTrackingPropertiesEXT handTrackingProps = {
        .type = XR_TYPE_SYSTEM_HAND_TRACKING_PROPERTIES_EXT,
        .next = props.next,
    };

    if (_handTrackingSupported) {
        props.next = &handTrackingProps;
    }

    XrSystemXDevSpacePropertiesMNDX xdevProps = {
        .type =XR_TYPE_SYSTEM_XDEV_SPACE_PROPERTIES_MNDX,
        .next = props.next,
    };

    if (_MNDX_xdevSpaceSupported) {
        props.next = &xdevProps;
    }

    result = xrGetSystemProperties(_instance, _systemId, &props);
    if (!xrCheck(_instance, result, "Failed to get System properties"))
        return false;

    _systemName = QString::fromUtf8(props.systemName);

    qCInfo(xr_context_cat, "System name         : %s", props.systemName);
    qCInfo(xr_context_cat, "Max layers          : %d", props.graphicsProperties.maxLayerCount);
    qCInfo(xr_context_cat, "Max swapchain size  : %dx%d", props.graphicsProperties.maxSwapchainImageHeight,
           props.graphicsProperties.maxSwapchainImageWidth);
    qCInfo(xr_context_cat, "Orientation Tracking: %d", props.trackingProperties.orientationTracking);
    qCInfo(xr_context_cat, "Position Tracking   : %d", props.trackingProperties.positionTracking);

    if (_EXT_debugUtilsSupported) {
        const bool createFunctionLoaded = loadXrFunction(
            _instance,
            "xrCreateDebugUtilsMessengerEXT",
            reinterpret_cast<PFN_xrVoidFunction*>(&xrCreateDebugUtilsMessengerEXT)
        );
        const bool destroyFunctionLoaded = loadXrFunction(
            _instance,
            "xrDestroyDebugUtilsMessengerEXT",
            reinterpret_cast<PFN_xrVoidFunction*>(&xrDestroyDebugUtilsMessengerEXT)
        );

        XrDebugUtilsMessengerCreateInfoEXT createInfo = {
            .type = XR_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT,
            .next = nullptr,
            .messageSeverities = XR_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT | XR_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT,
            .messageTypes = XR_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT,
            .userCallback = debugMessageCallback,
            .userData = nullptr,
        };

        const bool functionsReady = areOpenXrDebugMessengerFunctionsReady(
            isOpenXrOptionalFunctionReady(
                createFunctionLoaded,
                xrCreateDebugUtilsMessengerEXT != nullptr),
            isOpenXrOptionalFunctionReady(
                destroyFunctionLoaded,
                xrDestroyDebugUtilsMessengerEXT != nullptr));
        const bool messengerCreated = functionsReady && xrCheck(
            _instance,
            xrCreateDebugUtilsMessengerEXT(_instance, &createInfo, &_debugMessenger),
            "Failed to create OpenXR debug messenger");
        if (!messengerCreated || _debugMessenger == XR_NULL_HANDLE) {
            qCWarning(xr_context_cat,
                      "Disabling unavailable OpenXR debug messenger");
            _debugMessenger = XR_NULL_HANDLE;
            xrCreateDebugUtilsMessengerEXT = nullptr;
            xrDestroyDebugUtilsMessengerEXT = nullptr;
            _EXT_debugUtilsSupported = false;
        }
    }

    auto next = reinterpret_cast<const XrExtensionProperties*>(props.next);
    while (next) {
        if (next->type == XR_TYPE_SYSTEM_HAND_TRACKING_PROPERTIES_EXT) {
            auto ext = reinterpret_cast<const XrSystemHandTrackingPropertiesEXT*>(next);
            _handTrackingSupported = ext->supportsHandTracking;

            if (!_handTrackingSupported) {
                next = reinterpret_cast<const XrExtensionProperties*>(next->next);
                continue;
            }

            const bool createLoaded = loadXrFunction(
                _instance,
                "xrCreateHandTrackerEXT",
                reinterpret_cast<PFN_xrVoidFunction*>(&xrCreateHandTrackerEXT)
            );

            const bool destroyLoaded = loadXrFunction(
                _instance,
                "xrDestroyHandTrackerEXT",
                reinterpret_cast<PFN_xrVoidFunction*>(&xrDestroyHandTrackerEXT)
            );

            const bool locateLoaded = loadXrFunction(
                _instance,
                "xrLocateHandJointsEXT",
                reinterpret_cast<PFN_xrVoidFunction*>(&xrLocateHandJointsEXT)
            );
            if (!areOpenXrHandTrackingFunctionsReady(
                    createLoaded && xrCreateHandTrackerEXT != nullptr,
                    destroyLoaded && xrDestroyHandTrackerEXT != nullptr,
                    locateLoaded && xrLocateHandJointsEXT != nullptr)) {
                qCWarning(xr_context_cat,
                          "Disabling hand tracking because its OpenXR API is incomplete");
                _handTrackingSupported = false;
                xrCreateHandTrackerEXT = nullptr;
                xrDestroyHandTrackerEXT = nullptr;
                xrLocateHandJointsEXT = nullptr;
            }
        }

        if (next->type == XR_TYPE_SYSTEM_XDEV_SPACE_PROPERTIES_MNDX) {
            auto ext = reinterpret_cast<const XrSystemXDevSpacePropertiesMNDX*>(next);
            _MNDX_xdevSpaceSupported = ext->supportsXDevSpace;

            if (!_MNDX_xdevSpaceSupported) {
                next = reinterpret_cast<const XrExtensionProperties*>(next->next);
                continue;
            }

            const bool createListLoaded = loadXrFunction(
                _instance,
                "xrCreateXDevListMNDX",
                reinterpret_cast<PFN_xrVoidFunction*>(&xrCreateXDevListMNDX)
            );

            const bool generationLoaded = loadXrFunction(
                _instance,
                "xrGetXDevListGenerationNumberMNDX",
                reinterpret_cast<PFN_xrVoidFunction*>(&xrGetXDevListGenerationNumberMNDX)
            );

            const bool enumerateLoaded = loadXrFunction(
                _instance,
                "xrEnumerateXDevsMNDX",
                reinterpret_cast<PFN_xrVoidFunction*>(&xrEnumerateXDevsMNDX)
            );

            const bool propertiesLoaded = loadXrFunction(
                _instance,
                "xrGetXDevPropertiesMNDX",
                reinterpret_cast<PFN_xrVoidFunction*>(&xrGetXDevPropertiesMNDX)
            );

            const bool destroyListLoaded = loadXrFunction(
                _instance,
                "xrDestroyXDevListMNDX",
                reinterpret_cast<PFN_xrVoidFunction*>(&xrDestroyXDevListMNDX)
            );

            const bool createSpaceLoaded = loadXrFunction(
                _instance,
                "xrCreateXDevSpaceMNDX",
                reinterpret_cast<PFN_xrVoidFunction*>(&xrCreateXDevSpaceMNDX)
            );
            const bool functionsReady = areOpenXrXDevFunctionsReady(
                createListLoaded && xrCreateXDevListMNDX != nullptr,
                enumerateLoaded && xrEnumerateXDevsMNDX != nullptr,
                propertiesLoaded && xrGetXDevPropertiesMNDX != nullptr,
                destroyListLoaded && xrDestroyXDevListMNDX != nullptr,
                createSpaceLoaded && xrCreateXDevSpaceMNDX != nullptr);
            if (!functionsReady) {
                qCWarning(xr_context_cat,
                          "Disabling XDev tracking because its OpenXR API is incomplete");
                _MNDX_xdevSpaceSupported = false;
                xrCreateXDevListMNDX = nullptr;
                xrGetXDevListGenerationNumberMNDX = nullptr;
                xrEnumerateXDevsMNDX = nullptr;
                xrGetXDevPropertiesMNDX = nullptr;
                xrDestroyXDevListMNDX = nullptr;
                xrCreateXDevSpaceMNDX = nullptr;
            } else if (!isOpenXrOptionalFunctionReady(
                    generationLoaded,
                    xrGetXDevListGenerationNumberMNDX != nullptr)) {
                qCWarning(xr_context_cat,
                          "Dynamic XDev generation tracking is unavailable");
                xrGetXDevListGenerationNumberMNDX = nullptr;
            }
        }

        next = reinterpret_cast<const XrExtensionProperties*>(next->next);
    }

    // don't start up hand tracking stuff if it's force disabled
    if (qApp->arguments().contains("--xrNoHandTracking")) {
        _handTrackingSupported = false;
    }

    if (qApp->arguments().contains("--xrNoBodyTracking")) {
        _MNDX_xdevSpaceSupported = false;
        _HTCX_viveTrackerInteractionSupported = false;
    }

    if (qApp->arguments().contains("--xrNoPalmPose")) {
        _palmPoseSupported = false;
    }

    bool viveEnumerationFunctionReady = false;
    if (_HTCX_viveTrackerInteractionSupported) {
        const bool viveEnumerationLoaded = loadXrFunction(
            _instance,
            "xrEnumerateViveTrackerPathsHTCX",
            reinterpret_cast<PFN_xrVoidFunction*>(&xrEnumerateViveTrackerPathsHTCX)
        );
        viveEnumerationFunctionReady = isOpenXrOptionalFunctionReady(
            viveEnumerationLoaded, xrEnumerateViveTrackerPathsHTCX != nullptr);
    }
    const auto bodyTrackingBackend = selectOpenXrBodyTrackingBackend(
        _HTCX_viveTrackerInteractionSupported,
        viveEnumerationFunctionReady,
        _MNDX_xdevSpaceSupported);
    _HTCX_viveTrackerInteractionSupported =
        bodyTrackingBackend == OpenXrBodyTrackingBackend::Vive;
    _MNDX_xdevSpaceSupported =
        bodyTrackingBackend == OpenXrBodyTrackingBackend::Mndx;
    if (!_HTCX_viveTrackerInteractionSupported) {
        xrEnumerateViveTrackerPathsHTCX = nullptr;
    }

    if (_userPresenceAvailable) {
        XrSystemUserPresencePropertiesEXT presenceProps = {XR_TYPE_SYSTEM_USER_PRESENCE_PROPERTIES_EXT};
        XrSystemProperties sysProps = {XR_TYPE_SYSTEM_PROPERTIES, &presenceProps};
        result = xrGetSystemProperties(_instance, _systemId, &sysProps);
        if (xrCheck(XR_NULL_HANDLE, result, "Couldn't get system properties")) {
            _userPresenceAvailable = presenceProps.supportsUserPresence;
        }
    }

    return true;
}

bool OpenXrContext::initGraphics() {
#if defined(HAVE_VULKAN)
    // VKTODO
    return false;
#else
    XrGraphicsRequirementsOpenGLKHR requirements = { .type = XR_TYPE_GRAPHICS_REQUIREMENTS_OPENGL_KHR };
    XrResult result = pfnGetOpenGLGraphicsRequirementsKHR(_instance, _systemId, &requirements);
    return xrCheck(_instance, result, "Failed to get OpenGL graphics requirements!");
#endif
}

bool OpenXrContext::requestExitSession() {
    if (_session == XR_NULL_HANDLE) { return true; }

    XrResult result = xrRequestExitSession(_session);
    return xrCheck(_instance, result, "Failed to request exit session!");
}

bool OpenXrContext::initSession() {
#if defined(HAVE_VULKAN)
    // VKTODO
    return false;
#else
    if (_session != XR_NULL_HANDLE) { return true; }

    XrSessionCreateInfo info = {
        .type = XR_TYPE_SESSION_CREATE_INFO,
        .next = nullptr,
        .systemId = _systemId,
    };

    bool eglBindingAvailable = false;

#if defined(XR_USE_PLATFORM_EGL)
    XrGraphicsBindingEGLMNDX eglBinding = {
        .type = XR_TYPE_GRAPHICS_BINDING_EGL_MNDX,
        .next = nullptr,
    };

    // try egl first since it should work on any platform
    // do-while so we can break out early
    do {
        if (!_MNDX_eglEnableSupported) { break; }

        auto eglContext = eglGetCurrentContext();
        auto eglDisplay = eglGetCurrentDisplay();

        if (!eglContext || !eglDisplay) { break; }

        auto attribs = std::to_array<EGLint>({
            EGL_RED_SIZE, 8,
            EGL_GREEN_SIZE, 8,
            EGL_BLUE_SIZE, 8,
            EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
#if defined(Q_OS_ANDROID)
            EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
#else
            EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT | EGL_OPENGL_ES3_BIT,
#endif
            EGL_NONE // terminator
        });
        if (!hasRequiredOpenXrEglColorAttributes(
                attribs.data(), attribs.size(), EGL_NONE,
                EGL_RED_SIZE, EGL_GREEN_SIZE, EGL_BLUE_SIZE)) {
            qCWarning(xr_context_cat, "Invalid EGL color attributes");
            break;
        }

        EGLConfig eglConfig;
        EGLint configCount = 0;
        if (
            !eglChooseConfig(eglDisplay, attribs.data(), &eglConfig, 1, &configCount) ||
            configCount != 1 ||
            !eglConfig
        ) {
            qCWarning(xr_context_cat, "Failed to get EGL config");
            break;
        }

        eglBinding.getProcAddress = eglGetProcAddress;
        eglBinding.display = eglDisplay;
        eglBinding.config = eglConfig;
        eglBinding.context = eglContext;
        info.next = &eglBinding;

        eglBindingAvailable = true;
    } while(0);
#endif

#if defined(Q_OS_ANDROID)
    // ANDROID TODO: This is untested and will need changes in
    // OpenXrDisplayPlugin to use the OpenGLES structs instead
    XrGraphicsBindingOpenGLESAndroidKHR androidBinding = {
        .type = XR_TYPE_GRAPHICS_BINDING_OPENGL_ES_ANDROID_KHR,
        .next = nullptr,
    };
    if (!eglBindingAvailable) {
        auto eglContext = eglGetCurrentContext();
        auto eglDisplay = eglGetCurrentDisplay();

        auto attribs = std::to_array<EGLint>({
            EGL_RED_SIZE, 8,
            EGL_GREEN_SIZE, 8,
            EGL_BLUE_SIZE, 8,
            EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
            EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
            EGL_NONE // terminator
        });
        if (!hasRequiredOpenXrEglColorAttributes(
                attribs.data(), attribs.size(), EGL_NONE,
                EGL_RED_SIZE, EGL_GREEN_SIZE, EGL_BLUE_SIZE)) {
            qCWarning(xr_context_cat, "Invalid EGL color attributes");
            return false;
        }

        EGLConfig eglConfig;
        EGLint configCount = 0;
        if (
            !eglChooseConfig(eglDisplay, attribs.data(), &eglConfig, 1, &configCount) ||
            configCount != 1 ||
            !eglConfig
        ) {
            qCWarning(xr_context_cat, "Failed to get EGL config");
            return false;
        }

        androidBinding.display = eglDisplay;
        androidBinding.config = eglConfig;
        androidBinding.context = eglContext;

        info.next = &androidBinding;
    }
#elif defined(Q_OS_LINUX)
    if (!eglBindingAvailable) {
        auto* xDisplay = XOpenDisplay(nullptr);
        int fbConfigCount = 0;
        auto* fbConfigs = glXGetFBConfigs(xDisplay, 0, &fbConfigCount);

        XrGraphicsBindingOpenGLXlibKHR xlibBinding = {
            .type = XR_TYPE_GRAPHICS_BINDING_OPENGL_XLIB_KHR,
            .xDisplay = xDisplay,

            // not actually used anywhere but monado now
            // requires these to be non-null (in-line with the spec)
            .visualid = 1,
            .glxFBConfig = fbConfigs[0],

            .glxDrawable = glXGetCurrentDrawable(),
            .glxContext = glXGetCurrentContext(),
        };

        // HACK: Is this a compiler bug? How come adding this check fixes
        // the XR_ERROR_GRAPHICS_DEVICE_INVALID (glxContext is null) error??
        // Putting glxContext into a separate variable and checking that *doesn't*
        // work, but checking it after xlibBinding has been initialised with it *does*?
        if (!xlibBinding.glxContext) {
            qCCritical(xr_context_cat, "OpenGL context is null");
            return false;
        }

        info.next = &xlibBinding;
    }
#elif defined(Q_OS_WIN)
    if (!eglBindingAvailable) {
        XrGraphicsBindingOpenGLWin32KHR binding = {
            .type = XR_TYPE_GRAPHICS_BINDING_OPENGL_WIN32_KHR,
            .hDC = wglGetCurrentDC(),
            .hGLRC = wglGetCurrentContext(),
        };

        // FIXME: is this the same thing as the GLX context bug?
        if (!binding.hDC || !binding.hGLRC) {
            qCCritical(xr_context_cat, "OpenGL context is null");
            return false;
        }

        info.next = &binding;
    }
#else
    #error "Unsupported platform"
#endif

    XrResult result = xrCreateSession(_instance, &info, &_session);
    if (!xrCheck(_instance, result, "Failed to create session")) {
        return false;
    }

#if defined(Q_OS_ANDROID)
    if (_displayRefreshRateSupported) {
        const bool enumerateLoaded = loadXrFunction(
            _instance, "xrEnumerateDisplayRefreshRatesFB",
            reinterpret_cast<PFN_xrVoidFunction*>(&xrEnumerateDisplayRefreshRatesFB));
        const bool getLoaded = loadXrFunction(
            _instance, "xrGetDisplayRefreshRateFB",
            reinterpret_cast<PFN_xrVoidFunction*>(&xrGetDisplayRefreshRateFB));
        const bool requestLoaded = loadXrFunction(
            _instance, "xrRequestDisplayRefreshRateFB",
            reinterpret_cast<PFN_xrVoidFunction*>(&xrRequestDisplayRefreshRateFB));
        const bool functionsLoaded = areOpenXrRefreshRateFunctionsReady(
            isOpenXrOptionalFunctionReady(
                enumerateLoaded, xrEnumerateDisplayRefreshRatesFB != nullptr),
            isOpenXrOptionalFunctionReady(
                getLoaded, xrGetDisplayRefreshRateFB != nullptr),
            isOpenXrOptionalFunctionReady(
                requestLoaded, xrRequestDisplayRefreshRateFB != nullptr));

        if (!functionsLoaded) {
            qCWarning(xr_context_cat,
                      "Disabling incomplete OpenXR display refresh-rate API");
            xrEnumerateDisplayRefreshRatesFB = nullptr;
            xrGetDisplayRefreshRateFB = nullptr;
            xrRequestDisplayRefreshRateFB = nullptr;
            _displayRefreshRateSupported = false;
        }

        if (functionsLoaded) {
            uint32_t rateCapacity = 0;
            result = xrEnumerateDisplayRefreshRatesFB(_session, 0, &rateCapacity, nullptr);
            if (xrCheck(_instance, result, "Failed to enumerate display refresh-rate count")) {
                std::vector<float> rates(rateCapacity);
                uint32_t returnedRateCount = 0;
                if (rateCapacity > 0) {
                    result = xrEnumerateDisplayRefreshRatesFB(
                        _session, rateCapacity, &returnedRateCount, rates.data());
                }
                if (rateCapacity == 0 ||
                        xrCheck(_instance, result, "Failed to enumerate display refresh rates")) {
                    if (!isOpenXrEnumerationCountWithinCapacity(
                            rateCapacity, returnedRateCount)) {
                        qCWarning(xr_context_cat,
                                  "The OpenXR runtime returned an invalid display refresh-rate count.");
                        rates.clear();
                    } else {
                        rates.resize(returnedRateCount);
                    }
                    QStringList rateNames;
                    for (float rate : rates) {
                        rateNames << QString::number(rate, 'f', 1);
                    }
                    qCInfo(xr_context_cat) << "Supported display refresh rates:" << rateNames.join(", ") << "Hz";

                    // Use the lowest native mode and keep rendering synchronized
                    // to it. Pico 4 currently advertises 72 and 90 Hz.
                    float requestedRate = selectLowestUsableOpenXrRefreshRate(
                        rates.data(), rates.size());
                    if (requestedRate > 0.0f) {
                        result = xrRequestDisplayRefreshRateFB(_session, requestedRate);
                        if (xrCheck(_instance, result, "Failed to request the lowest Pico display refresh rate")) {
                            qCInfo(xr_context_cat, "Requested Pico display refresh rate: %.1f Hz (Overte target: 72 FPS)",
                                   requestedRate);
                        }
                    } else {
                        qCWarning(xr_context_cat, "The OpenXR runtime returned no usable display refresh rate.");
                    }
                }
            }
        }
    }
#endif

    return true;
#endif
}

bool OpenXrContext::initSpaces() {
    uint32_t spaceCount = 0;
    XrResult result = xrEnumerateReferenceSpaces(_session, 0, &spaceCount, nullptr);
    if (!xrCheck(_instance, result, "Failed to enumerate reference-space count"))
        return false;

    std::vector<XrReferenceSpaceType> supportedSpaces(spaceCount);
    result = xrEnumerateReferenceSpaces(
        _session, spaceCount, &spaceCount, supportedSpaces.data());
    if (!xrCheck(_instance, result, "Failed to enumerate reference spaces"))
        return false;

    bool stageAvailable = false;
    bool localAvailable = false;
    bool viewAvailable = false;
    for (auto space : supportedSpaces) {
        stageAvailable |= space == XR_REFERENCE_SPACE_TYPE_STAGE;
        localAvailable |= space == XR_REFERENCE_SPACE_TYPE_LOCAL;
        viewAvailable |= space == XR_REFERENCE_SPACE_TYPE_VIEW;
    }
    auto worldChoice = openXrWorldSpaceChoice(stageAvailable, localAvailable);
    if (worldChoice == OpenXrWorldSpaceChoice::Unavailable || !viewAvailable) {
        qCCritical(xr_context_cat) << "OpenXR runtime lacks required world or view reference space";
        return false;
    }
    if (worldChoice == OpenXrWorldSpaceChoice::Local) {
        qCWarning(xr_context_cat) << "OpenXR stage space unavailable; using local world space";
    }

    XrReferenceSpaceCreateInfo stageSpaceInfo = {
        .type = XR_TYPE_REFERENCE_SPACE_CREATE_INFO,
        .referenceSpaceType = worldChoice == OpenXrWorldSpaceChoice::Stage
                ? XR_REFERENCE_SPACE_TYPE_STAGE : XR_REFERENCE_SPACE_TYPE_LOCAL,
        .poseInReferenceSpace = XR_INDENTITY_POSE,
    };

    result = xrCreateReferenceSpace(_session, &stageSpaceInfo, &_stageSpace);
    if (!xrCheck(_instance, result, "Failed to create world space!"))
        return false;

    XrReferenceSpaceCreateInfo viewSpaceInfo = {
        .type = XR_TYPE_REFERENCE_SPACE_CREATE_INFO,
        .referenceSpaceType = XR_REFERENCE_SPACE_TYPE_VIEW,
        .poseInReferenceSpace = XR_INDENTITY_POSE,
    };

    result = xrCreateReferenceSpace(_session, &viewSpaceInfo, &_viewSpace);
    return xrCheck(_instance, result, "Failed to create view space!");
}

#define ENUM_TO_STR(r) \
    case r:            \
        return #r

static std::string xrSessionStateStr(XrSessionState state) {
    switch (state) {
        ENUM_TO_STR(XR_SESSION_STATE_UNKNOWN);
        ENUM_TO_STR(XR_SESSION_STATE_IDLE);
        ENUM_TO_STR(XR_SESSION_STATE_READY);
        ENUM_TO_STR(XR_SESSION_STATE_SYNCHRONIZED);
        ENUM_TO_STR(XR_SESSION_STATE_VISIBLE);
        ENUM_TO_STR(XR_SESSION_STATE_FOCUSED);
        ENUM_TO_STR(XR_SESSION_STATE_STOPPING);
        ENUM_TO_STR(XR_SESSION_STATE_LOSS_PENDING);
        ENUM_TO_STR(XR_SESSION_STATE_EXITING);
        default: {
            std::ostringstream ss;
            ss << "UNKNOWN STATE " << state;
            return ss.str();
        }
    }
}

// Called before restarting a new session
void OpenXrContext::reset() {
    _shouldQuit = false;
    _lastSessionState = XR_SESSION_STATE_UNKNOWN;
}

bool OpenXrContext::updateSessionState(XrSessionState newState) {
    qCDebug(xr_context_cat, "Session state changed %s -> %s", xrSessionStateStr(_lastSessionState).c_str(),
            xrSessionStateStr(newState).c_str());
    _lastSessionState = newState;

    switch (newState) {
        // Don't run frame cycle but keep polling events
        case XR_SESSION_STATE_IDLE:
        case XR_SESSION_STATE_UNKNOWN: {
            _shouldRunFrameCycle = false;
            break;
        }

        // Run frame cycle and poll events
        case XR_SESSION_STATE_FOCUSED:
        case XR_SESSION_STATE_SYNCHRONIZED:
        case XR_SESSION_STATE_VISIBLE: {
            _shouldRunFrameCycle = true;
            break;
        }

        // Begin the session
        case XR_SESSION_STATE_READY: {
            if (!_isSessionRunning) {
                XrSessionBeginInfo session_begin_info = {
                    .type = XR_TYPE_SESSION_BEGIN_INFO,
                    .primaryViewConfigurationType = XR_VIEW_CONFIG_TYPE,
                };
                XrResult result = xrBeginSession(_session, &session_begin_info);
                if (!xrCheck(_instance, result, "Failed to begin session!"))
                    return false;
                qCDebug(xr_context_cat, "Session started!");
                _isSessionRunning = true;
            }
            _shouldRunFrameCycle = true;
            _isValid = true;
            break;
        }

        // End the session, don't render, but keep polling for events
        case XR_SESSION_STATE_STOPPING: {
            if (_isSessionRunning) {
                XrResult result = xrEndSession(_session);
                if (!xrCheck(_instance, result, "Failed to end session!"))
                    return false;
                _isSessionRunning = openXrSessionRunningAfterTermination(
                    _isSessionRunning, true);
            }
            _shouldRunFrameCycle = false;
            break;
        }

        // Destroy session, skip run frame cycle, quit
        case XR_SESSION_STATE_LOSS_PENDING:
        case XR_SESSION_STATE_EXITING: {
            XrResult result = xrDestroySession(_session);
            if (!xrCheck(_instance, result, "Failed to destroy session!"))
                return false;
            _shouldQuit = true;
            _shouldRunFrameCycle = false;
            _session = XR_NULL_HANDLE;
            _isSessionRunning = openXrSessionRunningAfterTermination(
                _isSessionRunning, true);
            _isValid = false;
            qCDebug(xr_context_cat, "Destroyed session");
            break;
        }
        default:
            qCWarning(xr_context_cat, "Unhandled session state: %d", newState);
    }

    return true;
}

bool OpenXrContext::pollEvents() {
    XrEventDataBuffer event = { .type = XR_TYPE_EVENT_DATA_BUFFER };
    XrResult result = xrPollEvent(_instance, &event);
    while (result == XR_SUCCESS) {
        const OpenXrEventDrainAction drainAction = openXrEventDrainAction(
            event.type == XR_TYPE_EVENT_DATA_INSTANCE_LOSS_PENDING);
        switch (event.type) {
            case XR_TYPE_EVENT_DATA_INSTANCE_LOSS_PENDING: {
                const auto& instanceLossPending = *reinterpret_cast<XrEventDataInstanceLossPending*>(&event);
                qCCritical(xr_context_cat,
                           "OpenXR instance loss pending at %lu; requesting shutdown.",
                           instanceLossPending.lossTime);
                _shouldQuit = true;
                _isValid = false;
                break;
            }
            case XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED: {
                const auto& sessionStateChanged = *reinterpret_cast<XrEventDataSessionStateChanged*>(&event);
                if (!updateSessionState(sessionStateChanged.state)) {
                    _isValid = openXrContextValidAfterEventProcessing(
                        _isValid, false);
                    _shouldRunFrameCycle =
                        openXrFrameCycleAllowedAfterEventProcessing(
                            false, _isValid, _shouldRunFrameCycle);
                    return false;
                }
                break;
            }
            case XR_TYPE_EVENT_DATA_INTERACTION_PROFILE_CHANGED: {
                for (int i = 0; i < HAND_COUNT; i++) {
                    XrInteractionProfileState state = { .type = XR_TYPE_INTERACTION_PROFILE_STATE };
                    XrResult res = xrGetCurrentInteractionProfile(_session, _handPaths[i], &state);
                    if (!xrCheck(_instance, res, "Failed to get interaction profile"))
                        continue;

                    _vivePoseHack[i] = _viveControllerPath != XR_NULL_PATH && state.interactionProfile == _viveControllerPath;

                    uint32_t bufferCountOutput { 0 };
                    char profilePath[XR_MAX_PATH_LENGTH] {};
                    res = xrPathToString(_instance, state.interactionProfile, XR_MAX_PATH_LENGTH, &bufferCountOutput,
                                         profilePath);
                    const bool pathConverted = xrCheck(
                        _instance, res, "Failed to get interaction profile path.");
                    const bool pathTerminated = bufferCountOutput > 0 &&
                        bufferCountOutput <= XR_MAX_PATH_LENGTH &&
                        profilePath[bufferCountOutput - 1] == '\0';
                    if (!isOpenXrPathStringUsable(
                            pathConverted, bufferCountOutput,
                            XR_MAX_PATH_LENGTH, pathTerminated)) {
                        if (pathConverted) {
                            qCWarning(xr_context_cat,
                                      "OpenXR runtime returned an invalid interaction profile path.");
                        }
                        continue;
                    }

                    qCInfo(xr_context_cat, "Controller %d: Interaction profile changed to '%s'", i, profilePath);
                }
                break;
            }
            case XR_TYPE_EVENT_DATA_USER_PRESENCE_CHANGED_EXT: {
                const auto& eventdata = *reinterpret_cast<XrEventDataUserPresenceChangedEXT*>(&event);
                _hmdMounted = eventdata.isUserPresent;
                break;
            }
            default:
                qCWarning(xr_context_cat, "Unhandled event type %d", event.type);
        }

        if (drainAction == OpenXrEventDrainAction::Stop) {
            return true;
        }
        event = { .type = XR_TYPE_EVENT_DATA_BUFFER };
        result = xrPollEvent(_instance, &event);
    }

    if (result != XR_EVENT_UNAVAILABLE) {
        qCCritical(xr_context_cat, "Failed to poll events!");
        _isValid = openXrContextValidAfterEventProcessing(
            _isValid, false);
        _shouldRunFrameCycle =
            openXrFrameCycleAllowedAfterEventProcessing(
                false, _isValid, _shouldRunFrameCycle);
        return false;
    }

    return true;
}

bool OpenXrContext::beginFrame() {
    XrFrameBeginInfo info = { .type = XR_TYPE_FRAME_BEGIN_INFO };
    XrResult result = xrBeginFrame(_session, &info);
    return xrCheck(_instance, result, "failed to begin frame!");
}

bool OpenXrContext::initPreGraphics() {
    if (!initInstance()) {
        return false;
    }

    if (!initSystem()) {
        return false;
    }

    return true;
}

bool OpenXrContext::initPostGraphics() {
    if (!initGraphics()) {
        return false;
    }

    if (!initSession()) {
        return false;
    }

    if (!initSpaces()) {
        const unsigned int cleanupTargets =
            openXrPostGraphicsCleanupTargets(
                _viewSpace != XR_NULL_HANDLE,
                _stageSpace != XR_NULL_HANDLE,
                _session != XR_NULL_HANDLE);
        if ((cleanupTargets & OpenXrPostGraphicsCleanupViewSpace) != 0) {
            xrCheck(_instance, xrDestroySpace(_viewSpace),
                    "Failed to roll back OpenXR view space");
        }
        _viewSpace = XR_NULL_HANDLE;
        if ((cleanupTargets & OpenXrPostGraphicsCleanupWorldSpace) != 0) {
            xrCheck(_instance, xrDestroySpace(_stageSpace),
                    "Failed to roll back OpenXR world space");
        }
        _stageSpace = XR_NULL_HANDLE;
        if ((cleanupTargets & OpenXrPostGraphicsCleanupSession) != 0) {
            xrCheck(_instance, xrDestroySession(_session),
                    "Failed to roll back OpenXR session");
        }
        _session = XR_NULL_HANDLE;
        _isSessionRunning = false;
        _shouldRunFrameCycle = false;
        return false;
    }

    return true;
}
