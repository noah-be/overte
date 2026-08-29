// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "E2eInputProtocol.h"

#include <openxr/openxr_loader_negotiation.h>

#include <android/log.h>

#include <chrono>
#include <cmath>
#include <cstring>
#include <iterator>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>

namespace overte::e2e::openxr {
namespace {

enum class ActionKind {
    None,
    Boolean,
    Float,
    Vector,
    Pose,
};

struct ActionBinding {
    XrInstance instance { XR_NULL_HANDLE };
    XrActionSet actionSet { XR_NULL_HANDLE };
    ActionKind kind { ActionKind::None };
    std::size_t channel { 0 };
};

struct SpaceBinding {
    XrInstance instance { XR_NULL_HANDLE };
    bool actionPose { false };
    std::size_t poseChannel { 0 };
    XrReferenceSpaceType referenceType { XR_REFERENCE_SPACE_TYPE_MAX_ENUM };
};

struct Dispatch {
    PFN_xrGetInstanceProcAddr getInstanceProcAddr { nullptr };
    PFN_xrDestroyInstance destroyInstance { nullptr };
    PFN_xrCreateSession createSession { nullptr };
    PFN_xrDestroySession destroySession { nullptr };
    PFN_xrCreateActionSet createActionSet { nullptr };
    PFN_xrDestroyActionSet destroyActionSet { nullptr };
    PFN_xrCreateAction createAction { nullptr };
    PFN_xrDestroyAction destroyAction { nullptr };
    PFN_xrCreateReferenceSpace createReferenceSpace { nullptr };
    PFN_xrCreateActionSpace createActionSpace { nullptr };
    PFN_xrDestroySpace destroySpace { nullptr };
    PFN_xrSyncActions syncActions { nullptr };
    PFN_xrGetActionStateBoolean getActionStateBoolean { nullptr };
    PFN_xrGetActionStateFloat getActionStateFloat { nullptr };
    PFN_xrGetActionStateVector2f getActionStateVector2f { nullptr };
    PFN_xrGetActionStatePose getActionStatePose { nullptr };
    PFN_xrLocateSpace locateSpace { nullptr };
    PFN_xrLocateViews locateViews { nullptr };
};

struct InstanceState {
    Dispatch dispatch;
    Protocol protocol;
};

std::mutex layerMutex;
std::unordered_map<XrInstance, std::unique_ptr<InstanceState>> instances;
std::unordered_map<XrSession, XrInstance> sessions;
std::unordered_map<XrActionSet, XrInstance> actionSets;
std::unordered_map<XrAction, ActionBinding> actions;
std::unordered_map<XrSpace, SpaceBinding> spaces;

std::int64_t epochMilliseconds() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

std::int64_t monotonicMilliseconds() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}

void logError(const char* message) {
    __android_log_print(ANDROID_LOG_ERROR, "OverteE2eOpenXR", "%s", message);
}

template<typename Function>
bool loadFunction(PFN_xrGetInstanceProcAddr getInstanceProcAddr, XrInstance instance,
                  const char* name, Function& function) {
    PFN_xrVoidFunction raw { nullptr };
    const XrResult result = getInstanceProcAddr(instance, name, &raw);
    if (XR_FAILED(result) || raw == nullptr) {
        return false;
    }
    function = reinterpret_cast<Function>(raw);
    return true;
}

bool loadDispatch(XrInstance instance, PFN_xrGetInstanceProcAddr next, Dispatch& dispatch) {
    dispatch.getInstanceProcAddr = next;
    return loadFunction(next, instance, "xrDestroyInstance", dispatch.destroyInstance) &&
        loadFunction(next, instance, "xrCreateSession", dispatch.createSession) &&
        loadFunction(next, instance, "xrDestroySession", dispatch.destroySession) &&
        loadFunction(next, instance, "xrCreateActionSet", dispatch.createActionSet) &&
        loadFunction(next, instance, "xrDestroyActionSet", dispatch.destroyActionSet) &&
        loadFunction(next, instance, "xrCreateAction", dispatch.createAction) &&
        loadFunction(next, instance, "xrDestroyAction", dispatch.destroyAction) &&
        loadFunction(next, instance, "xrCreateReferenceSpace", dispatch.createReferenceSpace) &&
        loadFunction(next, instance, "xrCreateActionSpace", dispatch.createActionSpace) &&
        loadFunction(next, instance, "xrDestroySpace", dispatch.destroySpace) &&
        loadFunction(next, instance, "xrSyncActions", dispatch.syncActions) &&
        loadFunction(next, instance, "xrGetActionStateBoolean", dispatch.getActionStateBoolean) &&
        loadFunction(next, instance, "xrGetActionStateFloat", dispatch.getActionStateFloat) &&
        loadFunction(next, instance, "xrGetActionStateVector2f", dispatch.getActionStateVector2f) &&
        loadFunction(next, instance, "xrGetActionStatePose", dispatch.getActionStatePose) &&
        loadFunction(next, instance, "xrLocateSpace", dispatch.locateSpace) &&
        loadFunction(next, instance, "xrLocateViews", dispatch.locateViews);
}

XrQuaternionf multiply(const XrQuaternionf& left, const XrQuaternionf& right) {
    XrQuaternionf result {
        left.w * right.x + left.x * right.w + left.y * right.z - left.z * right.y,
        left.w * right.y - left.x * right.z + left.y * right.w + left.z * right.x,
        left.w * right.z + left.x * right.y - left.y * right.x + left.z * right.w,
        left.w * right.w - left.x * right.x - left.y * right.y - left.z * right.z,
    };
    const float norm = std::sqrt(result.x * result.x + result.y * result.y +
                                 result.z * result.z + result.w * result.w);
    if (std::isfinite(norm) && norm > 0.0001f) {
        result.x /= norm;
        result.y /= norm;
        result.z /= norm;
        result.w /= norm;
    }
    return result;
}

XrInstance instanceForSession(XrSession session) {
    const auto iterator = sessions.find(session);
    return iterator == sessions.end() ? XR_NULL_HANDLE : iterator->second;
}

XrInstance instanceForActionSet(XrActionSet actionSet) {
    const auto iterator = actionSets.find(actionSet);
    return iterator == actionSets.end() ? XR_NULL_HANDLE : iterator->second;
}

InstanceState* stateForInstance(XrInstance instance) {
    const auto iterator = instances.find(instance);
    return iterator == instances.end() ? nullptr : iterator->second.get();
}

void eraseInstanceChildren(XrInstance instance) {
    for (auto iterator = sessions.begin(); iterator != sessions.end();) {
        iterator = iterator->second == instance ? sessions.erase(iterator) : std::next(iterator);
    }
    for (auto iterator = actionSets.begin(); iterator != actionSets.end();) {
        iterator = iterator->second == instance ? actionSets.erase(iterator) : std::next(iterator);
    }
    for (auto iterator = actions.begin(); iterator != actions.end();) {
        iterator = iterator->second.instance == instance ? actions.erase(iterator) : std::next(iterator);
    }
    for (auto iterator = spaces.begin(); iterator != spaces.end();) {
        iterator = iterator->second.instance == instance ? spaces.erase(iterator) : std::next(iterator);
    }
}

// Forward declarations for layer dispatch.
XRAPI_ATTR XrResult XRAPI_CALL layerGetInstanceProcAddr(
    XrInstance instance, const char* name, PFN_xrVoidFunction* function);
XRAPI_ATTR XrResult XRAPI_CALL layerDestroyInstance(XrInstance instance);
XRAPI_ATTR XrResult XRAPI_CALL layerCreateSession(
    XrInstance instance, const XrSessionCreateInfo* createInfo, XrSession* session);
XRAPI_ATTR XrResult XRAPI_CALL layerDestroySession(XrSession session);
XRAPI_ATTR XrResult XRAPI_CALL layerCreateActionSet(
    XrInstance instance, const XrActionSetCreateInfo* createInfo, XrActionSet* actionSet);
XRAPI_ATTR XrResult XRAPI_CALL layerDestroyActionSet(XrActionSet actionSet);
XRAPI_ATTR XrResult XRAPI_CALL layerCreateAction(
    XrActionSet actionSet, const XrActionCreateInfo* createInfo, XrAction* action);
XRAPI_ATTR XrResult XRAPI_CALL layerDestroyAction(XrAction action);
XRAPI_ATTR XrResult XRAPI_CALL layerCreateReferenceSpace(
    XrSession session, const XrReferenceSpaceCreateInfo* createInfo, XrSpace* space);
XRAPI_ATTR XrResult XRAPI_CALL layerCreateActionSpace(
    XrSession session, const XrActionSpaceCreateInfo* createInfo, XrSpace* space);
XRAPI_ATTR XrResult XRAPI_CALL layerDestroySpace(XrSpace space);
XRAPI_ATTR XrResult XRAPI_CALL layerSyncActions(
    XrSession session, const XrActionsSyncInfo* syncInfo);
XRAPI_ATTR XrResult XRAPI_CALL layerGetActionStateBoolean(
    XrSession session, const XrActionStateGetInfo* getInfo, XrActionStateBoolean* state);
XRAPI_ATTR XrResult XRAPI_CALL layerGetActionStateFloat(
    XrSession session, const XrActionStateGetInfo* getInfo, XrActionStateFloat* state);
XRAPI_ATTR XrResult XRAPI_CALL layerGetActionStateVector2f(
    XrSession session, const XrActionStateGetInfo* getInfo, XrActionStateVector2f* state);
XRAPI_ATTR XrResult XRAPI_CALL layerGetActionStatePose(
    XrSession session, const XrActionStateGetInfo* getInfo, XrActionStatePose* state);
XRAPI_ATTR XrResult XRAPI_CALL layerLocateSpace(
    XrSpace space, XrSpace baseSpace, XrTime time, XrSpaceLocation* location);
XRAPI_ATTR XrResult XRAPI_CALL layerLocateViews(
    XrSession session, const XrViewLocateInfo* viewLocateInfo, XrViewState* viewState,
    std::uint32_t viewCapacityInput, std::uint32_t* viewCountOutput, XrView* views);

template<typename Function>
bool expose(const char* requested, const char* expected, Function function,
            PFN_xrVoidFunction* output) {
    if (std::strcmp(requested, expected) != 0) {
        return false;
    }
    *output = reinterpret_cast<PFN_xrVoidFunction>(function);
    return true;
}

XRAPI_ATTR XrResult XRAPI_CALL layerGetInstanceProcAddr(
        XrInstance instance, const char* name, PFN_xrVoidFunction* function) {
    if (!name || !function) {
        return XR_ERROR_VALIDATION_FAILURE;
    }
    *function = nullptr;
    if (expose(name, "xrGetInstanceProcAddr", layerGetInstanceProcAddr, function) ||
            expose(name, "xrDestroyInstance", layerDestroyInstance, function) ||
            expose(name, "xrCreateSession", layerCreateSession, function) ||
            expose(name, "xrDestroySession", layerDestroySession, function) ||
            expose(name, "xrCreateActionSet", layerCreateActionSet, function) ||
            expose(name, "xrDestroyActionSet", layerDestroyActionSet, function) ||
            expose(name, "xrCreateAction", layerCreateAction, function) ||
            expose(name, "xrDestroyAction", layerDestroyAction, function) ||
            expose(name, "xrCreateReferenceSpace", layerCreateReferenceSpace, function) ||
            expose(name, "xrCreateActionSpace", layerCreateActionSpace, function) ||
            expose(name, "xrDestroySpace", layerDestroySpace, function) ||
            expose(name, "xrSyncActions", layerSyncActions, function) ||
            expose(name, "xrGetActionStateBoolean", layerGetActionStateBoolean, function) ||
            expose(name, "xrGetActionStateFloat", layerGetActionStateFloat, function) ||
            expose(name, "xrGetActionStateVector2f", layerGetActionStateVector2f, function) ||
            expose(name, "xrGetActionStatePose", layerGetActionStatePose, function) ||
            expose(name, "xrLocateSpace", layerLocateSpace, function) ||
            expose(name, "xrLocateViews", layerLocateViews, function)) {
        return XR_SUCCESS;
    }
    PFN_xrGetInstanceProcAddr next { nullptr };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        InstanceState* state = stateForInstance(instance);
        if (!state || !state->dispatch.getInstanceProcAddr) {
            return XR_ERROR_HANDLE_INVALID;
        }
        next = state->dispatch.getInstanceProcAddr;
    }
    return next(instance, name, function);
}

XRAPI_ATTR XrResult XRAPI_CALL layerDestroyInstance(XrInstance instance) {
    PFN_xrDestroyInstance next { nullptr };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        InstanceState* state = stateForInstance(instance);
        if (!state) {
            return XR_ERROR_HANDLE_INVALID;
        }
        next = state->dispatch.destroyInstance;
    }
    const XrResult result = next(instance);
    if (XR_SUCCEEDED(result)) {
        std::lock_guard<std::mutex> guard(layerMutex);
        eraseInstanceChildren(instance);
        instances.erase(instance);
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerCreateSession(
        XrInstance instance, const XrSessionCreateInfo* createInfo, XrSession* session) {
    PFN_xrCreateSession next { nullptr };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        InstanceState* state = stateForInstance(instance);
        if (!state) {
            return XR_ERROR_HANDLE_INVALID;
        }
        next = state->dispatch.createSession;
    }
    const XrResult result = next(instance, createInfo, session);
    if (XR_SUCCEEDED(result) && session) {
        std::lock_guard<std::mutex> guard(layerMutex);
        sessions[*session] = instance;
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerDestroySession(XrSession session) {
    PFN_xrDestroySession next { nullptr };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        InstanceState* state = stateForInstance(instanceForSession(session));
        if (!state) {
            return XR_ERROR_HANDLE_INVALID;
        }
        next = state->dispatch.destroySession;
    }
    const XrResult result = next(session);
    if (XR_SUCCEEDED(result)) {
        std::lock_guard<std::mutex> guard(layerMutex);
        sessions.erase(session);
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerCreateActionSet(
        XrInstance instance, const XrActionSetCreateInfo* createInfo, XrActionSet* actionSet) {
    PFN_xrCreateActionSet next { nullptr };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        InstanceState* state = stateForInstance(instance);
        if (!state) {
            return XR_ERROR_HANDLE_INVALID;
        }
        next = state->dispatch.createActionSet;
    }
    const XrResult result = next(instance, createInfo, actionSet);
    if (XR_SUCCEEDED(result) && actionSet) {
        std::lock_guard<std::mutex> guard(layerMutex);
        actionSets[*actionSet] = instance;
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerDestroyActionSet(XrActionSet actionSet) {
    PFN_xrDestroyActionSet next { nullptr };
    XrInstance instance { XR_NULL_HANDLE };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        instance = instanceForActionSet(actionSet);
        InstanceState* state = stateForInstance(instance);
        if (!state) {
            return XR_ERROR_HANDLE_INVALID;
        }
        next = state->dispatch.destroyActionSet;
    }
    const XrResult result = next(actionSet);
    if (XR_SUCCEEDED(result)) {
        std::lock_guard<std::mutex> guard(layerMutex);
        actionSets.erase(actionSet);
        for (auto iterator = actions.begin(); iterator != actions.end();) {
            iterator = iterator->second.actionSet == actionSet ? actions.erase(iterator)
                                                                : std::next(iterator);
        }
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerCreateAction(
        XrActionSet actionSet, const XrActionCreateInfo* createInfo, XrAction* action) {
    PFN_xrCreateAction next { nullptr };
    XrInstance instance { XR_NULL_HANDLE };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        instance = instanceForActionSet(actionSet);
        InstanceState* state = stateForInstance(instance);
        if (!state) {
            return XR_ERROR_HANDLE_INVALID;
        }
        next = state->dispatch.createAction;
    }
    const XrResult result = next(actionSet, createInfo, action);
    if (XR_SUCCEEDED(result) && createInfo && action) {
        ActionBinding binding { instance, actionSet, ActionKind::None, 0 };
        BooleanChannel booleanChannel;
        FloatChannel floatChannel;
        VectorChannel vectorChannel;
        PoseChannel poseChannel;
        if (booleanChannelForAction(createInfo->actionName, createInfo->actionType,
                                    booleanChannel)) {
            binding.kind = ActionKind::Boolean;
            binding.channel = static_cast<std::size_t>(booleanChannel);
        } else if (floatChannelForAction(createInfo->actionName, createInfo->actionType,
                                         floatChannel)) {
            binding.kind = ActionKind::Float;
            binding.channel = static_cast<std::size_t>(floatChannel);
        } else if (vectorChannelForAction(createInfo->actionName, createInfo->actionType,
                                          vectorChannel)) {
            binding.kind = ActionKind::Vector;
            binding.channel = static_cast<std::size_t>(vectorChannel);
        } else if (poseChannelForAction(createInfo->actionName, createInfo->actionType,
                                        poseChannel)) {
            binding.kind = ActionKind::Pose;
            binding.channel = static_cast<std::size_t>(poseChannel);
        }
        std::lock_guard<std::mutex> guard(layerMutex);
        actions[*action] = binding;
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerDestroyAction(XrAction action) {
    PFN_xrDestroyAction next { nullptr };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        const auto binding = actions.find(action);
        if (binding == actions.end()) {
            return XR_ERROR_HANDLE_INVALID;
        }
        InstanceState* state = stateForInstance(binding->second.instance);
        if (!state) {
            return XR_ERROR_HANDLE_INVALID;
        }
        next = state->dispatch.destroyAction;
    }
    const XrResult result = next(action);
    if (XR_SUCCEEDED(result)) {
        std::lock_guard<std::mutex> guard(layerMutex);
        actions.erase(action);
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerCreateReferenceSpace(
        XrSession session, const XrReferenceSpaceCreateInfo* createInfo, XrSpace* space) {
    PFN_xrCreateReferenceSpace next { nullptr };
    XrInstance instance { XR_NULL_HANDLE };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        instance = instanceForSession(session);
        InstanceState* state = stateForInstance(instance);
        if (!state) {
            return XR_ERROR_HANDLE_INVALID;
        }
        next = state->dispatch.createReferenceSpace;
    }
    const XrResult result = next(session, createInfo, space);
    if (XR_SUCCEEDED(result) && createInfo && space) {
        std::lock_guard<std::mutex> guard(layerMutex);
        spaces[*space] = { instance, false, 0, createInfo->referenceSpaceType };
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerCreateActionSpace(
        XrSession session, const XrActionSpaceCreateInfo* createInfo, XrSpace* space) {
    PFN_xrCreateActionSpace next { nullptr };
    XrInstance instance { XR_NULL_HANDLE };
    ActionBinding actionBinding;
    bool hasBinding = false;
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        instance = instanceForSession(session);
        InstanceState* state = stateForInstance(instance);
        if (!state) {
            return XR_ERROR_HANDLE_INVALID;
        }
        next = state->dispatch.createActionSpace;
        if (createInfo) {
            const auto iterator = actions.find(createInfo->action);
            if (iterator != actions.end()) {
                actionBinding = iterator->second;
                hasBinding = true;
            }
        }
    }
    const XrResult result = next(session, createInfo, space);
    if (XR_SUCCEEDED(result) && space) {
        SpaceBinding binding { instance, false, 0, XR_REFERENCE_SPACE_TYPE_MAX_ENUM };
        if (hasBinding && actionBinding.kind == ActionKind::Pose) {
            binding.actionPose = true;
            binding.poseChannel = actionBinding.channel;
        }
        std::lock_guard<std::mutex> guard(layerMutex);
        spaces[*space] = binding;
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerDestroySpace(XrSpace space) {
    PFN_xrDestroySpace next { nullptr };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        const auto binding = spaces.find(space);
        if (binding == spaces.end()) {
            return XR_ERROR_HANDLE_INVALID;
        }
        InstanceState* state = stateForInstance(binding->second.instance);
        if (!state) {
            return XR_ERROR_HANDLE_INVALID;
        }
        next = state->dispatch.destroySpace;
    }
    const XrResult result = next(space);
    if (XR_SUCCEEDED(result)) {
        std::lock_guard<std::mutex> guard(layerMutex);
        spaces.erase(space);
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerSyncActions(
        XrSession session, const XrActionsSyncInfo* syncInfo) {
    PFN_xrSyncActions next { nullptr };
    XrInstance instance { XR_NULL_HANDLE };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        instance = instanceForSession(session);
        InstanceState* state = stateForInstance(instance);
        if (!state) {
            return XR_ERROR_HANDLE_INVALID;
        }
        next = state->dispatch.syncActions;
    }
    const XrResult result = next(session, syncInfo);
    if (XR_SUCCEEDED(result)) {
        std::lock_guard<std::mutex> guard(layerMutex);
        InstanceState* state = stateForInstance(instance);
        if (state) {
            state->protocol.sync(epochMilliseconds(), monotonicMilliseconds());
        }
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerGetActionStateBoolean(
        XrSession session, const XrActionStateGetInfo* getInfo, XrActionStateBoolean* output) {
    PFN_xrGetActionStateBoolean next { nullptr };
    XrInstance instance { XR_NULL_HANDLE };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        instance = instanceForSession(session);
        InstanceState* state = stateForInstance(instance);
        if (!state) { return XR_ERROR_HANDLE_INVALID; }
        next = state->dispatch.getActionStateBoolean;
    }
    const XrResult result = next(session, getInfo, output);
    if (XR_SUCCEEDED(result) && getInfo && output) {
        std::lock_guard<std::mutex> guard(layerMutex);
        InstanceState* state = stateForInstance(instance);
        const auto binding = actions.find(getInfo->action);
        if (state && binding != actions.end() && binding->second.kind == ActionKind::Boolean &&
                state->protocol.current().overrideEnabled) {
            const bool current = state->protocol.current().booleans[binding->second.channel];
            const bool previous = state->protocol.previous().booleans[binding->second.channel];
            output->isActive = XR_TRUE;
            output->currentState = current ? XR_TRUE : XR_FALSE;
            output->changedSinceLastSync = current != previous ? XR_TRUE : XR_FALSE;
            if (current != previous && output->lastChangeTime <= 0) { output->lastChangeTime = 1; }
            state->protocol.recordBooleanApplication(
                static_cast<BooleanChannel>(binding->second.channel), current,
                epochMilliseconds());
        }
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerGetActionStateFloat(
        XrSession session, const XrActionStateGetInfo* getInfo, XrActionStateFloat* output) {
    PFN_xrGetActionStateFloat next { nullptr };
    XrInstance instance { XR_NULL_HANDLE };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        instance = instanceForSession(session);
        InstanceState* state = stateForInstance(instance);
        if (!state) { return XR_ERROR_HANDLE_INVALID; }
        next = state->dispatch.getActionStateFloat;
    }
    const XrResult result = next(session, getInfo, output);
    if (XR_SUCCEEDED(result) && getInfo && output) {
        std::lock_guard<std::mutex> guard(layerMutex);
        InstanceState* state = stateForInstance(instance);
        const auto binding = actions.find(getInfo->action);
        if (state && binding != actions.end() && binding->second.kind == ActionKind::Float &&
                state->protocol.current().overrideEnabled) {
            const float current = state->protocol.current().floats[binding->second.channel];
            const float previous = state->protocol.previous().floats[binding->second.channel];
            output->isActive = XR_TRUE;
            output->currentState = current;
            output->changedSinceLastSync = current != previous ? XR_TRUE : XR_FALSE;
            if (current != previous && output->lastChangeTime <= 0) { output->lastChangeTime = 1; }
        }
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerGetActionStateVector2f(
        XrSession session, const XrActionStateGetInfo* getInfo, XrActionStateVector2f* output) {
    PFN_xrGetActionStateVector2f next { nullptr };
    XrInstance instance { XR_NULL_HANDLE };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        instance = instanceForSession(session);
        InstanceState* state = stateForInstance(instance);
        if (!state) { return XR_ERROR_HANDLE_INVALID; }
        next = state->dispatch.getActionStateVector2f;
    }
    const XrResult result = next(session, getInfo, output);
    if (XR_SUCCEEDED(result) && getInfo && output) {
        std::lock_guard<std::mutex> guard(layerMutex);
        InstanceState* state = stateForInstance(instance);
        const auto binding = actions.find(getInfo->action);
        if (state && binding != actions.end() && binding->second.kind == ActionKind::Vector &&
                state->protocol.current().overrideEnabled) {
            const XrVector2f current = state->protocol.current().vectors[binding->second.channel];
            const XrVector2f previous = state->protocol.previous().vectors[binding->second.channel];
            const bool changed = current.x != previous.x || current.y != previous.y;
            output->isActive = XR_TRUE;
            output->currentState = current;
            output->changedSinceLastSync = changed ? XR_TRUE : XR_FALSE;
            if (changed && output->lastChangeTime <= 0) { output->lastChangeTime = 1; }
            state->protocol.recordVectorApplication(
                static_cast<VectorChannel>(binding->second.channel), current,
                epochMilliseconds());
        }
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerGetActionStatePose(
        XrSession session, const XrActionStateGetInfo* getInfo, XrActionStatePose* output) {
    PFN_xrGetActionStatePose next { nullptr };
    XrInstance instance { XR_NULL_HANDLE };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        instance = instanceForSession(session);
        InstanceState* state = stateForInstance(instance);
        if (!state) { return XR_ERROR_HANDLE_INVALID; }
        next = state->dispatch.getActionStatePose;
    }
    const XrResult result = next(session, getInfo, output);
    if (XR_SUCCEEDED(result) && getInfo && output) {
        std::lock_guard<std::mutex> guard(layerMutex);
        InstanceState* state = stateForInstance(instance);
        const auto binding = actions.find(getInfo->action);
        if (state && binding != actions.end() && binding->second.kind == ActionKind::Pose &&
                state->protocol.current().overrideEnabled &&
                state->protocol.current().poses[binding->second.channel].active) {
            output->isActive = XR_TRUE;
        }
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerLocateSpace(
        XrSpace space, XrSpace baseSpace, XrTime time, XrSpaceLocation* location) {
    PFN_xrLocateSpace next { nullptr };
    XrInstance instance { XR_NULL_HANDLE };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        const auto binding = spaces.find(space);
        if (binding == spaces.end()) { return XR_ERROR_HANDLE_INVALID; }
        instance = binding->second.instance;
        InstanceState* state = stateForInstance(instance);
        if (!state) { return XR_ERROR_HANDLE_INVALID; }
        next = state->dispatch.locateSpace;
    }
    const XrResult result = next(space, baseSpace, time, location);
    if (XR_SUCCEEDED(result) && location) {
        std::lock_guard<std::mutex> guard(layerMutex);
        InstanceState* state = stateForInstance(instance);
        const auto binding = spaces.find(space);
        const auto base = spaces.find(baseSpace);
        if (!state || binding == spaces.end() || !state->protocol.current().overrideEnabled) {
            return result;
        }
        const bool stageBase = base != spaces.end() && !base->second.actionPose &&
            base->second.referenceType == XR_REFERENCE_SPACE_TYPE_STAGE;
        if (binding->second.actionPose) {
            const PoseOverride& pose =
                state->protocol.current().poses[binding->second.poseChannel];
            if (pose.active) {
                if (!stageBase) {
                    state->protocol.failClosed("pose-base-not-stage", epochMilliseconds());
                    location->locationFlags = 0;
                    return result;
                }
                location->pose = pose.pose;
                location->locationFlags =
                    XR_SPACE_LOCATION_ORIENTATION_VALID_BIT |
                    XR_SPACE_LOCATION_POSITION_VALID_BIT |
                    XR_SPACE_LOCATION_ORIENTATION_TRACKED_BIT |
                    XR_SPACE_LOCATION_POSITION_TRACKED_BIT;
            }
        } else if (binding->second.referenceType == XR_REFERENCE_SPACE_TYPE_VIEW &&
                   stageBase && state->protocol.current().viewActive &&
                   (location->locationFlags & XR_SPACE_LOCATION_ORIENTATION_VALID_BIT) != 0) {
            location->pose.orientation = multiply(
                state->protocol.current().viewOrientation, location->pose.orientation);
            state->protocol.recordViewApplication(epochMilliseconds());
        }
    }
    return result;
}

XRAPI_ATTR XrResult XRAPI_CALL layerLocateViews(
        XrSession session, const XrViewLocateInfo* viewLocateInfo, XrViewState* viewState,
        std::uint32_t viewCapacityInput, std::uint32_t* viewCountOutput, XrView* views) {
    PFN_xrLocateViews next { nullptr };
    XrInstance instance { XR_NULL_HANDLE };
    {
        std::lock_guard<std::mutex> guard(layerMutex);
        instance = instanceForSession(session);
        InstanceState* state = stateForInstance(instance);
        if (!state) { return XR_ERROR_HANDLE_INVALID; }
        next = state->dispatch.locateViews;
    }
    const XrResult result = next(session, viewLocateInfo, viewState, viewCapacityInput,
                                 viewCountOutput, views);
    if (XR_SUCCEEDED(result) && viewState && views && viewCountOutput &&
            viewCapacityInput >= *viewCountOutput &&
            (viewState->viewStateFlags & XR_VIEW_STATE_ORIENTATION_VALID_BIT) != 0) {
        std::lock_guard<std::mutex> guard(layerMutex);
        InstanceState* state = stateForInstance(instance);
        if (state && state->protocol.current().overrideEnabled &&
                state->protocol.current().viewActive) {
            for (std::uint32_t index = 0; index < *viewCountOutput; ++index) {
                views[index].pose.orientation = multiply(
                    state->protocol.current().viewOrientation, views[index].pose.orientation);
            }
            state->protocol.recordViewApplication(epochMilliseconds());
        }
    }
    return result;
}

}  // namespace
}  // namespace overte::e2e::openxr

#if defined(__GNUC__)
#define OVERTE_E2E_EXPORT __attribute__((visibility("default")))
#else
#define OVERTE_E2E_EXPORT
#endif

extern "C" OVERTE_E2E_EXPORT XRAPI_ATTR const char* XRAPI_CALL
overteE2eOpenXrInputBuildMarker() {
    return overte::e2e::openxr::BUILD_MARKER;
}

extern "C" OVERTE_E2E_EXPORT XRAPI_ATTR XrResult XRAPI_CALL xrCreateApiLayerInstance(
        const XrInstanceCreateInfo* info, const XrApiLayerCreateInfo* layerInfo,
        XrInstance* instance) {
    using namespace overte::e2e::openxr;
    if (!info || !layerInfo || !instance ||
            layerInfo->structType != XR_LOADER_INTERFACE_STRUCT_API_LAYER_CREATE_INFO ||
            layerInfo->structVersion != XR_API_LAYER_CREATE_INFO_STRUCT_VERSION ||
            layerInfo->structSize < sizeof(XrApiLayerCreateInfo) || !layerInfo->nextInfo ||
            layerInfo->nextInfo->structType !=
                XR_LOADER_INTERFACE_STRUCT_API_LAYER_NEXT_INFO ||
            layerInfo->nextInfo->structVersion != XR_API_LAYER_NEXT_INFO_STRUCT_VERSION ||
            layerInfo->nextInfo->structSize < sizeof(XrApiLayerNextInfo) ||
            std::strcmp(layerInfo->nextInfo->layerName, LAYER_NAME) != 0 ||
            !layerInfo->nextInfo->nextGetInstanceProcAddr ||
            !layerInfo->nextInfo->nextCreateApiLayerInstance) {
        return XR_ERROR_INITIALIZATION_FAILED;
    }
    XrApiLayerCreateInfo nextInfo = *layerInfo;
    nextInfo.nextInfo = layerInfo->nextInfo->next;
    const XrResult result = layerInfo->nextInfo->nextCreateApiLayerInstance(
        info, &nextInfo, instance);
    if (XR_FAILED(result)) {
        return result;
    }
    auto state = std::make_unique<InstanceState>();
    if (!loadDispatch(*instance, layerInfo->nextInfo->nextGetInstanceProcAddr,
                      state->dispatch)) {
        logError("could not load downstream OpenXR dispatch");
        if (state->dispatch.destroyInstance) {
            state->dispatch.destroyInstance(*instance);
        }
        *instance = XR_NULL_HANDLE;
        return XR_ERROR_INITIALIZATION_FAILED;
    }
    std::lock_guard<std::mutex> guard(layerMutex);
    instances.emplace(*instance, std::move(state));
    return XR_SUCCESS;
}

extern "C" OVERTE_E2E_EXPORT XRAPI_ATTR XrResult XRAPI_CALL
xrNegotiateLoaderApiLayerInterface(
        const XrNegotiateLoaderInfo* loaderInfo, const char* layerName,
        XrNegotiateApiLayerRequest* request) {
    using namespace overte::e2e::openxr;
    if (!loaderInfo || !layerName || !request ||
            std::strcmp(layerName, LAYER_NAME) != 0 ||
            loaderInfo->structType != XR_LOADER_INTERFACE_STRUCT_LOADER_INFO ||
            loaderInfo->structVersion != XR_LOADER_INFO_STRUCT_VERSION ||
            loaderInfo->structSize < sizeof(XrNegotiateLoaderInfo) ||
            request->structType != XR_LOADER_INTERFACE_STRUCT_API_LAYER_REQUEST ||
            request->structVersion != XR_API_LAYER_INFO_STRUCT_VERSION ||
            request->structSize < sizeof(XrNegotiateApiLayerRequest) ||
            loaderInfo->minInterfaceVersion > XR_CURRENT_LOADER_API_LAYER_VERSION ||
            loaderInfo->maxInterfaceVersion < XR_CURRENT_LOADER_API_LAYER_VERSION ||
            loaderInfo->minApiVersion > XR_CURRENT_API_VERSION ||
            loaderInfo->maxApiVersion < XR_MAKE_VERSION(1, 0, 0)) {
        return XR_ERROR_INITIALIZATION_FAILED;
    }
    request->layerInterfaceVersion = XR_CURRENT_LOADER_API_LAYER_VERSION;
    request->layerApiVersion = loaderInfo->maxApiVersion < XR_CURRENT_API_VERSION
        ? loaderInfo->maxApiVersion : XR_CURRENT_API_VERSION;
    request->getInstanceProcAddr = layerGetInstanceProcAddr;
    request->createApiLayerInstance = xrCreateApiLayerInstance;
    return XR_SUCCESS;
}
