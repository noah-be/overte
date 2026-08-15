// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#import <Foundation/Foundation.h>
#import <OpenGL/OpenGL.h>
#import <OpenGL/gl3.h>

namespace {

NSString* glString(GLenum name) {
    const auto* value = glGetString(name);
    return value ? [NSString stringWithUTF8String:reinterpret_cast<const char*>(value)] : @"";
}

}  // namespace

int main() {
    @autoreleasepool {
        CGLPixelFormatAttribute attributes[] = {
            kCGLPFAOpenGLProfile,
            // Apple's modern Core selector is named 3.2 even when the
            // selected renderer exposes the maximum macOS 4.1 context.
            static_cast<CGLPixelFormatAttribute>(kCGLOGLPVersion_3_2_Core),
            kCGLPFAAccelerated,
            kCGLPFANoRecovery,
            static_cast<CGLPixelFormatAttribute>(0),
        };
        CGLPixelFormatObj pixelFormat { nullptr };
        GLint pixelFormatCount { 0 };
        const auto chooseError = CGLChoosePixelFormat(attributes, &pixelFormat, &pixelFormatCount);
        CGLContextObj context { nullptr };
        const auto contextError = chooseError == kCGLNoError && pixelFormat
            ? CGLCreateContext(pixelFormat, nullptr, &context)
            : chooseError;

        GLint accelerated { 0 };
        GLint rendererID { 0 };
        GLint virtualScreens { 0 };
        if (pixelFormat) {
            CGLDescribePixelFormat(pixelFormat, 0, kCGLPFAAccelerated, &accelerated);
            CGLDescribePixelFormat(pixelFormat, 0, kCGLPFARendererID, &rendererID);
            CGLDescribePixelFormat(pixelFormat, 0, kCGLPFAVirtualScreenCount, &virtualScreens);
        }

        NSMutableDictionary* result = [@{
            @"schema_version": @1,
            @"pixel_format_count": @(pixelFormatCount),
            @"choose_error": @(chooseError),
            @"context_error": @(contextError),
            @"context_created": @(context != nullptr),
            @"accelerated": @(accelerated != 0),
            @"renderer_id": @(rendererID),
            @"virtual_screen_count": @(virtualScreens),
        } mutableCopy];

        if (context) {
            CGLSetCurrentContext(context);
            result[@"gl_vendor"] = glString(GL_VENDOR);
            result[@"gl_renderer"] = glString(GL_RENDERER);
            result[@"gl_version"] = glString(GL_VERSION);
            result[@"glsl_version"] = glString(GL_SHADING_LANGUAGE_VERSION);
            CGLSetCurrentContext(nullptr);
            CGLReleaseContext(context);
        }
        if (pixelFormat) {
            CGLReleasePixelFormat(pixelFormat);
        }

        NSData* data = [NSJSONSerialization dataWithJSONObject:result options:0 error:nil];
        [[NSFileHandle fileHandleWithStandardOutput] writeData:data];
        [[NSFileHandle fileHandleWithStandardOutput] writeData:[@"\n" dataUsingEncoding:NSUTF8StringEncoding]];
        return 0;
    }
}
