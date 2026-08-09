//
// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
//

#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface PlatformProbe : NSObject

@property(nonatomic, readonly) BOOL deviceMotionAvailable;
@property(nonatomic, readonly, copy) NSString* applicationSupportPath;

- (void)startNetworkMonitoringWithHandler:(void (^)(BOOL reachable))handler;
- (void)stop;

@end

NS_ASSUME_NONNULL_END

