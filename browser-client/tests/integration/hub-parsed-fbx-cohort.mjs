// SPDX-License-Identifier: Apache-2.0
// Changes one existing entry query only. No live sampling, retries or assertions.
export function configureParsedFbxTemplateCohort(mode,entryURL){
 if(mode===undefined)return undefined;
 if(mode!=='baseline'&&mode!=='templates')throw Error('Parsed FBX cohort mode refused.');
 if(!(entryURL instanceof URL))throw Error('Parsed FBX cohort entry refused.');
 if(mode==='templates')entryURL.searchParams.set('parsedFbxTemplates','1');
 else entryURL.searchParams.delete('parsedFbxTemplates');
 return {schema:1,mode};
}
