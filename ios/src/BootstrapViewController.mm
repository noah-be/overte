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
#include "RedactingDiagnostics.h"
#include "../networking/CallbackEpoch.h"
#include "../networking/DirectoryAttempt.h"
#include <chrono>
#import "../networking/BoundedDirectoryRequest.h"
#include "../performance/NativeMetrics.h"
#include "../input/PreviewCamera.h"
#import "../ui/PreviewInputLayout.h"

namespace {
std::uint64_t directoryClock() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
}

@interface BootstrapViewController () <MTKViewDelegate, UITextFieldDelegate>
@property(nonatomic, strong) MTKView* metalView;
@property(nonatomic, strong) id<MTLCommandQueue> commandQueue;
@property(nonatomic, strong) id<MTLRenderPipelineState> pipelineState;
@property(nonatomic, strong) id<MTLRenderPipelineState> scenePipelineState;
@property(nonatomic, strong) id<MTLDepthStencilState> sceneDepthState;
@property(nonatomic, strong) UILabel* statusLabel;
@property(nonatomic, strong) UILabel* touchStatusLabel;
@property(nonatomic, strong) UITextField* addressField;
@property(nonatomic, strong) UIButton* connectButton;
@property(nonatomic, strong) UIStackView* inputRow;
@property(nonatomic, strong) UILabel* connectionStatusLabel;
@property(nonatomic, strong) BoundedDirectoryRequest* directoryTask;
@property(nonatomic, strong) PlatformProbe* platformProbe;
@property(nonatomic) BOOL sceneLoaded;
@property(nonatomic) uint32_t sceneAttendance;
@property(nonatomic) uint32_t sceneSeed;
@end

typedef struct {
    float aspect;
    float yaw;
    float pitch;
    float zoom;
    uint32_t sceneLoaded;
    uint32_t attendance;
    uint32_t domainSeed;
    uint32_t reserved;
} OverteSceneUniforms;

@implementation BootstrapViewController {
    overte::ios::CallbackEpoch _directoryEpoch;
    overte::ios::DirectoryAttempt _directoryAttempt;
    std::string _directoryIntent;
    overte::ios::PreviewCamera _camera;
}

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
    self.metalView.depthStencilPixelFormat = MTLPixelFormatDepth32Float;
    self.metalView.clearColor = MTLClearColorMake(0.015, 0.035, 0.075, 1.0);
    self.commandQueue = [device newCommandQueue];
    self.metalView.accessibilityCustomActions = @[
        [[UIAccessibilityCustomAction alloc] initWithName:@"Look left" target:self selector:@selector(cameraLeft:)],
        [[UIAccessibilityCustomAction alloc] initWithName:@"Look right" target:self selector:@selector(cameraRight:)],
        [[UIAccessibilityCustomAction alloc] initWithName:@"Zoom in" target:self selector:@selector(cameraZoomIn:)],
        [[UIAccessibilityCustomAction alloc] initWithName:@"Zoom out" target:self selector:@selector(cameraZoomOut:)],
        [[UIAccessibilityCustomAction alloc] initWithName:@"Reset camera" target:self selector:@selector(cameraReset:)]
    ];

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
        pipelineDescriptor.depthAttachmentPixelFormat = self.metalView.depthStencilPixelFormat;
        self.pipelineState = [device newRenderPipelineStateWithDescriptor:pipelineDescriptor
                                                                     error:&pipelineError];
        id<MTLFunction> sceneVertexFunction = [library newFunctionWithName:@"overteSceneVertex"];
        if (sceneVertexFunction != nil) {
            pipelineDescriptor.vertexFunction = sceneVertexFunction;
            self.scenePipelineState = [device newRenderPipelineStateWithDescriptor:pipelineDescriptor
                                                                               error:&pipelineError];
            MTLDepthStencilDescriptor* depthDescriptor = [[MTLDepthStencilDescriptor alloc] init];
            depthDescriptor.depthCompareFunction = MTLCompareFunctionLess;
            depthDescriptor.depthWriteEnabled = YES;
            self.sceneDepthState = [device newDepthStencilStateWithDescriptor:depthDescriptor];
        }
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
    [self.addressField addTarget:self action:@selector(directoryAddressEdited:)
               forControlEvents:UIControlEventEditingChanged];
    // Locations can embed private queries/path material. This native preview
    // retains the current input only in memory and removes its old raw history.
    [NSUserDefaults.standardUserDefaults removeObjectForKey:@"lastOverteAddress"];
    self.addressField.text = @"overte_hub";

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
    self.inputRow = inputRow;

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
    self.statusLabel.accessibilityHint = motionStatus;
    __weak BootstrapViewController* weakSelf = self;
    [self.platformProbe startNetworkMonitoringWithHandler:^(BOOL reachable) {
        BootstrapViewController* strongSelf = weakSelf;
        if (strongSelf != nil) {
            strongSelf.view.accessibilityValue = reachable ? @"Network reachable" : @"Network unavailable";
            if (!reachable) { [strongSelf cancelDirectoryLookup]; }
        }
    }];

    [[NSNotificationCenter defaultCenter]
        addObserver:self selector:@selector(directoryApplicationDidEnterBackground:)
        name:UIApplicationDidEnterBackgroundNotification object:nil];
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
    UIPinchGestureRecognizer* pinch = [[UIPinchGestureRecognizer alloc]
        initWithTarget:self action:@selector(handlePinch:)];
    [self.metalView addGestureRecognizer:pinch];
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
    [[NSNotificationCenter defaultCenter]
        addObserver:self selector:@selector(accessibilitySettingsDidChange:)
        name:NSProcessInfoThermalStateDidChangeNotification object:nil];
    [[NSNotificationCenter defaultCenter]
        addObserver:self selector:@selector(accessibilitySettingsDidChange:)
        name:NSProcessInfoPowerStateDidChangeNotification object:nil];
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
    ]];
    installPreviewKeyboardLayout(self.view, self.touchStatusLabel);

    [self drainPendingDeepLinks];
}

- (void)dealloc {
    _directoryAttempt.stop();
    _directoryEpoch.cancel();
    [self.directoryTask cancel];
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    [self.platformProbe stop];
}

- (void)cancelDirectoryLookup {
    _directoryAttempt.cancel();
    _directoryEpoch.cancel();
    if (self.directoryTask != nil) {
        [self.directoryTask cancel];
        self.directoryTask = nil;
        self.connectButton.enabled = YES;
        self.sceneLoaded = NO;
        [self setConnectionMessage:@"Connection interrupted. Check domain to retry." error:YES];
    }
}

- (void)setPreviewForeground:(BOOL)active {
    if (active) { [self loadViewIfNeeded]; }
    _directoryAttempt.visible(active);
    if (active) {
        [self drainPendingDeepLinks];
    } else {
        [self cancelDirectoryLookup];
    }
}

- (void)directoryAddressEdited:(id)sender {
    (void)sender;
    [self cancelDirectoryLookup];
    _directoryIntent.clear(); // explicit edited navigation starts a new budget
    [self.connectButton setTitle:@"Check domain" forState:UIControlStateNormal];
}

- (void)showDirectoryRecovery {
    const bool exhausted = _directoryAttempt.snapshot().state == overte::lifecycle::State::Failed;
    [self.connectButton setTitle:exhausted ? @"Edit address" : @"Retry directory"
                       forState:UIControlStateNormal];
    [self setConnectionMessage:exhausted ? @"Lookup retry limit reached. Edit the address to start again."
                                        : @"Directory lookup failed. Retry directory to continue." error:YES];
}

- (void)directoryApplicationDidEnterBackground:(NSNotification*)notification {
    (void)notification;
    [self setPreviewForeground:NO];
}

- (BOOL)textFieldShouldReturn:(UITextField*)textField {
    [textField resignFirstResponder];
    [self checkDomain:self.connectButton];
    return YES;
}

- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    updatePreviewInputLayout(self.view, self.inputRow);
}

- (NSArray<UIKeyCommand*>*)keyCommands {
    if (self.addressField.isFirstResponder || !self.sceneLoaded) { return @[]; }
    return @[
        [UIKeyCommand keyCommandWithInput:UIKeyInputLeftArrow modifierFlags:0 action:@selector(cameraLeft:)],
        [UIKeyCommand keyCommandWithInput:UIKeyInputRightArrow modifierFlags:0 action:@selector(cameraRight:)],
        [UIKeyCommand keyCommandWithInput:@"+" modifierFlags:0 action:@selector(cameraZoomIn:)],
        [UIKeyCommand keyCommandWithInput:@"-" modifierFlags:0 action:@selector(cameraZoomOut:)],
        [UIKeyCommand keyCommandWithInput:@"0" modifierFlags:0 action:@selector(cameraReset:)]
    ];
}

- (BOOL)cameraLeft:(id)sender {
    (void)sender;
    return self.sceneLoaded && _camera.rotate(-0.15, 0);
}
- (BOOL)cameraRight:(id)sender {
    (void)sender;
    return self.sceneLoaded && _camera.rotate(0.15, 0);
}
- (BOOL)cameraZoomIn:(id)sender {
    (void)sender;
    return self.sceneLoaded && _camera.scale(1.1);
}
- (BOOL)cameraZoomOut:(id)sender {
    (void)sender;
    return self.sceneLoaded && _camera.scale(1.0 / 1.1);
}
- (BOOL)cameraReset:(id)sender {
    (void)sender;
    if (!self.sceneLoaded) { return NO; }
    _camera.reset();
    self.touchStatusLabel.text = @"Camera reset · drag to look · pinch to zoom";
    return YES;
}

- (void)openURLReceived:(NSNotification*)notification {
    (void)notification;
    [self drainPendingDeepLinks];
}

- (void)drainPendingDeepLinks {
    // Cold-launch links remain queued until the real scene is active.
    if (!_directoryAttempt.snapshot().foreground) { return; }
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
    [self cancelDirectoryLookup];
    [self.addressField resignFirstResponder];
    self.sceneLoaded = NO;
    const char* encodedAddress = self.addressField.text.UTF8String;
    auto parsed = overte::ios::parseOverteAddress(encodedAddress != nullptr ? encodedAddress : "");
    if (!parsed) {
        [self setConnectionMessage:[NSString stringWithUTF8String:parsed.error.c_str()] error:YES];
        return;
    }

    NSString* normalized = [NSString stringWithUTF8String:parsed.normalized.c_str()];
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

    const auto state = _directoryAttempt.snapshot().state;
    const bool sameIntent = _directoryIntent == parsed.normalized;
    if (sameIntent && state == overte::lifecycle::State::Failed) {
        [self showDirectoryRecovery];
        return;
    }
    const auto ticket = sameIntent && state == overte::lifecycle::State::Recovery
        ? _directoryAttempt.retry(directoryClock()) : _directoryAttempt.begin(directoryClock());
    if (ticket == 0) {
        [self setConnectionMessage:@"Lookup unavailable until the preview is active." error:YES];
        return;
    }
    _directoryIntent = parsed.normalized;

    self.connectButton.enabled = NO;
    self.connectionStatusLabel.textColor = [UIColor colorWithWhite:1.0 alpha:0.9];
    self.connectionStatusLabel.text = [NSString stringWithFormat:@"Resolving %@…", place];
    auto epoch = _directoryEpoch.begin();
    __weak BootstrapViewController* weakSelf = self;
    self.directoryTask = [[BoundedDirectoryRequest alloc] initWithURL:url completion:^(NSData* data) {
        dispatch_async(dispatch_get_main_queue(), ^{
            BootstrapViewController* strongSelf = weakSelf;
            if (strongSelf == nil || !epoch.current()) {
                return;
            }
            strongSelf.connectButton.enabled = YES;
            strongSelf.directoryTask = nil;
            if (data == nil) {
                strongSelf->_directoryAttempt.failed(ticket);
                overte::ios::logDiagnostic(overte::ios::DiagnosticEvent::DirectoryLookupFailed);
                [strongSelf showDirectoryRecovery];
                return;
            }

            NSError* jsonError = nil;
            id decoded = [NSJSONSerialization JSONObjectWithData:data options:0 error:&jsonError];
            NSDictionary* root = [decoded isKindOfClass:NSDictionary.class] ? decoded : nil;
            NSDictionary* payload = [root[@"data"] isKindOfClass:NSDictionary.class] ? root[@"data"] : nil;
            NSDictionary* placeData = [payload[@"place"] isKindOfClass:NSDictionary.class]
                ? payload[@"place"] : nil;
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
            if (jsonError != nil || domain == nil || host.length == 0 || port == nil ||
                port.doubleValue < 1 || port.doubleValue > 65535 ||
                port.doubleValue != port.unsignedIntegerValue || address.length == 0) {
                overte::ios::logDiagnostic(overte::ios::DiagnosticEvent::DirectoryResponseInvalid);
                strongSelf->_directoryAttempt.failed(ticket);
                [strongSelf showDirectoryRecovery];
                return;
            }
            if (!strongSelf->_directoryAttempt.complete(ticket, directoryClock())) {
                [strongSelf showDirectoryRecovery];
                return;
            }
            [strongSelf.connectButton setTitle:@"Check domain" forState:UIControlStateNormal];

            NSString* state = active.boolValue ? @"active" : @"offline";
            NSString* message = [NSString stringWithFormat:
                @"%@ is %@ · %@:%@ · %@ present\nResolved location: %@",
                place, state, host, port, attendance, address];
            [strongSelf setConnectionMessage:message error:!active.boolValue];
            if (active.boolValue) {
                NSString* domainID = [domain[@"id"] isKindOfClass:NSString.class] ? domain[@"id"] : host;
                strongSelf.sceneAttendance = attendance.unsignedIntValue;
                strongSelf.sceneSeed = (uint32_t)domainID.hash;
                strongSelf.sceneLoaded = YES;
                strongSelf.statusLabel.text = [NSString stringWithFormat:@"%@\nScene preview loaded", place];
                strongSelf.touchStatusLabel.text = @"Drag to look · pinch to zoom · tap to reset";
                strongSelf.metalView.accessibilityLabel = [NSString stringWithFormat:
                    @"Interactive scene preview for %@", place];
                strongSelf.metalView.accessibilityHint = @"Drag to rotate, pinch to zoom, or tap to reset the camera.";
            }
        });
    }];
}

- (void)handlePan:(UIPanGestureRecognizer*)gesture {
    CGPoint translation = [gesture translationInView:self.metalView];
    CGPoint velocity = [gesture velocityInView:self.metalView];
    if (self.sceneLoaded) {
        _camera.rotate(translation.x * 0.005, translation.y * 0.003);
        [gesture setTranslation:CGPointZero inView:self.metalView];
    }
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
    if (self.sceneLoaded) {
        _camera.reset();
        self.touchStatusLabel.text = @"Camera reset · drag to look · pinch to zoom";
        return;
    }
    self.touchStatusLabel.text = [NSString stringWithFormat:
        @"Touch tap %.0f, %.0f", location.x, location.y];
    UIAccessibilityPostNotification(UIAccessibilityAnnouncementNotification,
                                    self.touchStatusLabel.text);
}

- (void)handlePinch:(UIPinchGestureRecognizer*)gesture {
    if (!self.sceneLoaded) {
        return;
    }
    _camera.scale(gesture.scale);
    gesture.scale = 1.0;
    self.touchStatusLabel.text = [NSString stringWithFormat:@"Scene zoom %.0f%%", _camera.zoom * 100.0f];
}

- (void)handleHover:(UIHoverGestureRecognizer*)gesture API_AVAILABLE(ios(13.0)) {
    CGPoint location = [gesture locationInView:self.metalView];
    self.touchStatusLabel.text = [NSString stringWithFormat:
        @"Pointer hover %.0f, %.0f", location.x, location.y];
}

- (void)accessibilitySettingsDidChange:(NSNotification*)notification {
    (void)notification;
    // Process-info notifications need not arrive on the UIKit queue.
    dispatch_async(dispatch_get_main_queue(), ^{ [self updateAccessibilitySettings]; });
}

- (void)updateAccessibilitySettings {
    const auto metrics = overte::ios::sampleNativeMetrics();
    self.metalView.preferredFramesPerSecond = overte::ios::previewFrameLimit(
        metrics.thermal, metrics.lowPower, UIAccessibilityIsReduceMotionEnabled());
    overte::ios::recordNativeMetrics(metrics);
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
    if (self.sceneLoaded && self.scenePipelineState != nil) {
        const float width = fmaxf((float)view.drawableSize.width, 1.0f);
        const float height = fmaxf((float)view.drawableSize.height, 1.0f);
        OverteSceneUniforms uniforms = {
            .aspect = width / height,
            .yaw = _camera.yaw,
            .pitch = _camera.pitch,
            .zoom = _camera.zoom,
            .sceneLoaded = 1,
            .attendance = self.sceneAttendance,
            .domainSeed = self.sceneSeed,
            .reserved = 0,
        };
        [encoder setRenderPipelineState:self.scenePipelineState];
        [encoder setDepthStencilState:self.sceneDepthState];
        [encoder setVertexBytes:&uniforms length:sizeof(uniforms) atIndex:0];
        [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:36 instanceCount:26];
    } else if (self.pipelineState != nil) {
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
