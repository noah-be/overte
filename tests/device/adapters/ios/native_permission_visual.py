"""Read actual native switch pixels, retaining the independently observed row."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from io import BytesIO
import math
from PIL import Image

def _image(data):
    assert isinstance(data,bytes) and 0<len(data)<=24*1024*1024,'bounded-native-switch-screenshot-required'
    image=Image.open(BytesIO(data))
    assert image.format=='PNG' and 0<image.width*image.height<=24*1024*1024,'native-switch-png-required'
    image.load()
    return image.convert('RGB')

def observe(before_bytes,after_bytes,switch_rect,row_rect,viewport):
    before,after=_image(before_bytes),_image(after_bytes)
    assert before.size==after.size,'native-switch-screen-dimensions-changed'
    for rect in (switch_rect,row_rect,viewport):
        assert set(rect)=={'x','y','width','height'}
        assert all(type(v) in (int,float) and math.isfinite(v) for v in rect.values())
        assert rect['width']>0 and rect['height']>0
    assert viewport['x']==viewport['y']==0,'native-switch-screen-origin-unsupported'
    for rect in (switch_rect,row_rect):
        assert rect['x']>=0 and rect['y']>=0 and rect['x']+rect['width']<=viewport['width'] and rect['y']+rect['height']<=viewport['height'],'native-switch-frame-outside-screen'
    center_x=switch_rect['x']+switch_rect['width']/2
    center_y=switch_rect['y']+switch_rect['height']/2
    assert row_rect['x']<=center_x<=row_rect['x']+row_rect['width'] and row_rect['y']<=center_y<=row_rect['y']+row_rect['height'],'native-switch-center-outside-owned-row'
    sx,sy=before.width/viewport['width'],before.height/viewport['height']
    assert 1<=sx<=4 and 1<=sy<=4 and abs(sx-sy)<=.01*max(sx,sy),'native-switch-screenshot-orientation-mismatch'
    assert 1.5<=switch_rect['width']/switch_rect['height']<=3,'native-switch-frame-shape-unsupported'
    def bounds(rect):
        return tuple(round(v) for v in (rect['x']*sx,rect['y']*sy,(rect['x']+rect['width'])*sx,(rect['y']+rect['height'])*sy))
    def state(image):
        crop=image.crop(bounds(switch_rect));pixels=crop.load();total=crop.width*crop.height
        green=0;white=0;white_x=0
        for y in range(crop.height):
            for x in range(crop.width):
                r,g,b=pixels[x,y]
                green+=g>90 and g>r*1.6 and g>b*1.4
                if min(r,g,b)>180 and max(r,g,b)-min(r,g,b)<35:
                    white+=1;white_x+=(x+.5)/crop.width
        green_fraction=green/total;white_fraction=white/total
        assert .12<=white_fraction<=.65,'native-switch-knob-not-observed'
        knob_x=white_x/white
        if green_fraction>=.2 and knob_x>=.6:actual='granted'
        elif green_fraction<=.03 and knob_x<=.4:actual='denied'
        else:raise AssertionError('native-switch-appearance-ambiguous')
        return {'state':actual,'greenPixelFraction':green_fraction,'whiteKnobFraction':white_fraction,'whiteKnobCenterX':knob_x}
    before_state,after_state=state(before),state(after)
    identity={**row_rect,'width':switch_rect['x']-row_rect['x']-4}
    assert identity['width']>=40,'native-switch-row-identity-region-required'
    first,last=before.crop(bounds(identity)),after.crop(bounds(identity))
    colors=first.getcolors(first.width*first.height)
    background=max(colors,key=lambda item:item[0])[1]
    initial,current=first.load(),last.load();features=changed=difference=0
    for y in range(first.height):
        for x in range(first.width):
            a,b=initial[x,y],current[x,y]
            if max(abs(a[i]-background[i]) for i in range(3))<60:continue
            delta=max(abs(a[i]-b[i]) for i in range(3))
            features+=1;changed+=delta>45;difference+=sum(abs(a[i]-b[i]) for i in range(3))/3
    assert features>=64,'native-switch-owned-row-features-not-observed'
    assert changed/features<=.15 and difference/features<=20,'native-switch-owned-row-changed'
    return {'before':before_state,'after':after_state,'ownedRowFeaturesVerified':True,
            'identityFeaturePixels':features,'identityChangedFraction':changed/features,
            'identityMeanDifference':difference/features,'screenScale':sx}
