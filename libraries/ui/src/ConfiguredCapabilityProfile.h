// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QtCore/QtGlobal>
#include "CapabilityProfile.h"

namespace overte { namespace ui {
inline Product configuredProduct() {
#if defined(Q_OS_ANDROID) && defined(Q_OS_IOS)
    return Product::Unknown;
#elif defined(Q_OS_ANDROID)
#if defined(HIFI_ANDROID_APP)
    return resolveProduct(true, false, HIFI_ANDROID_APP);
#else
    return Product::Unknown;
#endif
#elif defined(Q_OS_IOS)
    return Product::IOS;
#else
    return Product::Desktop;
#endif
}
}} // namespace overte::ui
