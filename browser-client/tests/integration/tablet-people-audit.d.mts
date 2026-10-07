// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Read-only binding of the actual Tablet navigation command and displayed ACK. */
export function createPeopleFrameAcknowledgement():
  (message:unknown, frames:unknown) => Record<string,unknown>|null;
