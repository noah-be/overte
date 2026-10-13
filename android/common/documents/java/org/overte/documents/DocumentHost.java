// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.documents;
import android.app.Activity;
/** Immutable Activity owner for one explicit OS document selection. */
public interface DocumentHost { Activity activity(); boolean isForeground(); }
