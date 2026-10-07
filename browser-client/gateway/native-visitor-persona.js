// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Narrow visitor values; native account/settings state is never read or copied.
function createBrowserVisitorPersona(config) {
    var restored=false,stopped=false,lastPoll=0,lastSignature='',lastAuthority=null,warned=false;
    var initial=config.initial||{},pendingAvatar=false,baseline={};
    function modelURL(value){return String(value).replace(/^(qrc|resource):\/+(meshes\/(?:defaultAvatar_full\.fst|mannequin\/mannequin\.fbx))$/, '$1:/$2');}
    function restore(){
        if(stopped||restored||!config.authority()){return;}
        if(typeof config.displayName==='string'){config.avatar.displayName=config.displayName;}
        else if(typeof initial.displayName==='string'){config.avatar.displayName=initial.displayName;}
        if(initial.avatarURL){config.avatar.useFullAvatarURL(initial.avatarURL);pendingAvatar=true;}
        if(typeof initial.avatarScale==='number'){config.avatar.setAvatarScale(initial.avatarScale);}
        (config.preserveFields||[]).forEach(function(key){
            if(key==='avatarFavorites'){baseline[key]=JSON.stringify(bookmarkMap());}
            else if(key==='avatarURL'){baseline[key]=modelURL(config.avatar.skeletonModelURL||'');}
            else if(key==='avatarScale'){baseline[key]=Number(config.avatar.getTargetScale());}
        });
        restored=true;
    }
    function bookmarkMap(){
        var source=config.bookmarks.getBookmarks(),result=Object.create(null);
        Object.keys(source).forEach(function(name){result[name]=source[name];});
        // QVariantMap-to-JS setProperty treats this legitimate QMap key as a prototype setter.
        // The documented single-entry API returns the stored record without that outer-name conversion.
        if(typeof config.bookmarks.getBookmark==='function'){
            var special=config.bookmarks.getBookmark('__proto__');
            if(special&&Object.keys(special).length){result['__proto__']=special;}
        }
        return result;
    }
    function favorites(){
        var raw=bookmarkMap(),names=Object.keys(raw),result=[];
        if(names.length>100){throw Error('Too many avatar favorites.');}
        names.sort().forEach(function(name){
            var value=raw[name];
            if(typeof value==='string'){result.push({name:name,avatarURL:value,avatarScale:1});return;}
            if(!value||value.version!==3){throw Error('Unsupported native avatar favorite version.');}
            var entities=value.avatarEntites||[];
            if(entities.length>32){throw Error('Too many favorite wearables.');}
            var favorite={name:name,avatarURL:String(value.avatarUrl),avatarScale:Number(value.avatarScale),avatarIcon:String(value.avatarIcon||''),avatarEntities:[]};
            entities.forEach(function(entity){
                var properties=entity.properties,copy={};
                if(!properties||properties.type!=='Model'){throw Error('Unsupported wearable.');}
                Object.keys(properties).forEach(function(key){
                    if(config.wearableFields.indexOf(key)!==-1){copy[key]=properties[key];return;}
                    // Only explicit runtime metadata and inert packaged defaults can be omitted.
                    if(config.runtimeFields.indexOf(key)!==-1){return;}
                    var expected=config.inertFields[key];
                    if(expected!==undefined&&JSON.stringify(expected)===JSON.stringify(properties[key])){return;}
                    throw Error('Unsupported native wearable property.');
                });
                favorite.avatarEntities.push({properties:copy});
            });
            result.push(favorite);
        });
        return result;
    }
    function poll(force){
        var authority=config.authority(),now=Date.now();
        if(stopped||!restored||!authority||(!force&&now-lastPoll<1000)){return;}
        lastPoll=now;
        var result={displayName:String(config.avatar.displayName||''),avatarURL:modelURL(config.avatar.skeletonModelURL||''),avatarScale:Number(config.avatar.getTargetScale())};
        // A requested model may still be loading: do not replace the saved visitor model with the prior default.
        if(pendingAvatar){
            if(result.avatarURL!==initial.avatarURL){delete result.avatarURL;delete result.avatarScale;}
            else{pendingAvatar=false;if(typeof initial.avatarScale==='number'){config.avatar.setAvatarScale(initial.avatarScale);result.avatarScale=initial.avatarScale;}}
        }
        try{result.avatarFavorites=favorites();if(unescape(encodeURIComponent(JSON.stringify(result))).length>49152){delete result.avatarFavorites;throw Error('Favorite collection too large.');}}
        catch(error){delete result.avatarFavorites;if(!warned){warned=true;config.send({type:'warning',message:'Native avatar favorites contain unsupported wearable properties or exceed the browser limits. Existing saved browser favorites were preserved.'});}}
        (config.preserveFields||[]).forEach(function(key){
            var current=key==='avatarFavorites'?JSON.stringify(bookmarkMap()):result[key];
            if(current===baseline[key]){delete result[key];}else{delete baseline[key];}
        });
        var signature=JSON.stringify(result);
        if((signature===lastSignature&&authority===lastAuthority)||config.authority()!==authority){return;}
        lastSignature=signature;lastAuthority=authority;result.type='visitorPersona';result.permissionRevision=config.revision();config.send(result);
    }
    return {restore:restore,poll:poll,stop:function(){stopped=true;}};
}
