//
// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
//

#import "BootstrapViewController.h"

#import <Metal/Metal.h>
#import <MetalKit/MetalKit.h>

#import "PlatformProbe.h"

@interface BootstrapViewController () <MTKViewDelegate>
@property(nonatomic, strong) MTKView* metalView;
@property(nonatomic, strong) id<MTLCommandQueue> commandQueue;
@property(nonatomic, strong) id<MTLRenderPipelineState> pipelineState;
@property(nonatomic, strong) UILabel* statusLabel;
@property(nonatomic, strong) UILabel* touchStatusLabel;
@property(nonatomic, strong) PlatformProbe* platformProbe;
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

    NSError* pipelineError = nil;
    id<MTLLibrary> library = [device newDefaultLibrary];
    id<MTLFunction> vertexFunction = [library newFunctionWithName:@"overteBootstrapVertex"];
    id<MTLFunction> fragmentFunction = [library newFunctionWithName:@"overteBootstrapFragment"];
    MTLRenderPipelineDescriptor* pipelineDescriptor = [[MTLRenderPipelineDescriptor alloc] init];
    pipelineDescriptor.vertexFunction = vertexFunction;
    pipelineDescriptor.fragmentFunction = fragmentFunction;
    pipelineDescriptor.colorAttachments[0].pixelFormat = self.metalView.colorPixelFormat;
    self.pipelineState = [device newRenderPipelineStateWithDescriptor:pipelineDescriptor
                                                                 error:&pipelineError];
    [self.view addSubview:self.metalView];

    self.statusLabel = [[UILabel alloc] initWithFrame:CGRectZero];
    self.statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    self.statusLabel.textAlignment = NSTextAlignmentCenter;
    self.statusLabel.numberOfLines = 0;
    self.statusLabel.textColor = UIColor.whiteColor;
    self.statusLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleTitle2];
    self.statusLabel.adjustsFontForContentSizeCategory = YES;
    self.statusLabel.accessibilityIdentifier = @"overte.bootstrap.status";
    self.statusLabel.text = self.pipelineState
        ? @"Overte iOS Bootstrap\nMetal pipeline ready"
        : [NSString stringWithFormat:@"Overte iOS Bootstrap\nMetal unavailable: %@",
                                     pipelineError.localizedDescription ?: @"no device"];
    [self.view addSubview:self.statusLabel];

    self.touchStatusLabel = [[UILabel alloc] initWithFrame:CGRectZero];
    self.touchStatusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    self.touchStatusLabel.textAlignment = NSTextAlignmentCenter;
    self.touchStatusLabel.textColor = [UIColor colorWithWhite:1.0 alpha:0.75];
    self.touchStatusLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];
    self.touchStatusLabel.adjustsFontForContentSizeCategory = YES;
    self.touchStatusLabel.accessibilityIdentifier = @"overte.bootstrap.touch-status";
    self.touchStatusLabel.text = UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad
        ? @"iPad layout · drag to validate touch input"
        : @"iPhone layout · drag to validate touch input";
    [self.view addSubview:self.touchStatusLabel];

    self.platformProbe = [[PlatformProbe alloc] init];
    NSString* motionStatus = self.platformProbe.deviceMotionAvailable ? @"motion ready" : @"motion unavailable";
    self.statusLabel.accessibilityHint = [NSString stringWithFormat:@"%@; app support at %@",
                                          motionStatus, self.platformProbe.applicationSupportPath];
    __weak BootstrapViewController* weakSelf = self;
    [self.platformProbe startNetworkMonitoringWithHandler:^(BOOL reachable) {
        BootstrapViewController* strongSelf = weakSelf;
        if (strongSelf != nil) {
            strongSelf.view.accessibilityValue = reachable ? @"Network reachable" : @"Network unavailable";
        }
    }];

    UIPanGestureRecognizer* pan = [[UIPanGestureRecognizer alloc]
        initWithTarget:self action:@selector(handlePan:)];
    [self.metalView addGestureRecognizer:pan];
    UITapGestureRecognizer* tap = [[UITapGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleTap:)];
    [self.metalView addGestureRecognizer:tap];

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
        [self.touchStatusLabel.leadingAnchor constraintGreaterThanOrEqualToAnchor:safeArea.leadingAnchor constant:16.0],
        [self.touchStatusLabel.trailingAnchor constraintLessThanOrEqualToAnchor:safeArea.trailingAnchor constant:-16.0],
        [self.touchStatusLabel.centerXAnchor constraintEqualToAnchor:safeArea.centerXAnchor],
        [self.touchStatusLabel.bottomAnchor constraintEqualToAnchor:safeArea.bottomAnchor constant:-16.0],
    ]];
}

- (void)dealloc {
    [self.platformProbe stop];
}

- (void)handlePan:(UIPanGestureRecognizer*)gesture {
    CGPoint translation = [gesture translationInView:self.metalView];
    CGPoint velocity = [gesture velocityInView:self.metalView];
    self.touchStatusLabel.text = [NSString stringWithFormat:
        @"Touch pan Δ %.0f, %.0f · velocity %.0f, %.0f",
        translation.x, translation.y, velocity.x, velocity.y];
}

- (void)handleTap:(UITapGestureRecognizer*)gesture {
    CGPoint location = [gesture locationInView:self.metalView];
    self.touchStatusLabel.text = [NSString stringWithFormat:
        @"Touch tap %.0f, %.0f", location.x, location.y];
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
    if (self.pipelineState != nil) {
        [encoder setRenderPipelineState:self.pipelineState];
        [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    }
    [encoder endEncoding];
    [commandBuffer presentDrawable:drawable];
    [commandBuffer commit];
}

- (UIInterfaceOrientationMask)supportedInterfaceOrientations {
    return UIInterfaceOrientationMaskAll;
}

@end
