export const CREATE_LAYOUT_SOURCE_SHA256:Readonly<Record<string,string>>;
export const RESPONSIVE_CREATE_CSS:string;
export function responsiveCreateHTML(source:string):string;
export function buildResponsiveCreateHTML(sources:Record<string,string>):string;
export function loadBrowserCreatePackage(defaultScriptsURL:string):Promise<{
    sourceHashes:Record<string,string>;
    prepare(directory:string):Promise<{readOnlyOverrides:Array<{source:string;target:string}>}>;
}>;
