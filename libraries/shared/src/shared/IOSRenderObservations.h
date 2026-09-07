// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cstdint>
#include <initializer_list>
#include <limits>
#include <mutex>
#include <utility>

// Process-local numeric observations, never world identity or acceptance.
// No strings, addresses, shader names, URLs or pixels enter this transport.
#define OVERTE_IOS_RENDER_METRICS(X) \
    X(sequence) X(domainConnections) X(entityServers) X(entityQueries) \
    X(entityPackets) X(entityCommits) X(renderHandoffs) \
    X(qmlUploads) X(qmlWidth) X(qmlHeight) X(qmlSamples) X(qmlAlphaSamples) X(qmlNonBlackSamples) \
    X(pipelineAttempts) X(pipelineCreated) X(pipelineFailed) X(pipelineTopology) \
    X(pipelineVertexBindings) X(pipelineVertexAttributes) X(pipelineVertexDescriptors) X(pipelineFragmentDescriptors) \
    X(uniformFallbacks) X(storageFallbacks) X(textureFallbacks) \
    X(descriptorChecks) X(descriptorExpected) X(descriptorWritten) X(descriptorMissing) X(descriptorInvalid) \
    X(drawChecks) X(invalidDrawRanges) X(invalidObjectRanges) \
    X(recoveredSubmits) X(quarantinedDraws) X(configReloads)

namespace overte { namespace ios {
enum class RenderMetric : std::size_t {
#define OVERTE_IOS_METRIC_ENUM(name) name,
    OVERTE_IOS_RENDER_METRICS(OVERTE_IOS_METRIC_ENUM)
#undef OVERTE_IOS_METRIC_ENUM
    Count
};
constexpr std::size_t renderMetricCount = static_cast<std::size_t>(RenderMetric::Count);
constexpr std::array<const char*, renderMetricCount> renderMetricNames {{
#define OVERTE_IOS_METRIC_NAME(name) #name,
    OVERTE_IOS_RENDER_METRICS(OVERTE_IOS_METRIC_NAME)
#undef OVERTE_IOS_METRIC_NAME
}};
using RenderSnapshot = std::array<std::uint64_t, renderMetricCount>;
struct RenderObservationState { std::mutex mutex; RenderSnapshot values {}; };
inline RenderObservationState& renderObservationState() {
    static RenderObservationState state;
    return state;
}
inline void incrementRenderValue(std::uint64_t& value) {
    if (value != std::numeric_limits<std::uint64_t>::max()) { ++value; }
}
// A single producer update is atomic with respect to the exported snapshot.
inline void observeRender(RenderMetric counter,
        std::initializer_list<std::pair<RenderMetric, std::uint64_t>> gauges = {}) {
    const auto index = static_cast<std::size_t>(counter);
    if (index == 0 || index >= renderMetricCount) { return; }
    for (const auto& gauge : gauges) {
        const auto position = static_cast<std::size_t>(gauge.first);
        if (position == 0 || position >= renderMetricCount) { return; }
    }
    auto& state = renderObservationState();
    std::lock_guard<std::mutex> lock(state.mutex);
    incrementRenderValue(state.values[index]);
    for (const auto& gauge : gauges) { state.values[static_cast<std::size_t>(gauge.first)] = gauge.second; }
    incrementRenderValue(state.values[0]);
}
inline RenderSnapshot renderObservations() {
    auto& state = renderObservationState();
    std::lock_guard<std::mutex> lock(state.mutex);
    return state.values;
}
}}
#undef OVERTE_IOS_RENDER_METRICS
