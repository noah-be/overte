// Test-only Android log ABI declarations.
#pragma once
#define ANDROID_LOG_ERROR 6
#define ANDROID_LOG_WARN 5
extern "C" int __android_log_write(int priority, const char* tag, const char* text);
