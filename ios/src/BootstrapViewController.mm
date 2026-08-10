//
// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
//

#import "BootstrapViewController.h"

#import <Metal/Metal.h>
#import <MetalKit/MetalKit.h>

#import "PlatformProbe.h"
#import "SceneDelegate.h"

#include "OverteAddress.h"
#include "PendingDeepLinkStore.h"

@interface BootstrapViewController () <MTKViewDelegate, UITextFieldDelegate>
@property(nonatomic, strong) MTKView* metalView;
@property(nonatomic, strong) id<MTLCommandQueue> commandQueue;
@property(nonatomic, strong) id<MTLRenderPipelineState> pipelineState;
@property(nonatomic, strong) UILabel* statusLabel;
@property(nonatomic, strong) UILabel* touchStatusLabel;
@property(nonatomic, strong) UITextField* addressField;
@property(nonatomic, strong) UIButton* connectButton;
@property(nonatomic, strong) UILabel* connectionStatusLabel;
@property(nonatomic, strong) NSURLSessionDataTask* directoryTask;
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
    self.metalView.accessibilityIdentifier = @"overte.bootstrap.metal-view";
    self.metalView.isAccessibilityElement = YES;
    self.metalView.accessibilityLabel = @"Overte three dimensional view";
    self.metalView.accessibilityHint = @"Use touch or pointer input to inspect the bootstrap scene.";
    self.metalView.colorPixelFormat = MTLPixelFormatBGRA8Unorm_sRGB;
    self.metalView.clearColor = MTLClearColorMake(0.015, 0.035, 0.075, 1.0);
    self.commandQueue = [device newCommandQueue];

    NSError* pipelineError = nil;
    id<MTLLibrary> library = [device newDefaultLibrary];
    id<MTLFunction> vertexFunction = [library newFunctionWithName:@"overteBootstrapVertex"];
    id<MTLFunction> fragmentFunction = [library newFunctionWithName:@"overteBootstrapFragment"];
    if (device == nil || library == nil || vertexFunction == nil || fragmentFunction == nil) {
        pipelineError = [NSError errorWithDomain:@"org.overte.interface.metal"
                                             code:1
                                         userInfo:@{
            NSLocalizedDescriptionKey: @"default Metal shader library is unavailable"
        }];
    } else {
        MTLRenderPipelineDescriptor* pipelineDescriptor = [[MTLRenderPipelineDescriptor alloc] init];
        pipelineDescriptor.vertexFunction = vertexFunction;
        pipelineDescriptor.fragmentFunction = fragmentFunction;
        pipelineDescriptor.colorAttachments[0].pixelFormat = self.metalView.colorPixelFormat;
        self.pipelineState = [device newRenderPipelineStateWithDescriptor:pipelineDescriptor
                                                                     error:&pipelineError];
    }
    [self.view addSubview:self.metalView];

    self.statusLabel = [[UILabel alloc] initWithFrame:CGRectZero];
    self.statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    self.statusLabel.textAlignment = NSTextAlignmentCenter;
    self.statusLabel.numberOfLines = 0;
    self.statusLabel.textColor = UIColor.whiteColor;
    self.statusLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleTitle2];
    self.statusLabel.adjustsFontForContentSizeCategory = YES;
    self.statusLabel.accessibilityIdentifier = @"overte.bootstrap.status";
    self.statusLabel.accessibilityTraits = UIAccessibilityTraitHeader;
    self.statusLabel.text = self.pipelineState
        ? @"Overte iPad Preview\nMetal pipeline ready"
        : [NSString stringWithFormat:@"Overte iPad Preview\nMetal unavailable: %@",
                                     pipelineError.localizedDescription ?: @"no device"];
    [self.view addSubview:self.statusLabel];

    self.touchStatusLabel = [[UILabel alloc] initWithFrame:CGRectZero];
    self.touchStatusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    self.touchStatusLabel.textAlignment = NSTextAlignmentCenter;
    self.touchStatusLabel.textColor = [UIColor colorWithWhite:1.0 alpha:0.75];
    self.touchStatusLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];
    self.touchStatusLabel.adjustsFontForContentSizeCategory = YES;
    self.touchStatusLabel.accessibilityIdentifier = @"overte.bootstrap.touch-status";
    self.touchStatusLabel.accessibilityLabel = @"Input status";
    self.touchStatusLabel.text = UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad
        ? @"iPad layout · drag to validate touch input"
        : @"iPhone layout · drag to validate touch input";
    [self.view addSubview:self.touchStatusLabel];

    self.addressField = [[UITextField alloc] initWithFrame:CGRectZero];
    self.addressField.translatesAutoresizingMaskIntoConstraints = NO;
    self.addressField.backgroundColor = [UIColor colorWithWhite:1.0 alpha:0.94];
    self.addressField.textColor = UIColor.blackColor;
    self.addressField.borderStyle = UITextBorderStyleRoundedRect;
    self.addressField.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    self.addressField.adjustsFontForContentSizeCategory = YES;
    self.addressField.autocapitalizationType = UITextAutocapitalizationTypeNone;
    self.addressField.autocorrectionType = UITextAutocorrectionTypeNo;
    self.addressField.keyboardType = UIKeyboardTypeURL;
    self.addressField.returnKeyType = UIReturnKeyGo;
    self.addressField.clearButtonMode = UITextFieldViewModeWhileEditing;
    self.addressField.placeholder = @"Overte place or hifi:// address";
    self.addressField.accessibilityIdentifier = @"overte.preview.address";
    self.addressField.delegate = self;
    NSString* savedAddress = [NSUserDefaults.standardUserDefaults stringForKey:@"lastOverteAddress"];
    self.addressField.text = savedAddress.length > 0 ? savedAddress : @"overte_hub";

    self.connectButton = [UIButton buttonWithType:UIButtonTypeSystem];
    self.connectButton.translatesAutoresizingMaskIntoConstraints = NO;
    [self.connectButton setTitle:@"Check domain" forState:UIControlStateNormal];
    self.connectButton.titleLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    self.connectButton.titleLabel.adjustsFontForContentSizeCategory = YES;
    self.connectButton.backgroundColor = [UIColor colorWithRed:0.20 green:0.55 blue:0.95 alpha:0.95];
    [self.connectButton setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    self.connectButton.layer.cornerRadius = 8.0;
    self.connectButton.contentEdgeInsets = UIEdgeInsetsMake(10.0, 14.0, 10.0, 14.0);
    self.connectButton.accessibilityIdentifier = @"overte.preview.check-domain";
    [self.connectButton addTarget:self action:@selector(checkDomain:) forControlEvents:UIControlEventTouchUpInside];

    UIStackView* inputRow = [[UIStackView alloc] initWithArrangedSubviews:@[
        self.addressField, self.connectButton
    ]];
    inputRow.translatesAutoresizingMaskIntoConstraints = NO;
    inputRow.axis = UILayoutConstraintAxisHorizontal;
    inputRow.alignment = UIStackViewAlignmentFill;
    inputRow.spacing = 10.0;

    self.connectionStatusLabel = [[UILabel alloc] initWithFrame:CGRectZero];
    self.connectionStatusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    self.connectionStatusLabel.textAlignment = NSTextAlignmentCenter;
    self.connectionStatusLabel.numberOfLines = 0;
    self.connectionStatusLabel.textColor = [UIColor colorWithWhite:1.0 alpha:0.9];
    self.connectionStatusLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];
    self.connectionStatusLabel.adjustsFontForContentSizeCategory = YES;
    self.connectionStatusLabel.text = @"Resolve a live Overte place through the directory service.";
    self.connectionStatusLabel.accessibilityIdentifier = @"overte.preview.connection-status";

    UIStackView* connectionStack = [[UIStackView alloc] initWithArrangedSubviews:@[
        inputRow, self.connectionStatusLabel
    ]];
    connectionStack.translatesAutoresizingMaskIntoConstraints = NO;
    connectionStack.axis = UILayoutConstraintAxisVertical;
    connectionStack.alignment = UIStackViewAlignmentFill;
    connectionStack.spacing = 8.0;
    [self.view addSubview:connectionStack];

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

    [[NSNotificationCenter defaultCenter]
        addObserver:self
           selector:@selector(openURLReceived:)
               name:OverteOpenURLNotification
             object:nil];

    UIPanGestureRecognizer* pan = [[UIPanGestureRecognizer alloc]
        initWithTarget:self action:@selector(handlePan:)];
    [self.metalView addGestureRecognizer:pan];
    UITapGestureRecognizer* tap = [[UITapGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleTap:)];
    [self.metalView addGestureRecognizer:tap];
    if (@available(iOS 13.0, *)) {
        UIHoverGestureRecognizer* hover = [[UIHoverGestureRecognizer alloc]
            initWithTarget:self action:@selector(handleHover:)];
        [self.metalView addGestureRecognizer:hover];
    }

    [[NSNotificationCenter defaultCenter]
        addObserver:self
           selector:@selector(accessibilitySettingsDidChange:)
               name:UIAccessibilityReduceMotionStatusDidChangeNotification
             object:nil];
    [self updateAccessibilitySettings];

    UILayoutGuide* safeArea = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [self.metalView.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [self.metalView.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [self.metalView.topAnchor constraintEqualToAnchor:self.view.topAnchor],
        [self.metalView.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor],
        [self.statusLabel.leadingAnchor constraintGreaterThanOrEqualToAnchor:safeArea.leadingAnchor constant:24.0],
        [self.statusLabel.trailingAnchor constraintLessThanOrEqualToAnchor:safeArea.trailingAnchor constant:-24.0],
        [self.statusLabel.centerXAnchor constraintEqualToAnchor:safeArea.centerXAnchor],
        [self.statusLabel.centerYAnchor constraintEqualToAnchor:safeArea.centerYAnchor constant:-80.0],
        [connectionStack.leadingAnchor constraintGreaterThanOrEqualToAnchor:safeArea.leadingAnchor constant:20.0],
        [connectionStack.trailingAnchor constraintLessThanOrEqualToAnchor:safeArea.trailingAnchor constant:-20.0],
        [connectionStack.centerXAnchor constraintEqualToAnchor:safeArea.centerXAnchor],
        [connectionStack.widthAnchor constraintLessThanOrEqualToConstant:640.0],
        [connectionStack.bottomAnchor constraintEqualToAnchor:self.touchStatusLabel.topAnchor constant:-22.0],
        [self.connectButton.widthAnchor constraintGreaterThanOrEqualToConstant:130.0],
        [self.touchStatusLabel.leadingAnchor constraintGreaterThanOrEqualToAnchor:safeArea.leadingAnchor constant:16.0],
        [self.touchStatusLabel.trailingAnchor constraintLessThanOrEqualToAnchor:safeArea.trailingAnchor constant:-16.0],
        [self.touchStatusLabel.centerXAnchor constraintEqualToAnchor:safeArea.centerXAnchor],
        [self.touchStatusLabel.bottomAnchor constraintEqualToAnchor:safeArea.bottomAnchor constant:-16.0],
    ]];

    [self drainPendingDeepLinks];
}

- (void)dealloc {
    [self.directoryTask cancel];
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    [self.platformProbe stop];
}

- (BOOL)textFieldShouldReturn:(UITextField*)textField {
    [textField resignFirstResponder];
    [self checkDomain:self.connectButton];
    return YES;
}

- (void)openURLReceived:(NSNotification*)notification {
    (void)notification;
    [self drainPendingDeepLinks];
}

- (void)drainPendingDeepLinks {
    auto addresses = overte::ios::PendingDeepLinkStore::instance().takeAll();
    if (addresses.empty()) {
        return;
    }
    NSString* address = [NSString stringWithUTF8String:addresses.back().c_str()];
    if (address != nil) {
        self.addressField.text = address;
        [self checkDomain:self.connectButton];
    }
}

- (void)setConnectionMessage:(NSString*)message error:(BOOL)isError {
    self.connectionStatusLabel.text = message;
    self.connectionStatusLabel.textColor = isError
        ? [UIColor colorWithRed:1.0 green:0.55 blue:0.50 alpha:1.0]
        : [UIColor colorWithRed:0.55 green:1.0 blue:0.72 alpha:1.0];
    UIAccessibilityPostNotification(UIAccessibilityAnnouncementNotification, message);
}

- (void)checkDomain:(id)sender {
    (void)sender;
    [self.addressField resignFirstResponder];
    const char* encodedAddress = self.addressField.text.UTF8String;
    auto parsed = overte::ios::parseOverteAddress(encodedAddress != nullptr ? encodedAddress : "");
    if (!parsed) {
        [self setConnectionMessage:[NSString stringWithUTF8String:parsed.error.c_str()] error:YES];
        return;
    }

    NSString* normalized = [NSString stringWithUTF8String:parsed.normalized.c_str()];
    [NSUserDefaults.standardUserDefaults setObject:normalized forKey:@"lastOverteAddress"];
    self.addressField.text = normalized;
    if (parsed.kind == overte::ios::AddressKind::Network) {
        NSString* message = [NSString stringWithFormat:
            @"Direct domain parsed: %s:%u · protocol connection is the next integration stage.",
            parsed.host.c_str(), parsed.port];
        [self setConnectionMessage:message error:NO];
        return;
    }

    NSString* place = [NSString stringWithUTF8String:parsed.host.c_str()];
    NSString* escapedPlace = [place stringByAddingPercentEncodingWithAllowedCharacters:
        NSCharacterSet.URLPathAllowedCharacterSet];
    NSString* endpoint = [NSString stringWithFormat:
        @"https://mv.overte.org/server/api/v1/places/%@", escapedPlace];
    NSURL* url = [NSURL URLWithString:endpoint];
    if (url == nil) {
        [self setConnectionMessage:@"Could not construct the Overte directory request." error:YES];
        return;
    }

    [self.directoryTask cancel];
    self.connectButton.enabled = NO;
    self.connectionStatusLabel.textColor = [UIColor colorWithWhite:1.0 alpha:0.9];
    self.connectionStatusLabel.text = [NSString stringWithFormat:@"Resolving %@…", place];
    NSMutableURLRequest* request = [NSMutableURLRequest requestWithURL:url];
    request.timeoutInterval = 12.0;
    [request setValue:@"Mozilla/5.0 (OverteInterface iOS Preview)" forHTTPHeaderField:@"User-Agent"];

    __weak BootstrapViewController* weakSelf = self;
    self.directoryTask = [NSURLSession.sharedSession
        dataTaskWithRequest:request
          completionHandler:^(NSData* data, NSURLResponse* response, NSError* error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            BootstrapViewController* strongSelf = weakSelf;
            if (strongSelf == nil) {
                return;
            }
            strongSelf.connectButton.enabled = YES;
            NSHTTPURLResponse* httpResponse = [response isKindOfClass:NSHTTPURLResponse.class]
                ? (NSHTTPURLResponse*)response : nil;
            if (error != nil || httpResponse.statusCode != 200 || data == nil) {
                NSString* detail = error.localizedDescription ?: [NSString stringWithFormat:
                    @"HTTP %ld", (long)httpResponse.statusCode];
                [strongSelf setConnectionMessage:[NSString stringWithFormat:
                    @"Directory lookup failed: %@", detail] error:YES];
                return;
            }

            NSError* jsonError = nil;
            NSDictionary* root = [NSJSONSerialization JSONObjectWithData:data options:0 error:&jsonError];
            NSDictionary* placeData = [root[@"data"] isKindOfClass:NSDictionary.class]
                ? root[@"data"][@"place"] : nil;
            NSDictionary* domain = [placeData[@"domain"] isKindOfClass:NSDictionary.class]
                ? placeData[@"domain"] : nil;
            NSString* address = [placeData[@"address"] isKindOfClass:NSString.class]
                ? placeData[@"address"] : nil;
            NSString* host = [domain[@"network_address"] isKindOfClass:NSString.class]
                ? domain[@"network_address"] : nil;
            NSNumber* port = [domain[@"network_port"] isKindOfClass:NSNumber.class]
                ? domain[@"network_port"] : nil;
            NSNumber* active = [domain[@"active"] isKindOfClass:NSNumber.class]
                ? domain[@"active"] : nil;
            NSNumber* attendance = [placeData[@"current_attendance"] isKindOfClass:NSNumber.class]
                ? placeData[@"current_attendance"] : @0;
            if (jsonError != nil || domain == nil || host.length == 0 || port == nil || address.length == 0) {
                [strongSelf setConnectionMessage:@"The directory returned an incomplete place record." error:YES];
                return;
            }

            NSString* state = active.boolValue ? @"active" : @"offline";
            NSString* message = [NSString stringWithFormat:
                @"%@ is %@ · %@:%@ · %@ present\nResolved location: %@",
                place, state, host, port, attendance, address];
            [strongSelf setConnectionMessage:message error:!active.boolValue];
        });
    }];
    [self.directoryTask resume];
}

- (void)handlePan:(UIPanGestureRecognizer*)gesture {
    CGPoint translation = [gesture translationInView:self.metalView];
    CGPoint velocity = [gesture velocityInView:self.metalView];
    self.touchStatusLabel.text = [NSString stringWithFormat:
        @"Touch pan Δ %.0f, %.0f · velocity %.0f, %.0f",
        translation.x, translation.y, velocity.x, velocity.y];
    if (gesture.state == UIGestureRecognizerStateEnded) {
        UIAccessibilityPostNotification(UIAccessibilityAnnouncementNotification,
                                        self.touchStatusLabel.text);
    }
}

- (void)handleTap:(UITapGestureRecognizer*)gesture {
    CGPoint location = [gesture locationInView:self.metalView];
    self.touchStatusLabel.text = [NSString stringWithFormat:
        @"Touch tap %.0f, %.0f", location.x, location.y];
    UIAccessibilityPostNotification(UIAccessibilityAnnouncementNotification,
                                    self.touchStatusLabel.text);
}

- (void)handleHover:(UIHoverGestureRecognizer*)gesture API_AVAILABLE(ios(13.0)) {
    CGPoint location = [gesture locationInView:self.metalView];
    self.touchStatusLabel.text = [NSString stringWithFormat:
        @"Pointer hover %.0f, %.0f", location.x, location.y];
}

- (void)accessibilitySettingsDidChange:(NSNotification*)notification {
    (void)notification;
    [self updateAccessibilitySettings];
}

- (void)updateAccessibilitySettings {
    self.metalView.preferredFramesPerSecond = UIAccessibilityIsReduceMotionEnabled() ? 30 : 60;
    self.view.accessibilityIdentifier = UIAccessibilityIsReduceMotionEnabled()
        ? @"overte.bootstrap.reduce-motion"
        : @"overte.bootstrap.standard-motion";
}

- (void)viewWillTransitionToSize:(CGSize)size
       withTransitionCoordinator:(id<UIViewControllerTransitionCoordinator>)coordinator {
    [super viewWillTransitionToSize:size withTransitionCoordinator:coordinator];
    [coordinator animateAlongsideTransition:nil completion:^(id<UIViewControllerTransitionCoordinatorContext> context) {
        (void)context;
        self.touchStatusLabel.accessibilityValue = [NSString stringWithFormat:
            @"Viewport %.0f by %.0f points", size.width, size.height];
    }];
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
