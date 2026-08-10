//
// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
//

#import "PlatformProbe.h"

#import <CoreMotion/CoreMotion.h>
#import <Network/Network.h>
#import <os/log.h>

namespace {
os_log_t platformLog() {
    static os_log_t log = os_log_create("org.overte.interface", "platform");
    return log;
}
}

@interface PlatformProbe ()
@property(nonatomic, strong) CMMotionManager* motionManager;
@property(nonatomic, strong) nw_path_monitor_t networkMonitor;
@property(nonatomic, strong) dispatch_queue_t networkQueue;
@end

@implementation PlatformProbe

- (instancetype)init {
    self = [super init];
    if (self != nil) {
        _motionManager = [[CMMotionManager alloc] init];
        _networkQueue = dispatch_queue_create("org.overte.interface.network-path", DISPATCH_QUEUE_SERIAL);
    }
    return self;
}

- (BOOL)deviceMotionAvailable {
    return self.motionManager.deviceMotionAvailable;
}

- (NSString*)applicationSupportPath {
    NSError* error = nil;
    NSURL* url = [NSFileManager.defaultManager URLForDirectory:NSApplicationSupportDirectory
                                                      inDomain:NSUserDomainMask
                                             appropriateForURL:nil
                                                        create:YES
                                                         error:&error];
    if (url == nil) {
        os_log_error(platformLog(), "Could not create application support directory: %{public}@", error);
    }
    return url.path ?: @"";
}

- (void)startNetworkMonitoringWithHandler:(void (^)(BOOL reachable))handler {
    [self stop];
    self.networkMonitor = nw_path_monitor_create();
    nw_path_monitor_set_update_handler(self.networkMonitor, ^(nw_path_t path) {
        BOOL reachable = nw_path_get_status(path) == nw_path_status_satisfied;
        dispatch_async(dispatch_get_main_queue(), ^{
            handler(reachable);
        });
    });
    nw_path_monitor_set_queue(self.networkMonitor, self.networkQueue);
    nw_path_monitor_start(self.networkMonitor);
}

- (void)stop {
    if (self.networkMonitor != nil) {
        nw_path_monitor_cancel(self.networkMonitor);
        self.networkMonitor = nil;
    }
    [self.motionManager stopDeviceMotionUpdates];
}

- (void)dealloc {
    [self stop];
}

@end
