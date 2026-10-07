// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Finalize only the owned fixture resources and fixed diagnostic fields.
 * New cleanup/hash errors never reflect exception messages, paths or secrets.
 * Publishing still runs after failed close/source/bundle operations. A failing
 * publisher propagates after both owned close attempts have already run.
 */
export async function finalizeNativeIgnoredFbxEvidence({report,closeBrowser,closeServer,hashSources,hashBundles,publish,now=()=>new Date().toISOString()}) {
 let failed=false;
 const refuse=()=>{failed=true;report.completed=false;};
 report.cleanup={browserClose:closeBrowser?'pending':'not-created',serverClose:closeServer?'pending':'not-created'};
 try {
  try {if(closeBrowser){await closeBrowser();report.cleanup.browserClose='closed';}}
  catch {report.cleanup.browserClose='failed';refuse();}
 } finally {
  try {if(closeServer){await closeServer();report.cleanup.serverClose='closed';}}
  catch {report.cleanup.serverClose='failed';refuse();}
 }
 report.finishedAt=now();
 try {report.sourceEnd=await hashSources();report.sourceCoherent=JSON.stringify(report.sourceStart)===JSON.stringify(report.sourceEnd);if(!report.sourceCoherent)refuse();}
 catch {report.sourceHashFailure=true;report.sourceCoherent=false;refuse();}
 report.bundleSHA256={};
 try {report.bundleSHA256=await hashBundles();}
 catch {report.bundleHashFailure=true;refuse();}
 await publish(report);
 return {failed};
}
