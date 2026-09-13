//
//  Created by Bradley Austin Davis on 2016/08/07
//  Adapted for Vulkan in 2022-2025 by dr Karol Suprynowicz.
//  Copyright 2013-2018 High Fidelity, Inc.
//  Copyright 2023-2025 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//  SPDX-License-Identifier: Apache-2.0
//

#include "VKFramebuffer.h"
#include "VKBackend.h"
#include "VKTexture.h"
#include "VKShared.h"

void gpu::vk::VKFramebuffer::update() {
    auto backend = _backend.lock();
    auto& recycler = backend->getContext().recycler;
    // Earlier commands in this frame can still reference the old framebuffer
    // and its views. The backend drains this recycler only after the previous
    // submission's fence, before recording the next frame.
    if (vkFramebuffer != VK_NULL_HANDLE) {
        recycler.trashVkFramebuffer(vkFramebuffer);
        vkFramebuffer = VK_NULL_HANDLE;
    }
    if (vkRenderPass != VK_NULL_HANDLE) {
        recycler.trashVkRenderPass(vkRenderPass);
        vkRenderPass = VK_NULL_HANDLE;
    }
    for (const auto& attachment : attachments) {
        recycler.trashVkImageView(attachment.view);
    }
    attachments.clear();

    // A framebuffer is one complete attachment set. Rebuilding only the side
    // whose stamp changed either drops unchanged depth or appends a second
    // depth attachment. Rebuild both sides, including explicit removals.
    auto appendSurface = [&](const TexturePointer& surface, uint32_t subresource,
                             VkImageUsageFlags usage) {
        Q_ASSERT(TextureUsageType::RENDERBUFFER == surface->getUsageType());
        auto* texture = backend->syncGPUObject(surface);
        Q_ASSERT(texture);
        if (!texture) {
            return;
        }
        VKAttachmentCreateInfo attachmentCI {};
        attachmentCI.width = texture->_gpuObject.getWidth();
        attachmentCI.height = texture->_gpuObject.getHeight();
        attachmentCI.format = gpu::vk::evalTexelFormatInternal(
            texture->_gpuObject.getTexelFormat(), backend->getContext());
        attachmentCI.usage = usage;
        attachmentCI.imageSampleCount = VK_SAMPLE_COUNT_1_BIT;
        if (texture->_target == VK_IMAGE_VIEW_TYPE_2D) {
            attachmentCI.layerCount = 1;
            addAttachment(attachmentCI, texture);
        } else if (texture->_target == VK_IMAGE_VIEW_TYPE_2D_ARRAY) {
            Q_ASSERT(subresource < texture->_gpuObject.getNumSlices());
            attachmentCI.layerCount = texture->_gpuObject.getNumSlices() - subresource;
            addAttachment(attachmentCI, texture, subresource);
        } else {
            Q_ASSERT(false);
        }
    };

    bool lastTextureWasNull = false;
    if (_gpuObject.hasColor()) {
        for (const auto& buffer : _gpuObject.getRenderBuffers()) {
            if (buffer._texture) {
                // Sparse color slots are not supported by this backend.
                Q_ASSERT(!lastTextureWasNull);
                appendSurface(buffer._texture, buffer._subresource,
                              VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT |
                              VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT);
            } else {
                lastTextureWasNull = true;
            }
        }
    }
    const auto& depthSurface = _gpuObject.getDepthStencilBuffer();
    if (_gpuObject.hasDepthStencil() && depthSurface) {
        appendSurface(depthSurface, _gpuObject.getDepthStencilBufferSubresource(),
                      VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT);
    }
    _colorStamps = _gpuObject.getColorStamps();
    _depthStamp = _gpuObject.getDepthStamp();

    // sync() excludes empty framebuffers; depth-only and color-only are valid.
    Q_ASSERT(!attachments.empty());
    if (!attachments.empty()) {
        VK_CHECK_RESULT(createFramebuffer());
    }
}

// From VKS
VkResult gpu::vk::VKFramebuffer::createFramebuffer()
{
    std::vector<VkAttachmentDescription> attachmentDescriptions;
    for (auto& attachment : attachments)
    {
        attachmentDescriptions.push_back(attachment.description);
    };

    // Collect attachment references
    std::vector<VkAttachmentReference> colorReferences;
    VkAttachmentReference depthReference = {};
    bool hasDepth = false;
    bool hasColor = false;

    uint32_t attachmentIndex = 0;

    for (auto& attachment : attachments)
    {
        if (attachment.isDepthStencil())
        {
            // Only one depth attachment allowed
            assert(!hasDepth);
            depthReference.attachment = attachmentIndex;
            depthReference.layout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;
            hasDepth = true;
        }
        else
        {
            colorReferences.push_back({ attachmentIndex, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL });
            hasColor = true;
        }
        attachmentIndex++;
    };

    // Default render pass setup uses only one subpass
    VkSubpassDescription subpass = {};
    subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
    if (hasColor)
    {
        subpass.pColorAttachments = colorReferences.data();
        subpass.colorAttachmentCount = static_cast<uint32_t>(colorReferences.size());
    }
    if (hasDepth)
    {
        subpass.pDepthStencilAttachment = &depthReference;
    }

    // Use subpass dependencies for attachment layout transitions
    //std::array<VkSubpassDependency, 2> dependencies;

    // VKTODO: what are these for?
    /*dependencies[0].srcSubpass = VK_SUBPASS_EXTERNAL;
    dependencies[0].dstSubpass = 0;
    dependencies[0].srcStageMask = VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT;
    dependencies[0].dstStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
    dependencies[0].srcAccessMask = VK_ACCESS_MEMORY_READ_BIT;
    dependencies[0].dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_READ_BIT | VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;
    dependencies[0].dependencyFlags = VK_DEPENDENCY_BY_REGION_BIT;

    dependencies[1].srcSubpass = 0;
    dependencies[1].dstSubpass = VK_SUBPASS_EXTERNAL;
    dependencies[1].srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
    dependencies[1].dstStageMask = VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT;
    dependencies[1].srcAccessMask = VK_ACCESS_COLOR_ATTACHMENT_READ_BIT | VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;
    dependencies[1].dstAccessMask = VK_ACCESS_MEMORY_READ_BIT;
    dependencies[1].dependencyFlags = VK_DEPENDENCY_BY_REGION_BIT;*/

    // Create render pass
    VkRenderPassCreateInfo renderPassInfo = {};
    renderPassInfo.sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO;
    renderPassInfo.pAttachments = attachmentDescriptions.data();
    renderPassInfo.attachmentCount = static_cast<uint32_t>(attachmentDescriptions.size());
    renderPassInfo.subpassCount = 1;
    renderPassInfo.pSubpasses = &subpass;
    // VKTODO
    //renderPassInfo.dependencyCount = 2;
    //renderPassInfo.pDependencies = dependencies.data();
    renderPassInfo.dependencyCount = 0;
    VK_CHECK_RESULT(vkCreateRenderPass(_backend.lock()->_context.device->logicalDevice, &renderPassInfo, nullptr, &vkRenderPass));

    std::vector<VkImageView> attachmentViews;
    for (auto attachment : attachments)
    {
        attachmentViews.push_back(attachment.view);
    }

    // Find. max number of layers across attachments
    uint32_t maxLayers = 0;
    for (auto attachment : attachments)
    {
        if (attachment.subresourceRange.layerCount > maxLayers)
        {
            maxLayers = attachment.subresourceRange.layerCount;
        }
    }

    VkFramebufferCreateInfo framebufferInfo = {};
    framebufferInfo.sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO;
    framebufferInfo.renderPass = vkRenderPass;
    framebufferInfo.pAttachments = attachmentViews.data();
    framebufferInfo.attachmentCount = static_cast<uint32_t>(attachmentViews.size());
    framebufferInfo.width = _gpuObject.getWidth();
    framebufferInfo.height = _gpuObject.getHeight();
    framebufferInfo.layers = maxLayers;
    VK_CHECK_RESULT(vkCreateFramebuffer(_backend.lock()->_context.device->logicalDevice, &framebufferInfo, nullptr, &vkFramebuffer));

    return VK_SUCCESS;
}

//bool gpu::vk::VKFramebuffer::checkStatus(gpu::vk::VKFramebuffer::FramebufferStatus target) const {
    // VKTODO
    /*switch (_status) {
        case GL_FRAMEBUFFER_COMPLETE:
            // Success !
            return true;

        case GL_FRAMEBUFFER_INCOMPLETE_ATTACHMENT:
            qCWarning(gpugllogging) << "GLFramebuffer::syncGPUObject : Framebuffer not valid, GL_FRAMEBUFFER_INCOMPLETE_ATTACHMENT.";
            break;
        case GL_FRAMEBUFFER_INCOMPLETE_MISSING_ATTACHMENT:
            qCWarning(gpugllogging) << "GLFramebuffer::syncGPUObject : Framebuffer not valid, GL_FRAMEBUFFER_INCOMPLETE_MISSING_ATTACHMENT.";
            break;
        case GL_FRAMEBUFFER_UNSUPPORTED:
            qCWarning(gpugllogging) << "GLFramebuffer::syncGPUObject : Framebuffer not valid, GL_FRAMEBUFFER_UNSUPPORTED.";
            break;
#if !defined(USE_GLES)
        case GL_FRAMEBUFFER_INCOMPLETE_DRAW_BUFFER:
            qCWarning(gpugllogging) << "GLFramebuffer::syncGPUObject : Framebuffer not valid, GL_FRAMEBUFFER_INCOMPLETE_DRAW_BUFFER.";
            break;
        case GL_FRAMEBUFFER_INCOMPLETE_READ_BUFFER:
            qCWarning(gpugllogging) << "GLFramebuffer::syncGPUObject : Framebuffer not valid, GL_FRAMEBUFFER_INCOMPLETE_READ_BUFFER.";
            break;
#endif
        default:
            break;
    }
    return false;
*/
//}

gpu::vk::VKFramebuffer::~VKFramebuffer() {
    auto backend = _backend.lock();
    if (backend) {
        auto& recycler = backend->getContext().recycler;  // VKTODO: these sometimes get destroyed after backend was destroyed?
        recycler.trashVkRenderPass(vkRenderPass);
        recycler.trashVkFramebuffer(vkFramebuffer);
        for (auto &attachment : attachments) {
            recycler.trashVkImageView(attachment.view);
        }
        recycler.framebufferDeleted(this);
    } else {
        Q_ASSERT(false);
    }
    //VKTODO
    /*if (_id) {
        auto backend = _backend.lock();
        if (backend) {
            backend->releaseFramebuffer(_id);
        }
    }*/
}

// From VKS
uint32_t gpu::vk::VKFramebuffer::addAttachment(VKAttachmentCreateInfo createinfo, VKTexture *texture, uint32_t subresource) {
    auto *attachmentTexture = dynamic_cast<VKAttachmentTexture*>(texture);
    Q_ASSERT(attachmentTexture);

    FramebufferAttachment attachment {};

    attachment.format = createinfo.format;

    VkImageAspectFlags aspectMask = VK_FLAGS_NONE;

    // Select aspect mask and layout depending on usage

    // Color attachment
    if (createinfo.usage & VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT)
    {
        Q_ASSERT(attachment.format != VK_FORMAT_D24_UNORM_S8_UINT);
        aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
    }

    // Depth (and/or stencil) attachment
    if (createinfo.usage & VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT)
    {
        if (attachment.hasDepth())
        {
            aspectMask = VK_IMAGE_ASPECT_DEPTH_BIT;
        }
        if (attachment.hasStencil())
        {
            aspectMask = aspectMask | VK_IMAGE_ASPECT_STENCIL_BIT;
        }
    }

    assert(aspectMask > 0);

    attachment.image = attachmentTexture->_vkImage;

    attachment.subresourceRange = {};
    attachment.subresourceRange.aspectMask = aspectMask;
    attachment.subresourceRange.baseArrayLayer = subresource;
    attachment.subresourceRange.levelCount = 1;
    attachment.subresourceRange.layerCount = 1; // Even though texture can have multiple layers, we only render to one of them currently.

    VkImageViewCreateInfo imageView = vks::initializers::imageViewCreateInfo();
    imageView.viewType = (createinfo.layerCount == 1) ? VK_IMAGE_VIEW_TYPE_2D : VK_IMAGE_VIEW_TYPE_2D_ARRAY;
    imageView.format = createinfo.format;
    imageView.subresourceRange = attachment.subresourceRange;
    imageView.subresourceRange.aspectMask = attachment.hasDepth() ? VkImageAspectFlags{VK_IMAGE_ASPECT_DEPTH_BIT} : aspectMask;
    imageView.image = attachment.image;
    VK_CHECK_RESULT(vkCreateImageView(_backend.lock()->_context.device->logicalDevice, &imageView, nullptr, &attachment.view));

    // Fill attachment description
    attachment.description = {};
    attachment.description.samples = createinfo.imageSampleCount;
    attachment.description.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
    attachment.description.storeOp = (createinfo.usage & VK_IMAGE_USAGE_SAMPLED_BIT) ? VK_ATTACHMENT_STORE_OP_STORE : VK_ATTACHMENT_STORE_OP_DONT_CARE;
    attachment.description.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
    attachment.description.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
    attachment.description.format = createinfo.format;
    attachment.description.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    // Final layout
    // If not, final layout depends on attachment type
    if (attachment.hasDepth() || attachment.hasStencil())
    {
        attachment.description.finalLayout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL; // VKTODO: this is tricky, because it depends on what the image will be used for
    }
    else
    {
        attachment.description.finalLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL; // VKTODO: this is tricky, because it depends on what the image will be used for
    }

    attachments.push_back(attachment);

    return static_cast<uint32_t>(attachments.size() - 1);
}

// VKTODO: get rid of _backend.lock()

#if 0

using namespace gpu;
using namespace gpu::gl;

VKFramebuffer::~VKFramebuffer() { 
    if (_id) { 
        auto backend = _backend.lock();
        if (backend) {
            backend->releaseFramebuffer(_id);
        }
    } 
}

bool VKFramebuffer::checkStatus(VKenum target) const {
    bool result = false;
    switch (_status) {
    case VK_FRAMEBUFFER_COMPLETE:
        // Success !
        result = true;
        break;
    case VK_FRAMEBUFFER_INCOMPLETE_ATTACHMENT:
        qCDebug(gpu_vk_logging) << "VKFramebuffer::syncGPUObject : Framebuffer not valid, VK_FRAMEBUFFER_INCOMPLETE_ATTACHMENT.";
        break;
    case VK_FRAMEBUFFER_INCOMPLETE_MISSING_ATTACHMENT:
        qCDebug(gpu_vk_logging) << "VKFramebuffer::syncGPUObject : Framebuffer not valid, VK_FRAMEBUFFER_INCOMPLETE_MISSING_ATTACHMENT.";
        break;
    case VK_FRAMEBUFFER_INCOMPLETE_DRAW_BUFFER:
        qCDebug(gpu_vk_logging) << "VKFramebuffer::syncGPUObject : Framebuffer not valid, VK_FRAMEBUFFER_INCOMPLETE_DRAW_BUFFER.";
        break;
    case VK_FRAMEBUFFER_INCOMPLETE_READ_BUFFER:
        qCDebug(gpu_vk_logging) << "VKFramebuffer::syncGPUObject : Framebuffer not valid, VK_FRAMEBUFFER_INCOMPLETE_READ_BUFFER.";
        break;
    case VK_FRAMEBUFFER_UNSUPPORTED:
        qCDebug(gpu_vk_logging) << "VKFramebuffer::syncGPUObject : Framebuffer not valid, VK_FRAMEBUFFER_UNSUPPORTED.";
        break;
    }
    return result;
}
#endif