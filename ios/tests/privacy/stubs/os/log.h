// Test-only replacement of the OS transport, not of the production sanitizer.
#pragma once
using os_log_t = int;
inline os_log_t os_log_create(const char*, const char*) { return 1; }
void captureOSLog(const char* format, const char* message);
#define os_log_info(log, format, message) ((void)(log), captureOSLog(format, message))
