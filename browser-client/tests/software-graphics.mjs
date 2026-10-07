// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Virtual-display software fixtures need an explicit ANGLE backend too.
export function chromiumGraphicsArgs({ headless = false, software = process.env.LIBGL_ALWAYS_SOFTWARE } = {}) {
    return headless || software === 'true' ? ['--use-angle=swiftshader'] : [];
}
