#include "TextureCache.h"

#include <cassert>

#include <gl/Config.h>

#include <QtCore/QThread>
#include <QtCore/QCoreApplication>

#include <shared/GlobalAppProperties.h>

#include "Profiling.h"

using namespace hifi::qml::impl;

uint64_t uvec2ToUint64(const QSize& size, bool generateMips) {
    uint64_t result = size.width();
    result <<= 32;
    result |= size.height();
    if (!generateMips) {
        result |= (uint64_t { 1 } << 63);
    }
    return result;
}

void TextureCache::acquireSize(const QSize& size, bool generateMips) {
    auto sizeKey = uvec2ToUint64(size, generateMips);
    Lock lock(_mutex);
    auto& textureSet = _textures[sizeKey];
    ++textureSet.clientCount;
}

void TextureCache::releaseSize(const QSize& size, bool generateMips) {
    auto sizeKey = uvec2ToUint64(size, generateMips);
    {
        Lock lock(_mutex);
        assert(_textures.count(sizeKey));
        auto& textureSet = _textures[sizeKey];
        if (0 == --textureSet.clientCount) {
            for (const auto& textureAndFence : textureSet.returnedTextures) {
                destroy(textureAndFence);
            }
            _textures.erase(sizeKey);
        }
    }
}

uint32_t TextureCache::acquireTexture(const QSize& size, bool generateMips) {
    Lock lock(_mutex);
    recycle();

    ++_activeTextureCount;
    auto sizeKey = uvec2ToUint64(size, generateMips);
    assert(_textures.count(sizeKey));
    auto& textureSet = _textures[sizeKey];
    if (!textureSet.returnedTextures.empty()) {
        auto textureAndFence = textureSet.returnedTextures.front();
        textureSet.returnedTextures.pop_front();
        if (textureAndFence.second) {
            glWaitSync((GLsync)textureAndFence.second, 0, GL_TIMEOUT_IGNORED);
            glDeleteSync((GLsync)textureAndFence.second);
        }
        return textureAndFence.first;
    }
    return createTexture(size, generateMips);
}

void TextureCache::releaseTexture(const Value& textureAndFence) {
    --_activeTextureCount;
    Lock lock(_mutex);
    _returnedTextures.push_back(textureAndFence);
}

void TextureCache::report() {
    if (randFloat() < 0.01f) {
        PROFILE_COUNTER(render_qml_gl, "offscreenTextures",
                        {
                            { "total", QVariant::fromValue(_allTextureCount.load()) },
                            { "active", QVariant::fromValue(_activeTextureCount.load()) },
                        });
        PROFILE_COUNTER(render_qml_gl, "offscreenTextureMemory", { { "value", QVariant::fromValue(_totalTextureUsage) } });
    }
}

size_t TextureCache::getUsedTextureMemory() {
    size_t toReturn;
    {
        Lock lock(_mutex);
        toReturn = _totalTextureUsage;
    }
    return toReturn;
}

size_t TextureCache::getMemoryForSize(const QSize& size, bool generateMips) {
    const auto baseSize = static_cast<size_t>((size.width() * size.height()) << 2);
    return generateMips ? static_cast<size_t>(baseSize * 1.33f) : baseSize;
}

void TextureCache::destroyTexture(uint32_t texture) {
    --_allTextureCount;
    const auto info = _textureSizes[texture];
    assert(getMemoryForSize(info.size, info.generateMips) <= _totalTextureUsage);
    _totalTextureUsage -= getMemoryForSize(info.size, info.generateMips);
    _textureSizes.erase(texture);
    // FIXME prevents crash on shutdown, but we should migrate to a global functions object owned by the shared context.
    glDeleteTextures(1, &texture);
}

void TextureCache::destroy(const Value& textureAndFence) {
    const auto& fence = textureAndFence.second;
    if (fence) {
        // FIXME prevents crash on shutdown, but we should migrate to a global functions object owned by the shared context.
        glWaitSync((GLsync)fence, 0, GL_TIMEOUT_IGNORED);
        glDeleteSync((GLsync)fence);
    }
    destroyTexture(textureAndFence.first);
}

uint32_t TextureCache::createTexture(const QSize& size, bool generateMips) {
    // Need a new texture
    uint32_t newTexture;
    glGenTextures(1, &newTexture);
    ++_allTextureCount;
    _textureSizes[newTexture] = { size, generateMips };
    _totalTextureUsage += getMemoryForSize(size, generateMips);
    glBindTexture(GL_TEXTURE_2D, newTexture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, generateMips ? GL_LINEAR_MIPMAP_LINEAR : GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_R, GL_CLAMP_TO_EDGE);
    auto backendApi = hifi::properties::getGraphicsAPI();
    if (backendApi != hifi::properties::GraphicsAPI::GLES32) {
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_LOD_BIAS, -0.2f);
    }
    if (generateMips) {
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAX_ANISOTROPY_EXT, 8.0f);
    }
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, size.width(), size.height(), 0, GL_RGBA, GL_UNSIGNED_BYTE, 0);
    return newTexture;
}

void TextureCache::recycle() {
    // First handle any global returns
    ValueList returnedTextures;
    returnedTextures.swap(_returnedTextures);

    for (auto textureAndFence : returnedTextures) {
        GLuint texture = textureAndFence.first;
        const auto info = _textureSizes[texture];
        auto sizeKey = uvec2ToUint64(info.size, info.generateMips);
        // Textures can be returned after all surfaces of the given size have been destroyed,
        // in which case we just destroy the texture
        if (!_textures.count(sizeKey)) {
            destroy(textureAndFence);
            continue;
        }
        _textures[sizeKey].returnedTextures.push_back(textureAndFence);
    }
}
