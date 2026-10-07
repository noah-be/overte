// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
export interface TabletFileOptions {
    fileURL:(name?:string)=>string;
    onStatus:(message:string)=>void;
    onUpload?:(name:string)=>void;
}
/** Browser-owned files made available to genuine native dialogs in this session. */
export class TabletFiles {
    private input:HTMLInputElement;
    private panel:HTMLElement;
    private list:HTMLElement;
    private abort=new AbortController();
    private generation=0;
    private disposed=false;
    constructor(toolbar:HTMLElement,container:HTMLElement,private options:TabletFileOptions){
        this.input=document.createElement('input');this.input.type='file';this.input.multiple=true;this.input.hidden=true;
        const upload=document.createElement('button');upload.type='button';upload.textContent='Upload files';
        upload.addEventListener('click',()=>this.input.click(),{signal:this.abort.signal});
        const show=document.createElement('button');show.type='button';show.textContent='Visitor files';
        show.addEventListener('click',()=>{this.panel.hidden=!this.panel.hidden;if(!this.panel.hidden)void this.refresh();},{signal:this.abort.signal});
        toolbar.append(upload,show,this.input);
        this.panel=document.createElement('aside');this.panel.setAttribute('aria-label','Visitor files');this.panel.hidden=true;
        Object.assign(this.panel.style,{position:'absolute',inset:'60px 15px auto',maxHeight:'65%',overflow:'auto',padding:'12px',background:'#1c2635',border:'1px solid #7d8ba1',borderRadius:'8px',zIndex:'1'});
        const explanation=document.createElement('p');explanation.textContent='Uploaded files are available in the native file dialog’s home folder under “files”. Files belong to this connection and are deleted when you leave.';
        const close=document.createElement('button');close.type='button';close.textContent='Close files';close.addEventListener('click',()=>{this.panel.hidden=true;},{signal:this.abort.signal});
        this.list=document.createElement('ul');this.panel.append(explanation,close,this.list);container.append(this.panel);
        this.input.addEventListener('change',()=>void this.upload(),{signal:this.abort.signal});
    }
    private async upload():Promise<void>{
        const files=Array.from(this.input.files||[]);this.input.value='';const generation=this.generation;
        for(const file of files){
            if(this.disposed||generation!==this.generation)return;
            if(file.size>64*1024*1024){this.options.onStatus(`${file.name}: files must be at most 64 MiB.`);continue;}
            try{
                this.options.onStatus(`Uploading ${file.name}…`);
                const response=await fetch(this.options.fileURL(file.name),{method:'PUT',credentials:'same-origin',body:file,signal:this.abort.signal});
                if(!response.ok)throw Error((await response.json().catch(()=>({}))).error||`Upload returned HTTP ${response.status}`);
                if(this.disposed||generation!==this.generation)return;
                this.options.onStatus(`${file.name} is available in your native visitor files folder.`);this.options.onUpload?.(file.name);
            }catch(error){if(!this.disposed)this.options.onStatus(`File upload failed: ${error instanceof Error?error.message:String(error)}`);}
        }
        if(!this.panel.hidden)await this.refresh();
    }
    async refresh():Promise<void>{
        const generation=this.generation;
        try{
            const response=await fetch(this.options.fileURL(),{credentials:'same-origin',cache:'no-store',signal:this.abort.signal});
            if(!response.ok)throw Error(`File list returned HTTP ${response.status}`);
            const inventory:unknown=await response.json();
            const data=inventory&&typeof inventory==='object'&&!Array.isArray(inventory)?(inventory as {files?:unknown}).files:undefined;
            if(!Array.isArray(data)||data.length>256||!data.every(item=>item&&typeof item==='object'&&typeof item.name==='string'&&item.name.length<=180&&Number.isSafeInteger(item.size)&&item.size>=0&&item.size<=64*1024*1024))throw Error('Invalid visitor file list');
            if(this.disposed||generation!==this.generation)return;this.list.replaceChildren();
            for(const file of data){
                const item=document.createElement('li'),link=document.createElement('a');link.textContent=`${file.name} (${Math.ceil(file.size/1024)} KiB)`;link.href=this.options.fileURL(file.name);link.download=file.name;
                const remove=document.createElement('button');remove.type='button';remove.textContent='Delete';remove.setAttribute('aria-label',`Delete ${file.name}`);
                remove.addEventListener('click',()=>void this.remove(file.name),{signal:this.abort.signal});item.append(link,' ',remove);this.list.append(item);
            }
            if(!data.length){const empty=document.createElement('li');empty.textContent='No visitor files yet.';this.list.append(empty);}
        }catch(error){if(!this.disposed)this.options.onStatus(`Visitor files unavailable: ${error instanceof Error?error.message:String(error)}`);}
    }
    private async remove(name:string):Promise<void>{
        try{const response=await fetch(this.options.fileURL(name),{method:'DELETE',credentials:'same-origin',signal:this.abort.signal});if(!response.ok)throw Error(`Delete returned HTTP ${response.status}`);await this.refresh();}
        catch(error){if(!this.disposed)this.options.onStatus(`File deletion failed: ${error instanceof Error?error.message:String(error)}`);}
    }
    dispose():void{if(this.disposed)return;this.disposed=true;this.generation++;this.abort.abort();this.panel.remove();this.input.remove();}
}
