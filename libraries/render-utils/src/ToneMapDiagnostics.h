//
//  ToneMapDiagnostics.h
//  libraries/render-utils/src
//
//  A narrow diagnostics boundary for display backends.  Keep this header free
//  of render-task headers so consumers do not inherit render-utils' private
//  task include graph.
//

#pragma once

#include <QtCore/QtGlobal>

#include <gpu/Forward.h>

#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
gpu::FramebufferPointer getToneMapDiagnosticInputFramebuffer();
#endif
