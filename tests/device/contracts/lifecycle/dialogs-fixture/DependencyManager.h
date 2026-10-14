// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QSharedPointer>

class DependencyManager {
public:
    template <typename T> static QSharedPointer<T> get() {
        static auto instance = QSharedPointer<T>::create();
        return instance;
    }
};
