// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Retain a real operation failure when an independently attempted cleanup also
 * fails. Cleanup remains mandatory and a cleanup-only failure still rejects. */
export async function withRecordedCleanup(operation, cleanup, evidence, describe) {
    let primary;
    try { return await operation(); }
    catch (error) { primary = error; evidence.primaryFailure = describe(error); throw error; }
    finally {
        try { await cleanup(); }
        catch (error) { evidence.cleanupFailure = describe(error); if (!primary) throw error; }
    }
}
