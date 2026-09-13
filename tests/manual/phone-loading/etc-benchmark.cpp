// Deterministic, cache-independent ETC workload for on-device A/B comparison.
#include <Etc.h>
#include <EtcFilter.h>
#include <chrono>
#include <cstdio>
#include <cstdint>
#include <vector>

int main() {
    for (int test = 0; test < 3; ++test) {
        const unsigned size = test == 2 ? 512 : 256;
        const unsigned levels = test == 2 ? 10 : 9;
        std::vector<float> pixels(size * size * 4);
        uint32_t random = 12345;
        for (unsigned y = 0; y < size; ++y) {
            for (unsigned x = 0; x < size; ++x) {
                for (unsigned c = 0; c < 4; ++c) {
                    random = random * 1664525u + 1013904223u;
                    const unsigned value = test == 1 ? random >> 24 : (x * 7 + y * 3 + c * 61) % 256;
                    pixels[(y * size + x) * 4 + c] = (c == 3 && test != 1) ? 1.0f : value / 255.0f;
                }
            }
        }
        std::vector<Etc::RawImage> mips(levels);
        int reportedMs = 0;
        auto start = std::chrono::steady_clock::now();
        Etc::EncodeMipmaps(pixels.data(), size, size, Etc::Image::Format::SRGBA8,
            Etc::ErrorMetric::RGBA, 1.0f, 4, 4, levels, Etc::FILTER_WRAP_NONE, mips.data(), &reportedMs);
        const auto us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - start).count();
        uint64_t hash = 14695981039346656037ull;
        unsigned bytes = 0;
        for (const auto& mip : mips) {
            if (!mip.paucEncodingBits || !mip.uiEncodingBitsBytes) { return 2; }
            bytes += mip.uiEncodingBitsBytes;
            for (unsigned i = 0; i < mip.uiEncodingBitsBytes; ++i) {
                hash ^= mip.paucEncodingBits.get()[i];
                hash *= 1099511628211ull;
            }
        }
        Etc::Image source(pixels.data(), size, size, Etc::ErrorMetric::RGBA);
        Etc::Image decoded(Etc::Image::Format::SRGBA8, size, size,
            mips[0].paucEncodingBits.get(), mips[0].uiEncodingBitsBytes, &source, Etc::ErrorMetric::RGBA);
        const double error = decoded.GetError() / (size * size);
        printf("{\"test\":%d,\"size\":%u,\"us\":%lld,\"error_per_pixel\":%.9f,\"bytes\":%u,\"hash\":\"%016llx\"}\n",
            test, size, static_cast<long long>(us), error, bytes, static_cast<unsigned long long>(hash));
        fflush(stdout);
    }
}
