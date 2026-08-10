//
// Overte OpenXR Plugin
//
// Copyright 2024 Lubosz Sarnecki
// Copyright 2024 Overte e.V.
//
// SPDX-License-Identifier: Apache-2.0
//

#pragma once

#include <optional>

#if defined(__ANDROID__)
#include <jni.h>
#endif

#include <openxr/openxr.h>
#include "vendored_headers/XR_MNDX_xdev_space.h"

#include "gpu/gl/GLBackend.h"

#if defined(HAVE_VULKAN)
    #warning "OpenXR plugin doesn't support Vulkan yet and will always fail on startup"
    #define XR_USE_GRAPHICS_API_VULKAN
#else
    #if defined(Q_OS_ANDROID)
        #define XR_USE_GRAPHICS_API_OPENGL_ES
        #define XR_USE_PLATFORM_ANDROID
        #define XR_USE_PLATFORM_EGL
    #elif defined(Q_OS_LINUX)
        #define XR_USE_GRAPHICS_API_OPENGL
        // Wayland uses XR_USE_PLATFORM_EGL, XR_USE_PLATFORM_WAYLAND
        // is deprecated and never worked anyway
        #define XR_USE_PLATFORM_EGL
        #define XR_USE_PLATFORM_XLIB
        #include <GL/glx.h>
        // Unsorted from glx.h conflicts with qdir.h
        #undef Unsorted
        // MappingPointer from X11 conflicts with one from controllers/Forward.h
        #undef MappingPointer
        // CursorShape conflicts with QCursor
        #undef CursorShape
    #elif defined(Q_OS_WIN)
        // TODO: We can't support EGL on Windows yet, because we create
        // the OpenGL contexts ourselves using WGL on Windows.
        #define XR_USE_GRAPHICS_API_OPENGL
        #define XR_USE_PLATFORM_WIN32
        #include <Unknwn.h>
        #include <Windows.h>
    #else
        #error "Unsupported platform"
    #endif

    #if defined(XR_USE_PLATFORM_EGL)
        #include <EGL/egl.h>
    #endif
#endif


#include <openxr/openxr_platform.h>

#if defined(Q_OS_ANDROID)
// The renderer treats GL and GLES swapchain images identically (both carry an
// OpenGL texture name), while OpenXR exposes platform-specific type names.
using XrSwapchainImageOpenGLKHR = XrSwapchainImageOpenGLESKHR;
using XrGraphicsRequirementsOpenGLKHR = XrGraphicsRequirementsOpenGLESKHR;
using PFN_xrGetOpenGLGraphicsRequirementsKHR = PFN_xrGetOpenGLESGraphicsRequirementsKHR;
#define XR_TYPE_SWAPCHAIN_IMAGE_OPENGL_KHR XR_TYPE_SWAPCHAIN_IMAGE_OPENGL_ES_KHR
#define XR_TYPE_GRAPHICS_REQUIREMENTS_OPENGL_KHR XR_TYPE_GRAPHICS_REQUIREMENTS_OPENGL_ES_KHR
#define XR_KHR_OPENGL_ENABLE_EXTENSION_NAME XR_KHR_OPENGL_ES_ENABLE_EXTENSION_NAME
#endif

#include <glm/glm.hpp>
#include <glm/gtx/quaternion.hpp>

#include "controllers/Pose.h"

#define HAND_COUNT 2

constexpr XrPosef XR_INDENTITY_POSE = {
    .orientation = { .x = 0, .y = 0, .z = 0, .w = 1.0 },
    .position = { .x = 0, .y = 0, .z = 0 },
};

constexpr XrViewConfigurationType XR_VIEW_CONFIG_TYPE = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;

class OpenXrContext {
public:
    XrInstance _instance = XR_NULL_HANDLE;
    XrSession _session = XR_NULL_HANDLE;
    XrSystemId _systemId = XR_NULL_SYSTEM_ID;

    XrSpace _stageSpace = XR_NULL_HANDLE;
    XrSpace _viewSpace = XR_NULL_HANDLE;
    XrPath _handPaths[HAND_COUNT] { XR_NULL_PATH, XR_NULL_PATH };

    controller::Pose _lastHeadPose;
    std::optional<XrTime> _lastPredictedDisplayTime;
    XrDuration _lastPredictedDisplayPeriod { 0 };

    XrTime inputPredictionTime() const {
        if (!_lastPredictedDisplayTime.has_value()) {
            return 0;
        }
#if defined(Q_OS_ANDROID)
        // Input is sampled while preparing the frame after the one described
        // by the most recent xrWaitFrame result.
        return _lastPredictedDisplayTime.value() + _lastPredictedDisplayPeriod;
#else
        return _lastPredictedDisplayTime.value();
#endif
    }

    bool _isValid = true; // set to false when the context is lost
    bool _shouldQuit = false;
    bool _shouldRunFrameCycle = false;
    bool _isDisplayActive = false;

    bool _isSupported = false;

    QString _systemName;
    bool _isSessionRunning = false;

    std::array<bool, HAND_COUNT> _vivePoseHack = { false, false };

    // only supported by a few runtimes, but lets us
    // emulate OpenVR's headset proximity sensor system
    bool _userPresenceAvailable = false;

    // whether the headset is on, using XR_EXT_user_presence
    bool _hmdMounted = true;

    bool _handTrackingSupported = false;
    PFN_xrCreateHandTrackerEXT xrCreateHandTrackerEXT = nullptr;
    PFN_xrLocateHandJointsEXT xrLocateHandJointsEXT = nullptr;
    PFN_xrDestroyHandTrackerEXT xrDestroyHandTrackerEXT = nullptr;

    bool _palmPoseSupported = false;
    bool _BD_controllerInteractionSupported = false;

#if defined(Q_OS_ANDROID)
    bool _displayRefreshRateSupported = false;
    bool _picoLatencyTraceEnabled = false;
    PFN_xrEnumerateDisplayRefreshRatesFB xrEnumerateDisplayRefreshRatesFB = nullptr;
    PFN_xrGetDisplayRefreshRateFB xrGetDisplayRefreshRateFB = nullptr;
    PFN_xrRequestDisplayRefreshRateFB xrRequestDisplayRefreshRateFB = nullptr;

    bool _foveationSupported = false;
    PFN_xrCreateFoveationProfileFB xrCreateFoveationProfileFB = nullptr;
    PFN_xrDestroyFoveationProfileFB xrDestroyFoveationProfileFB = nullptr;
    PFN_xrUpdateSwapchainFB xrUpdateSwapchainFB = nullptr;
#endif

    bool _MNDX_xdevSpaceSupported = false;
    PFN_xrCreateXDevListMNDX xrCreateXDevListMNDX = nullptr;
    PFN_xrGetXDevListGenerationNumberMNDX xrGetXDevListGenerationNumberMNDX = nullptr;
    PFN_xrEnumerateXDevsMNDX xrEnumerateXDevsMNDX = nullptr;
    PFN_xrGetXDevPropertiesMNDX xrGetXDevPropertiesMNDX = nullptr;
    PFN_xrDestroyXDevListMNDX xrDestroyXDevListMNDX = nullptr;
    PFN_xrCreateXDevSpaceMNDX xrCreateXDevSpaceMNDX = nullptr;

    bool _HTCX_viveTrackerInteractionSupported = false;
    PFN_xrEnumerateViveTrackerPathsHTCX xrEnumerateViveTrackerPathsHTCX = nullptr;

    bool _MNDX_eglEnableSupported = false;

    bool _EXT_debugUtilsSupported = false;
    XrDebugUtilsMessengerEXT _debugMessenger = {};
    PFN_xrCreateDebugUtilsMessengerEXT xrCreateDebugUtilsMessengerEXT = nullptr;
    PFN_xrDestroyDebugUtilsMessengerEXT xrDestroyDebugUtilsMessengerEXT = nullptr;

private:
    XrSessionState _lastSessionState = XR_SESSION_STATE_UNKNOWN;

    XrPath _viveControllerPath = XR_NULL_PATH;

public:
    OpenXrContext();
    ~OpenXrContext();

    bool initPostGraphics();
    bool beginFrame();
    bool pollEvents();
    bool requestExitSession();
    void reset();

private:
    bool initPreGraphics();
    bool initInstance();
    bool initSystem();
    bool initGraphics();
    bool initSession();
    bool initSpaces();

    bool updateSessionState(XrSessionState newState);
};

inline static glm::vec3 xrVecToGlm(const XrVector3f& v) {
    return glm::vec3(v.x, v.y, v.z);
}

inline static glm::quat xrQuatToGlm(const XrQuaternionf& q) {
    return glm::quat(q.w, q.x, q.y, q.z);
}

bool xrCheck(XrInstance instance, XrResult result, const char* message);
