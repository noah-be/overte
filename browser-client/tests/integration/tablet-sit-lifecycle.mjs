// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Fixed authored harness lifecycle only; keep evidence attempts after close fails. */
export async function finishSitLifecycle(report,{closeBrowser,removeOwnedProfile,attest,persist}){
 try{await closeBrowser();report.browserClosed=true;}catch{report.browserClosed=false;report.browserCloseFailed=true;report.completed=false;}
 try{const removed=await removeOwnedProfile();report.cleanupVerified=removed===true&&report.baselineUnchanged===true&&report.browserClosed===true;}catch{report.cleanupVerified=false;report.cleanupFailed=true;report.completed=false;}
 try{report.sourceCoherent=await attest()===true;}catch{report.sourceCoherent=false;report.sourceAttestationFailed=true;report.completed=false;}
 if(!report.cleanupVerified||!report.sourceCoherent)report.completed=false;
 report.finishedAt=new Date().toISOString();await persist(report);return report.completed===true;
}
