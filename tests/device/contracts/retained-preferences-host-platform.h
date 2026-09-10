// SPDX-License-Identifier: Apache-2.0
#pragma once
// Load the real host Qt ABI before selecting the product macros ONLY for the
// application code under test. This does not pretend Linux Qt is an Android SDK.
#include <QtCore/QtCore>
#include <QtGui/QtGui>
#include <QtQml/QtQml>
#include <QtQuick/QtQuick>
#if defined(SH003_TEST_ANDROID)
#define Q_OS_ANDROID
#endif
#if defined(SH003_TEST_IOS)
#define Q_OS_IOS
#endif
