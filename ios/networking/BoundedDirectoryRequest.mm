// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#import "BoundedDirectoryRequest.h"

namespace { constexpr NSUInteger MAX_RESPONSE_BYTES = 256 * 1024; }

@interface BoundedDirectoryRequest ()
@property(nonatomic, strong) NSURLSession* session;
@property(nonatomic, strong) NSURLSessionDataTask* task;
@property(nonatomic, strong) NSMutableData* bytes;
@property(nonatomic, copy) void (^completion)(NSData*);
@end

@implementation BoundedDirectoryRequest
- (instancetype)initWithURL:(NSURL*)url completion:(void (^)(NSData*))completion {
    self = [super init];
    if (self) {
        NSAssert(NSThread.isMainThread, @"Directory requests require the main queue");
        _completion = [completion copy];
        _bytes = [NSMutableData data];
        // This request resolves public places only. User-provided URLs never
        // select a server, credential scope, redirect destination or auth prompt.
        if (![url.scheme.lowercaseString isEqualToString:@"https"] ||
            ![url.host.lowercaseString isEqualToString:@"mv.overte.org"] ||
            url.user != nil || url.password != nil || url.port != nil ||
            ![url.path hasPrefix:@"/server/api/v1/places/"] || url.query != nil || url.fragment != nil) {
            dispatch_async(dispatch_get_main_queue(), ^{ [self finish:nil]; });
            return self;
        }
        NSURLSessionConfiguration* configuration = NSURLSessionConfiguration.ephemeralSessionConfiguration;
        configuration.URLCache = nil;
        configuration.HTTPCookieStorage = nil;
        configuration.URLCredentialStorage = nil;
        configuration.HTTPShouldSetCookies = NO;
        configuration.requestCachePolicy = NSURLRequestReloadIgnoringLocalCacheData;
        configuration.timeoutIntervalForRequest = 12;
        configuration.timeoutIntervalForResource = 12;
        _session = [NSURLSession sessionWithConfiguration:configuration delegate:self
                                          delegateQueue:NSOperationQueue.mainQueue];
        NSMutableURLRequest* request = [NSMutableURLRequest requestWithURL:url];
        [request setValue:@"application/json" forHTTPHeaderField:@"Accept"];
        _task = [_session dataTaskWithRequest:request];
        [_task resume];
    }
    return self;
}

- (void)finish:(NSData*)data {
    void (^completion)(NSData*) = self.completion;
    self.completion = nil;
    [self.session invalidateAndCancel];
    self.session = nil;
    self.task = nil;
    self.bytes = nil;
    if (completion) { completion(data); }
}

- (void)cancel {
    NSAssert(NSThread.isMainThread, @"Directory cancellation requires the main queue");
    self.completion = nil;
    [self finish:nil];
}

- (void)URLSession:(NSURLSession*)session dataTask:(NSURLSessionDataTask*)task
 didReceiveResponse:(NSURLResponse*)response
 completionHandler:(void (^)(NSURLSessionResponseDisposition))completionHandler {
    (void)session; (void)task;
    NSHTTPURLResponse* http = [response isKindOfClass:NSHTTPURLResponse.class]
        ? (NSHTTPURLResponse*)response : nil;
    BOOL accepted = self.completion != nil && http.statusCode == 200 &&
        [response.MIMEType.lowercaseString isEqualToString:@"application/json"] &&
        response.expectedContentLength <= (long long)MAX_RESPONSE_BYTES;
    completionHandler(accepted ? NSURLSessionResponseAllow : NSURLSessionResponseCancel);
    if (!accepted) { [self finish:nil]; }
}

- (void)URLSession:(NSURLSession*)session dataTask:(NSURLSessionDataTask*)task didReceiveData:(NSData*)data {
    (void)session; (void)task;
    if (self.completion == nil) { return; }
    if (data.length > MAX_RESPONSE_BYTES - self.bytes.length) {
        [self finish:nil];
        return;
    }
    [self.bytes appendData:data];
}

- (void)URLSession:(NSURLSession*)session task:(NSURLSessionTask*)task didCompleteWithError:(NSError*)error {
    (void)session; (void)task;
    [self finish:error == nil && self.bytes.length > 0 ? [self.bytes copy] : nil];
}

- (void)URLSession:(NSURLSession*)session task:(NSURLSessionTask*)task
 willPerformHTTPRedirection:(NSHTTPURLResponse*)response newRequest:(NSURLRequest*)request
 completionHandler:(void (^)(NSURLRequest* _Nullable))completionHandler {
    (void)session; (void)task; (void)response; (void)request;
    completionHandler(nil);
    [self finish:nil];
}
@end
