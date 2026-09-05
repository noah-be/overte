// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
// HTTPS directory lookup; ephemeral, no redirects, no cookie/credential storage,
// 256 KiB response cap and a 12-second resource deadline. Completion on main.
@interface BoundedDirectoryRequest : NSObject <NSURLSessionDataDelegate>
- (instancetype)initWithURL:(NSURL*)url
                completion:(void (^)(NSData* _Nullable data))completion;
- (void)cancel;
@end
NS_ASSUME_NONNULL_END
