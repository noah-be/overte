//
// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
//

#import "BootstrapViewController.h"

#import <Metal/Metal.h>
#import <MetalKit/MetalKit.h>

@interface BootstrapViewController () <MTKViewDelegate>
@property(nonatomic, strong) MTKView* metalView;
@property(nonatomic, strong) id<MTLCommandQueue> commandQueue;
@property(nonatomic, strong) UILabel* statusLabel;
@end

@implementation BootstrapViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.blackColor;

    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    self.metalView = [[MTKView alloc] initWithFrame:CGRectZero device:device];
    self.metalView.translatesAutoresizingMaskIntoConstraints = NO;
    self.metalView.delegate = self;
    self.metalView.preferredFramesPerSecond = 60;
    self.metalView.colorPixelFormat = MTLPixelFormatBGRA8Unorm_sRGB;
    self.metalView.clearColor = MTLClearColorMake(0.015, 0.035, 0.075, 1.0);
    self.commandQueue = [device newCommandQueue];
    [self.view addSubview:self.metalView];

    self.statusLabel = [[UILabel alloc] initWithFrame:CGRectZero];
    self.statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    self.statusLabel.textAlignment = NSTextAlignmentCenter;
    self.statusLabel.numberOfLines = 0;
    self.statusLabel.textColor = UIColor.whiteColor;
    self.statusLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleTitle2];
    self.statusLabel.adjustsFontForContentSizeCategory = YES;
    self.statusLabel.text = device
        ? @"Overte iOS Bootstrap\nMetal ready"
        : @"Overte iOS Bootstrap\nMetal unavailable";
    [self.view addSubview:self.statusLabel];

    UILayoutGuide* safeArea = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [self.metalView.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [self.metalView.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [self.metalView.topAnchor constraintEqualToAnchor:self.view.topAnchor],
        [self.metalView.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor],
        [self.statusLabel.leadingAnchor constraintGreaterThanOrEqualToAnchor:safeArea.leadingAnchor constant:24.0],
        [self.statusLabel.trailingAnchor constraintLessThanOrEqualToAnchor:safeArea.trailingAnchor constant:-24.0],
        [self.statusLabel.centerXAnchor constraintEqualToAnchor:safeArea.centerXAnchor],
        [self.statusLabel.centerYAnchor constraintEqualToAnchor:safeArea.centerYAnchor],
    ]];
}

- (void)mtkView:(MTKView*)view drawableSizeWillChange:(CGSize)size {
    (void)view;
    (void)size;
}

- (void)drawInMTKView:(MTKView*)view {
    id<CAMetalDrawable> drawable = view.currentDrawable;
    MTLRenderPassDescriptor* pass = view.currentRenderPassDescriptor;
    if (drawable == nil || pass == nil || self.commandQueue == nil) {
        return;
    }

    id<MTLCommandBuffer> commandBuffer = [self.commandQueue commandBuffer];
    id<MTLRenderCommandEncoder> encoder = [commandBuffer renderCommandEncoderWithDescriptor:pass];
    [encoder endEncoding];
    [commandBuffer presentDrawable:drawable];
    [commandBuffer commit];
}

- (UIInterfaceOrientationMask)supportedInterfaceOrientations {
    return UIInterfaceOrientationMaskAll;
}

@end
