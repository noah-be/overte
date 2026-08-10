// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include <QtGlobal>

#if defined(Q_OS_IOS)
#include <QtPlugin>

Q_IMPORT_PLUGIN(PCMCodecProvider)
Q_IMPORT_PLUGIN(AthenaOpusCodecProvider)
#endif
