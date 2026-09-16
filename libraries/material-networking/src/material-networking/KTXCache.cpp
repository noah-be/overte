//
//  KTXCache.cpp
//  libraries/model-networking/src
//
//  Created by Zach Pomerantz on 2/22/2017.
//  Copyright 2017 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "KTXCache.h"

#include <SettingHandle.h>
#include <ktx/KTX.h>
#include <PhoneLoadingDiagnostics.h>

using File = cache::File;
using FilePointer = cache::FilePointer;

// Whenever a change is made to the serialized format for the KTX cache that isn't backward compatible,
// this value should be incremented.  This will force the KTX cache to be wiped
const int KTXCache::CURRENT_VERSION = 0x02;
const int KTXCache::INVALID_VERSION = 0x00;
const char* KTXCache::SETTING_VERSION_NAME = "hifi.ktx.cache_version";

KTXCache::KTXCache(const std::string& dir, const std::string& ext) :
    FileCache(dir, ext) { }

void KTXCache::initialize() {
    FileCache::initialize();
    Setting::Handle<int> cacheVersionHandle(SETTING_VERSION_NAME, INVALID_VERSION);
    auto cacheVersion = cacheVersionHandle.get();
    PHONE_LOADING("phase=ktx_cache_version edge=0 stored=%d expected=%d reset=%d indexed_files=%llu indexed_bytes=%llu unused_files=%llu unused_bytes=%llu",
        cacheVersion, CURRENT_VERSION, int(cacheVersion != CURRENT_VERSION),
        (unsigned long long)getNumTotalFiles(), (unsigned long long)getSizeTotalFiles(),
        (unsigned long long)getNumCachedFiles(), (unsigned long long)getSizeCachedFiles());
    if (cacheVersion != CURRENT_VERSION) {
        wipe();
        cacheVersionHandle.set(CURRENT_VERSION);
    }
    PHONE_LOADING("phase=ktx_cache_version edge=1 stored=%d expected=%d reset=%d indexed_files=%llu indexed_bytes=%llu unused_files=%llu unused_bytes=%llu",
        cacheVersionHandle.get(), CURRENT_VERSION, int(cacheVersion != CURRENT_VERSION),
        (unsigned long long)getNumTotalFiles(), (unsigned long long)getSizeTotalFiles(),
        (unsigned long long)getNumCachedFiles(), (unsigned long long)getSizeCachedFiles());
}


std::unique_ptr<File> KTXCache::createFile(Metadata&& metadata, const std::string& filepath) {
    qCDebug(file_cache) << "Wrote KTX" << metadata.key.c_str();
    return FileCache::createFile(std::move(metadata), filepath);
}

