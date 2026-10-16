#!/usr/bin/env python3
"""Pure protected affected-suite selection; no suite/build/runtime execution."""
from copy import deepcopy
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zlib
from unittest.mock import patch, Mock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inputs


def blob(raw=b'fixed', *, mode='100644'):
    return {'mode':mode,'type':'blob','sha':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}


def definition(scope='content'):
    return {'command':['python','contracts/test.py'],'layer':'host','scope':scope,'environment':'host-qt5-qt6',
        'closure':{'kind':'patterns','inputs':['contracts/**','source/**'],'required':['contracts/test.py']},
        'python_imports':{'roots':['contracts'],'reviewed':'sha256:'+'0'*64}}


class AffectedPlannerTests(unittest.TestCase):
    def setUp(self):
        self.tree={p:blob(p.encode(),mode='100755' if p=='tests/run-project-tests.py' else '100644')
                   for p in inputs.AFFECTED_AUTHORITY}
        self.tree['tests/platform-profile.json']=deepcopy(inputs._AFFECTED_SHARED_PROFILE)
        self.tree.update({'contracts/test.py':blob(b'fixed test'),'source/input.qml':blob(b'fixed data'),
            'tools/test-evidence/sandbox_host.py':blob(b'old controller'),'unrelated/readme.md':blob(b'data')})
        finite=definition();finite['python_imports']['reviewed']=inputs.python_import_digest(self.tree,['contracts'])
        self.registry={'schema':1,'control_inputs':['tests/run-project-tests.py','tools/test-evidence/**','*.py'],
            'suites':{'finite':finite,'unproved':{'command':['python','unknown.py'],'layer':'quick','scope':'content',
                'environment':'host-qt5-qt6','closure':{'kind':'repository','inputs':[],'required':[]}},
                'candidate':definition('candidate')}}
        self.dependencies={'schema':1,'lookup_digest':inputs.affected_lookup_digest(self.tree),'registry_digest':inputs._suite_definition_digest(self.registry),'suites':{
            n:{'kind':'repository' if n=='unproved' else 'reviewed-patterns',
               'definition_digest':inputs._suite_definition_digest(s),'setup':['host-full'] if n=='unproved' else ['python']}
            for n,s in self.registry['suites'].items()}}
        self.seal()
        self.candidate=deepcopy(self.tree)
        self.candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed candidate controller')

    def seal(self):
        self.raw=json.dumps(self.dependencies,indent=2).encode()
        self.tree[inputs.AFFECTED_POLICY]=blob(self.raw)

    def plan(self,base=None,candidate=None,trusted=None,raw=None,registry=None):
        return inputs.plan_affected(registry or self.registry,self.raw if raw is None else raw,
            self.tree if base is None else base,self.candidate if candidate is None else candidate,
            self.tree if trusted is None else trusted)

    def test_changed_controller_selects_unproved_and_candidate_owners_individually(self):
        plan=self.plan()
        self.assertEqual(plan['required'],['unproved','candidate'])
        self.assertEqual(plan['omitted'],['finite'])
        self.assertFalse(plan['reusable'])
        self.assertEqual(plan['required_setup'],['host-full'])
        self.assertEqual(plan['paths'],['tools/test-evidence/sandbox_host.py'])

    def test_own_data_and_discovery_changes_select_their_suite(self):
        for path in ('source/input.qml','source/new.qml','contracts/data.json'):
            with self.subTest(path=path):
                candidate=deepcopy(self.candidate);candidate[path]=blob(b'changed')
                self.assertIn('finite',self.plan(candidate=candidate)['required'])

    def test_lookup_shadows_native_modules_pth_and_deletions_are_not_hidden(self):
        for path in ('contracts/json.py','contracts/sitecustomize.py','contracts/module.so','contracts/path.pth','contracts/test.py'):
            with self.subTest(path=path):
                candidate=deepcopy(self.candidate)
                if path in candidate:del candidate[path]
                else:candidate[path]=blob(b'new lookup candidate')
                with self.assertRaises(inputs.InputError):self.plan(candidate=candidate)

    def test_historical_unreviewed_module_on_both_sides_keeps_owner_required(self):
        base=deepcopy(self.tree);candidate=deepcopy(self.candidate)
        for tree in (base,candidate):tree['contracts/historical.py']=blob(b'child variant')
        with self.assertRaises(inputs.InputError):self.plan(base=base,candidate=candidate)

    def test_nonregular_inventory_anywhere_declines_even_if_unchanged(self):
        for mode,kind in (('120000','blob'),('160000','commit')):
            with self.subTest(mode=mode):
                base=deepcopy(self.tree);candidate=deepcopy(self.candidate)
                for tree in (base,candidate):tree['other/entry']={'mode':mode,'type':kind,'sha':'a'*40}
                with self.assertRaises(inputs.InputError):self.plan(base=base,candidate=candidate)

    def test_candidate_cannot_add_replace_remove_or_enable_its_graph(self):
        for which in ('candidate','base','trusted'):
            for operation in ('remove','change','mode'):
                trees={n:deepcopy(t) for n,t in (('base',self.tree),('candidate',self.candidate),('trusted',self.tree))}
                if operation=='remove':del trees[which][inputs.AFFECTED_POLICY]
                elif operation=='mode':trees[which][inputs.AFFECTED_POLICY]['mode']='100755'
                else:trees[which][inputs.AFFECTED_POLICY]=blob(b'candidate narrowed graph')
                with self.subTest(which=which,operation=operation),self.assertRaises(inputs.InputError):self.plan(**trees)

    def test_every_authority_change_declines_before_selection(self):
        for path in inputs.AFFECTED_AUTHORITY:
            candidate=deepcopy(self.candidate);candidate[path]=blob(b'new authority')
            with self.subTest(path=path),self.assertRaises(inputs.InputError):self.plan(candidate=candidate)

    def test_closed_policy_registry_definition_and_global_controls_are_bound(self):
        mutations=[]
        for change in ('schema','unknown','missing','definition','arbitrary-kind','setup','duplicate-setup'):
            value=deepcopy(self.dependencies)
            if change=='schema':value['schema']=True
            elif change=='unknown':value['force']=[]
            elif change=='missing':del value['suites']['unproved']
            elif change=='definition':value['suites']['finite']['definition_digest']='sha256:'+'f'*64
            elif change=='arbitrary-kind':value['suites']['finite']['kind']='caller-selected'
            elif change=='setup':value['suites']['unproved']['setup']=['python']
            else:value['suites']['finite']['setup']=['python','python']
            mutations.append((change,json.dumps(value).encode()))
        mutations += [('duplicate-key',self.raw.replace(b'"schema": 1',b'"schema":1,"schema":1')),
                      ('oversized',b' '*64001),('wrong-type','{}')]
        for change,raw in mutations:
            with self.subTest(change=change),self.assertRaises(inputs.InputError):self.plan(raw=raw)
        registry=deepcopy(self.registry);registry['control_inputs']=[]
        with self.assertRaises(inputs.InputError):self.plan(registry=registry)

    def test_missing_unknown_empty_and_wrong_policy_bytes_fail_closed(self):
        for tree in (None,{},[] ):
            with self.subTest(tree=tree),self.assertRaises(inputs.InputError):
                inputs.plan_affected(self.registry,self.raw,tree,self.candidate,self.tree)
        with self.assertRaises(inputs.InputError):self.plan(candidate=self.tree)
        with self.assertRaises(inputs.InputError):self.plan(raw=self.raw+b' ')


# Fixture-only projection from genuine protected main
# 50b46b512233f882c61a6e8ae8a12f9f64f6e049 / tree f934231ec3aaee76d9071218889b7b38b06b2c75.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = 'fbc575cab5d4fa1359a340ec9e5a591f555cf95fce53b9c2a485b624268df43f'
_MAIN_PROJECTION_B85 = (
    'c-qa~+m;+h(jDmgd5pdm8gV}8DQ3-@`&x1E0Fo?JR@Z?|N=xrPpG9VY;NPf>$Si7Re(4vRAl2>};bCsJZSQUW^B@2Ga(MarI({A='
    '=BMLf{&f8JLwfr3@-#d=FX`!@zdRow{_)@c=Rdw3=k$;N{*OG%nyUK8fBVPt*TLTw?VP1NYnFNL%dGD6ISoVK6w8veb2W`ARc+Db'
    '@&DoFkH`2g81IkcKmON$`@ZaGq3P?V$K(BB`eS3YaV+ONZ&K5@**v7FYueTtS=MGt*^G0xv`sZ+-TSLO4%4s0m-Ol1$ERPH`{Tbq'
    'eMx@p@NzglJZ~&M<^5E5%h2Rm)r`eB)+wL!y6)P#80#YI>bdRfa(I97r}TJyKD->C{`fR~P1CPiD|SQPlvy)(WnLAjnddamWuLWm'
    'J<fAJR{fO5zDnu+6<^Zx%ctkp!%O-!r^oa#r-$i~w$^R?tQ@N%FH@7%ZIcgWkr!h(EXB}!++$u=OWQWZo^`j@$~-|oqV4k5u^Fqj'
    '>6fnVif-zPKChRd&C7mhFFe(^SNZJaKBb43Pyc!y?hnghTHoqF|M+(Q{_4$K%%x{rjZHcCer}T$Rh{Q`JLhFrSL0k49(%iM^{3-6'
    'X?pn-zy100vRz+fL!YO%pSo1kQ&~;fuz0<3xaKw=nxeLBzh~M1JX9B#ZkN_~Q!a6E^E6KVG&g-&Wce^m`P@x&+s=JeE&sXn_+&Ye'
    'VY)wf%Acph=U>vpuZM@{&tHak&yRn+ziOTjQ#DSL7hF~CSXABIOhw+-X|6jDeDN){ZB|^f>Z4!og<oFRK`m1?q_!)^Y-)?S%a(2&'
    'J?L>MT0yGIQktgg);*4wS6zms&Aik$U;Mrz>xZl;Tc6a_r>>gXWtfKAM}5tzPp=Ob*PQaIX_|Q%`myR-KX2&EChNO=EYp~ZY96yT'
    'Ez4DF#!0@LzCInlrMu_p_;~qO`&_cjlO6K1X`JgR^@DKOW_8i|w(4o_=PtkQS+6^I7`~-vfjiwjrQz}L@a5t*=FaJznp8Jc-YqGw'
    'QknNfRSnbV^Umw4YVs<du73~@kKgX5<HK^eynZ|6sp-nPX}WyK#W69w$m+2fTo7}S*<5Rn<<;xQy*%Ij{@XHMTz_=VvZ|Wvy6xMh'
    '&OC{F=(DMCLpqVAr;w#`9Ijs933OFnTsuum*$qNw?ZYeEacZaBZ6UVR)ie}&C)hUGj^7>;<=?{}pC8goM7q1D<LgVhn-9a6hvW0h'
    'VY(b`O1IR|r7EwdI#phO-=#G4OP$q?s5i}HG30gLU%idj`SIeyMd!9mdEv(J!Owj>eLHEUe3=U$!ZJFEscm;Jd^&jN)z`!<j^IoB'
    '{pE51s(tKj8j7+myV5moQ+1!(v7UX6eVX!Yj4W+)ANPa2@a6dJFntpCemgw7QGI})hu8V=a(BM*;+DPmMb>p1s<{|sgXJO`&U4kf'
    'W4efmc~i&B@MPMXce8$#@p0S_uX4%DQL1gq$*te?mG{xi!zga{a*bt~+cI17JZ0T7XSZ+WRXTY&QqI$mcT>@HOIG{sLp>F(tHEc|'
    '7K;?K9_FenQhxIueoapg>HcngOBZ+2OY7QZZX5UhShh=*70WmmO&!_T(xkp^o!?@)c_-h72kG{FC&zb`pZ>V}dU%dp<>IcgxVW07'
    '>c%Wh!bqEHmzi5su8@~@n6;Isbo;K3qkrkQjbPSH<ud0}J&KmqShTIvJCxa6N}rMwB#t%lPjBDF<GJz}?$@vSX_#Iv2exjmx}vR$'
    'PJz`mqIzAI?KF4tMaR0RvVKlQH}*GgNlvxgAHIBj*&S<}wp?UX*-+J^t0no)bGdvc{=@^C%S_F-wBrZ1w3Tjo0ChHXS*rpq8`WkJ'
    'S(hx!Bk8@ptSh^&EascHAnlk1yTflj?7Q!e=yDd|tPEq;FU2x>24&ZF;{MnOzRQ^B;>;xeWVb(-=NI4A<-^iD8f`2+_GLFsE}^A&'
    'ZYK|_Rj;>gUH0_{zM_}m=}X#u3oH`eY?x-*$I>_>$%ma+ZS9b>@q`-rL7%1D-_j{teY*<A<LkpbYy=v|L<N>f&%Kr`R|GY)|5G=U'
    '>UV6aOaVSFRr;IuwBvdz(~|dfKdQ;9GWBykW#ckWdF~{4vtt|)XIiok?r6QE?skR2sg}PNxeL?9*cITNIgOo@t;!k7vQ)k=(yR}@'
    'xAgGa;pzDB&A)hhb(hP!B5<C5No6_0VW!3vF%Au^sYydO7M__KeJ($?r`@+`H&pEaqsiN5OkL`ixl-Lqz?7Gx+_&+;+fnuRZRhSF'
    '3H)-pJvK7IaqJwZxh<wlARfJ}v2Uinb6J$`v@tD(?S5=)H{J4M+b8&yVqseP7QEF?Q76Ji@<}dIEmb+p{q#3&Z90BiagwbE)+|FR'
    'dx?D2=K^KC&rZ@TeA{gUbz9uCT{-_fyLwK)rH75GTFDA{j2Ebg6aX^MtIKlNM^UB@8d|nLMIEo%&#p)yJ*@gNAci?D{nR&u8+XVW'
    'AO8f9%^NQ?SLS|jD?emK-wu1uc)w)j5CB7&fOw$0sRb$KBSb6NU0Do(+M!xLwy*0`BkygHGr~dYu?(1N0WMZ~Q&f(4Q+9<NR@pLs'
    'bYJqLyXh&xc3%#|{qqJopyaBm!bRKlqqJ>VJgmqG@=>yzmlG&k<@(`0?MVqrm%oGKf1pJ}p8Muy)gXPyP1!XH)O={?qWIWmZphx`'
    'kmHg!dDHm9l+8m8HBD{3RCyY5S5Dy`%!}z`8+$&!J^{6+<JSbYo-Su|)|)d$(csAh%9eBj8bEv>CBQQEvxhc;m_E3r$SUu4l&}yc'
    '`5LgVXls?(GP-99sLNayb%J{ePhIxYzR&gBS%$;?>ju!<Ro#?^R1aBI57X4<t=x8yvrL7@G?iu7>rmw%Jl8MZ9+$&?`d+PF{`^~)'
    'ep3#rGjNcI*??s{mQlW&1thync~LhXJl!u(ug@=Tl3&vwPg~HaZ(e@s`>w{6JJY>)H1&YeY|I_1)GgKArH@nuS8OJ-?5xaNm}t>='
    'i?_EFVt7@JnJ;V_tFrE45&N$HGe~{@Czo%Fxr7Ef7SPeQc3&vyGns6ikF`V=MqBGWb^9{xFRyF3OHbbp&(CWQ@nSMI_Pu^YG&+_p'
    'jWbN6l}3-*SPgBJI!&Ni%-Q#ozaHc5ACFrBKQ3tXL^t$pHC6MZS-C`g-nqf&ET6$~K9hZGp3;`fp;MQ%@Zpu(A9G|;fbWz8xWFch'
    'J4av59_D@d(}T<Zw{$nm-wu~=5}ggnhxnI|MbqehKqcm7(qk+A-x9!8DHwJZ1m{)vfQeb=5?7W*fz(cEY83XBFCGdK@X@4P69)F3'
    'r60ef-8sfo=BXGJ`Rc={T6KWtN^4K9;bYH=dF+AkJL|<C`#pO;rFK?ZRHddgl)rAPDDYD+doF#-j<s4^Z8o=8EPg6Xr{hz)`^EM6'
    'kS^B{5n2T^eU7S`RewzjW$v@6+<VQaMx8oL%TA2$#~pk-{+8Ba)D^UG73OfswkVct?8+fvTxpG@Gww#XSg&etH6Hq5{~oT3D%0eN'
    'XQj_N)A}kky6Q1sN)26KT5<uUMgh@}``6zYTJm{OJE8?Rd~lSu^Th??7Oit1V$})n^6ql~!l(GM<C&|0ym!sq!u3_;S+Em^YSc&9'
    'c!2<@+~!*U^V+5VEMYI-AsX44v}cgI1{Ts5GW*Vh2k2*BcMd0!kS(__fA028kFS@XgYPcKl<=qCdWD0duUzL1l-NC|pU|}$E&UA}'
    '*|&bV)S8^RtWUF3@+C`Md=F*e54r)mfYLE%*B=21`^x3;DGX1Sv7iwlWiF!2>Q<SAyt=lh39Z5*OoC%4)0pS+<}K`d60PTNy-d@4'
    'KsG?$7_bdI{6T%3-0YI8TAp#kHvV||dVJUiXvX1JBmi}~m4?-Ka$<xJbwcX&m{iA}S9Qa~cuHSjItrEf?%z+t<KtGAHI13_cX23$'
    'g22FBj$=LO39HC4#+(=U&J70xuynZz+cfI5#$wXBxr){zXmHVOL)j7{p}f+*w6l0S6A<<$1bsX7LmA|fMKdDJnH#BsZdH<lxgK>H'
    'g95W$aUb2373eS2n%<4)?<bE~ak`z;5K!P?C%ALd)Ra4_q0=w_ba;4tefjLI-=A4kpJe!-{+%S=U^Nxd#og%DMV0EUujg-)*(()6'
    'YXOLWyBCk8sCQ&Zf7y-IKczW{Pd{!fN{_qYB_7>2a5ShArD<xAAbkx^#pLT%mb8`HL!UUssoepNzPGV0($3-wi2TW8DFSP7h0b%g'
    's6JY)&w88|0j%3WnOQIEH*(|UC8cW4W@M+Dy&^(%z(=)Mo4OHPT@QF7?Xc`z@(mh`Sb66?3{T&VPj|2Wy^XA;E_?{?NF5h=*wjo>'
    '{()NiuFdlWO)OW83gdhCajHB&ow*X9pP#1xugN3Z8~cBaPV)X%PMne`u+~g-1J9J+cHOM|lINY1E9Dv*cm|-{_v_gV4US#+f$h8j'
    '2<x^kXT8<f7N~^NB&G_fzF##*g+H-KhwVf1xgZ?fxS5s2c{<(5q{H*><1;tDS7~4>Kv6|<8&6m!-kREbm}`F|OKf(~uQvBJz8>!9'
    '6aKRoa244)M4+JY28nsfW<j8B+dx2IWZErd@H6v|Z|;oQ{qWc}cql%*cwR!ngs%yy%c2{s$$*j56v24NQ(t|2V+U=Zr?;1SCY@hK'
    '7WAnK?72?2JjctK^XPVz8pZ`a9eyFgdEWJZ!_FSuS@)VA!;@Cu<x`eK=n)pJYc17-or|8@{2-+fHAc;=ZQRvk{qbF$k{&VQhYs!K'
    'OLZKOyjtL*cb5rNvk!9a9W^Ho+ZHMS_3y@yZ|$1cHOn)ceFwj;7V*32H2o2rB9v+%N7qBWHvA2r<vCqHd|NBo*YWY|@Vvo}Mw)Dd'
    'dE1-Rv4JMYkOqJ;0)P_Ng%hOh@ozX|r>k%meBJ7EiW0D$sQ@6h-3pm5DC1dEOhHnkdYH2G@l8D+zO3ws11X5gcgIIbbD@}W59)`e'
    '3W(b+W7qi@w5}$Jt_KERP5&GAwq`mz+U{MN^FG>Z$gjP#ry5ofC0J;!M8rl)GxYgy_z2#F0GGG3=pSQ&f@GyOprH;d)D(@nps(`)'
    'r1eYP2sdu$Z4aNXyDIhjEvold&SSt;otp_q8Bqdti@GJmJb8QbTl~JO^`hKh-2`-nob5gw#Hq@sDDj44!F9)?450#I^M{|$ImBOv'
    'bjqSoEV*)A$fytyR(uvQ9)uvOqm}p2&Z_?CUUqzD1x8Jf`cN`jC?npkPWvbyrfz_4PJ?VzKfC?#R?hXqUq7~u2#`g&w6r=W!w6z8'
    'OM)|`|HZ#mdSTH~0f2vWYgcRuC<yQo74fy`d9*~8S@OTU7;vU&ZQ6jxvkTSae0T~0(RpX7NN=r(6_6dKmu)O~(al-1NjFq!+f9As'
    'Q+)=3XiAtkoLpHmwB<E>*eYUGX^N1dt6SxPf`B5g3@)>_(oBk>pltKH+5fwDHk$N%Giruv(ThhHDv3^dH9WF~lnsG8*M-RYpB+xu'
    '-|(<(p%#heEl6BL6vcY~&_q9sXlX)v8J+$RJx)JkaL&g`EiTI(?myq5>i;0ox{H6d(XX?t16*SI#(kE?C6tEVWl>a3IR;a_Y=?At'
    '*`OR=#$@_=K|9wM=#oT;suF`%#XW|0#hEDuJiV;)@-nA{XZ_C`z23eY>wsCtg`luN8Ki}36>X(1RYd<pG&BF?M+N+q9s(8rJUqP|'
    'D5oUKE7Rp=gF`MmpE2*C!LAZ=oGhR8it0#<gH~BA+C|!B7nfX5ip1RCZ_?TFs0B3i5q>8esSKZW&OmNWQn+_h-8T^fes;(H$ATwf'
    '$mMe~1hQ9`8I~Hrmn77;J;jNqmh>5%>f&kR_dSotZ+E}Bwdd`W28>A-n%6#U;0TN#^$S)*pos`tk21q~oco_OuTR;^oPImRTU6gY'
    'zQpQ#61^<M31}n%So+{oEY?wVDf3;DBmR3fYkCe_i_XL2OK4}-2=gB+dU}68S5GbT8gZjKDDF7uGU;E#5`@vV4T&V`R-5*%`21Z}'
    '{irDT{>PUCTM-@AiJll}DsLNUczO_eZU-#}aHg?Rj?-}C4jvy5uix(WY-9?ywr)~t*EVjM=zxh+>qyQb)}sZZFbwsT8`<>`@MRk9'
    'wNbpSf+$LooC@R!`NvQ+<J1k*4y1<Hu00*^-7m*e3V)_OZl8S;;Xs+F+4|9^?S?5dFTm@;<ReJYWA0@6^R>HK0pq(bNyB}s<%sBo'
    'VjME*DG0??<YO2ORhOEDd>WDrgHx65-okngcD)Of0@CDi5zvBaR#(VYODLtI{SPzp9$;F<?sxJ3k9VMR@oi&CB->6}fsvSz*ZQ4v'
    '1i)6P)lOFxx7Y<*ujSq)=k)xm?$zCKdc8mVzU$e8Rby#=E6_<J<w4_7itC&Z{>ylU25pPBzHtj*9$)Xi;z!=6=M7j>PjOZ});ZNS'
    'R(6|LrNjiJQ$}yCz_If-Qua6O11Z||j_SU_Gt#0F6%fa8NSkGew%;5jQ*aR~a&qdLvdsUU4Xpsvj%IX#;dSUX%4sR4S?8BpqNYM7'
    'RY>s)Q}C|J=EhyQxSud1o)5qJ+qb{Fn0TpzP*eI!4%ACcfK089EJfzr>2}Q_i`GIYZrslaff)X{7to?cN{9EZ*uO%m8RD<(C|jDk'
    'j_!PoLXy~cRFS{8TK23b>RUgntM|j(Lg1KaM~bdjOJLDZNqA<n8eB-7B;VyvT}6JrpKr(M*Igg?&_xeNQQek#gR6tT<4Ox5e`unX'
    'U@ge}muc_9=W200Jj`3{OO<LU!vwP_r%QK6kw6ia<|eSSTyP~qotoX>^W$MUR-c!{?=OM+ui)q9xE7in37tGb?=i~apbJPR1NDF$'
    't3hNPZFk-Je^RD)Un|P=A?T)>M_6Ogr&cdlB`Ogvk=|$<>^?x*bsKpKtCgqyn;>IS3TZ0_I{-vC@RzB>?1m(UNG9(HPysJ{H{riE'
    'h#FVi@l~W$bEuGkVEu?f<WiM>I-g_}OTs0X1|{i@J2>S#yProWI#js<a}fb6;`PB1N94qOeu&}93aO>5cHi~C9sTXyYH1YJ>PB>u'
    'R%N<(r3f$vg)NJe-=e}2Iw=KCunM==9(OL-`}iF?bghQA4}k=>1`e$&vaE4RuuvBU#m&}&1T%m9kF-mArRNT1h!5U%<wY-jXq*a|'
    'L*s^*=`l9y^&hsDT%~Alb@_%)xDN$IuSc9G{r)OT7*jj}!py1D!1b32Luo7E?9)l>Ji(oEfIDtQ5glvQHxZDmWrDxgC++rB?OkmB'
    'rN?tSIR4|^>EDnU-0x_+259Q&&MI~`7%k!pQb(y=_waF(9JT`CW6o~b&fy^%zc?4;>%y+<?(ube<HB6tlaTN71>!;{z;_d{XV$sv'
    'x|ZsOz7mYbWvcklo<iM5FO}|HOIyq}rX`_8Xuu1gJFwJ*&dn!?`W{SE*1=vIerAbu#eRNh-$)OZ^m6!i`I>SEVzASXD0``c<F+CJ'
    '^mXX?`hY@XCjXs>TXuEt>FD;Rt<dZ(WYMIba`hb}9}g<W5>kX{#f9JwU;z)wZ`s4QwH>G>v9*T+js<;z@Bo;kkMKMfwlh=ru^+J*'
    '?RT7S*+ba-*u&Gj<5?s(QyGe<#I{2{2J4bXPGN~a$}l(N3;>C#y=5O-qfw1NzUsm6Ivi^5UL{Ov;L}Di#B7xEbM~+!?V@gpTdV1B'
    'Ivgulb9cJ8PG9!r_mjDs8}*><6?<z8kPMWIvxE|W0XW5}Nw<AHu=(Q?0N}ive|@{(Ak|4`$V(6q-6srz)H@abFI5`Sl92B<RkY84'
    '!&c(YE@K8PR+?77I<1^CencLN7=sv#Io_r|aPDqyZr@9=GM@*BWdpql6chTLhbDz61h(Z(fp6tAGMbLB33^FNw`}Bj`1VMX_8k1+'
    'Q)_>VxbJV^i7G4}2jL-D$o3Z%j~3ckBL!kqJ2dI0*#8pB^m#`GP({rFHfr_6dCuXB=lT!~@RVB^fh{YX3I;gdvWe62nC=x~m-m1_'
    '7BZ0;cI224z=eRnh5UkiG|PeOcz5mo&u02Myu8V1hL_E6CG)sBStclc$9%};;%~+%ej^dbo&g}ts6D&a|8DYlwvGbfe%(L_5E1}f'
    'Nx!GXw~Drbb|v-#Nei1Mk0T(JZhsIvkzh}^%W({~q-JUm)rQB7BnkBsZCm=O<z7#nP7TissZlgg#Z)zUNddomBN4-=Kc@S1&fBKR'
    '7ZUl~%h%Nn;682FWuZexNoX>m%VnpZ2n0nIh}#E=LoX0AkPm;;o^}{}A&v0SBf<}7Lt&Qme*$||@u$5C8sLLr*!?XVnh#v}UN#u-'
    '1qu74m!{D>hRs(KM5~GYYr-CKw6Lz0DC7Q?9X+Lgy>7*PWac<JA{;+2CXbO+as<NeuA+V0k=zo-RP9GMbbtJEc-V!tG}>gYz!VoW'
    't4k*vT3yNhgDuOR(hXS!=jEe2f_^-QM&n^hyABg{BM{uRkEmPfjrDn>P|-siXGuf|nB7Vreo`8a-&NCFd-8s~9W{xTQ`;57QK91#'
    '#LFx)JpA58N|EM|?&&$bxT(Itb{~ev=dZ_&T@me8xPp*f{mv#FRpKqqa?L6j7IP59QMCWIUA;cuABW3O^Aae$0-lv9HZLC#r3hlq'
    'g7~Zx9Y{SwQ`Hn7-P6nQ*Yt3v&0bEnV7S4GozyEsEgL616phev$e;R>;Jt|LjW=&-o}U7Ze@ZF-jfYK+pleInNd1EH0?ora?ZVEE'
    'SqM&JSFzYdA-_3P`UladxcmC@^0+H735oiq#mcMT)gTyDSf2<9?iU<OE>sQg*1Y-XhMuRV!{eT-Usr2v*o8tOYV{?Js^kv{%PUm*'
    '%^f6Eq}@_{U_;w9Q$3PA90*jDb0ITU$*Qi|BamqEjdZyXQPtzkAN+j$Hi*;f_3@|I_vLt<JEsF>3>I$WL@P#4Sc!Xs{wiT&GZDs4'
    'AKcRYA*8lD&^l#GS0$=up4<zC3>1s~x5PDd1rVYOHIIl?{T=&J)uh9g5l}eT&Ai?x7lcfNv<>?zJ~SpW2xdhz1hr1H4{j*rO#J0`'
    'MQGwaObG;^%r_0QRc?Vd@qG~G!#!;#l7&^2w{GdgIQssL{h&Cz{Oam(DXXOMOb7;PG)-t5eS1X??~RenOLdz4UE7MkqB8EVWR;S5'
    'ZQ*3a!wEAPYjNUU-|+?Oyj{p7C3o5VP5WB5?QOy-Izb#o$Iud0xXLbDv@OQfomdHtY-wpexS_aJcUW07W{GgLV7)>^9q3LwqK{sj'
    'G8H`sDJj}R`3HA%VmUtf=w2`&H<cAwt_X)xjf#?$PJr|(4_-HMF^9RZPU3KZY5Kuko$rs=hn){g#}+Otzje0{cxN?rQ->!KI1dOO'
    'Lm!;Lru5creL21ygHtZyKJRTK+eTy$!D}k0ud84=B2*$!j0ym)MS}}!jM1B;cOVPF#|_x>@;5f}-jMMN%^Iyit<+d`x%t!-O~7RB'
    'O^xs6){WdB=he>YWFB=H@u|XzoK_Eoq+c}vE)BFgHIcSAY?u8_MD7plC5oZ*OFD<|T~`U%ArDMj@rtSm3@HPVD>Nd!s_-Xk6-la-'
    'k8NxfQP1m_HXS!x5s{!t4-qE#+4d;FQxMBB?uZH%anTB0!J%9CbcRL#d`#P0YVuwMo3}$q;-Dl97nY#z>dQLHVq_fZ{PqIGs_gd8'
    '?{6nKQb}RMbR=Lq%?Zx-oSNI9+LGU6rlI-<+5G0T<lz{Nqd@cM-#xJ{#&7OE!~36ttC&`yLU0OF7#2?8nmpu8yl`%=KaOh-c`Ao+'
    'W?wg=B1H`&21L?4jLBl?28t8}A{vh=rZh~z$8_@z3tEh0t>zc9_aQYPt0AnCL;o!jaL3W~k3XQ;n|MG~4q2O)kL>7d4RQDKHC*>D'
    'Z-*Ih7JUlKN*2Q<t+&3eAEs&ays%>^8gEXG&Lx>TNOVLv+$J4_HrKa~eGjwhCEOGYjt;qZp?grsCR<I7oA0spCY|@)9fg}+TYy;`'
    '$9(y#ToFjEC9j*!T1)4P*$LUp?R#18c+!r&UprA^CCB$}RE5<9``|xL^r5n*_0++Tf0*~td~ip<ecNI15#AwC7lWUQRKTe_IW(rW'
    'p-i|;#;wc}>tVV%5BjZ(#Pzp8)3(xkBd>sHeL&V_jJ>dQ7xs|utf;Q}ODmK5;R8EKzXxAF8rHjQM=jo)EX3ep#2cECOQJe7bjQu='
    'UnNwSnB9G3Q-}5Gq`i+xcLUKNT#*rLP+P(S595kOTonc}Fpw~0Df^G@=(wXEGwvs{vS99-L^9*g<_hVOiXe=N@XaG4wzor`v6Gj;'
    '7>-XHl*1~L^)g%?TI6lsnPiXRvw3N$D55f4LIU`KeVoaF)0W;4%?`7ePZ<oKWe^MBN%Mz&Tsem+icg-Bc1$1H%J+Lp1l-7TCKWSd'
    'N(cv(myD&!nC9@U6bPLXRlVEXC;oSAX1hBG01LGcy}GZu4FpEJl4=$F17x7@OFTi+_<_xYyl_K1C6tByCEWGc`qgEa?IBLu4O3I^'
    'W?@o~usVHY7cb$~c^4$EO)N?|94%4JYUz}O)P8i0g*%8{5G6roDxQzT-tRd?!U>`A-!OaPufb~1SS?)iUc=Bc@zyj|s!FCKK>MTR'
    '<}~Zi-1Ba2Y;FkoxnR>Hg5HtKV5eSG%ze_fP;xrSK%a1@zvYtjU_vtiOF40DH^gsRZ`=o~7>YQC7aOKA{K*v=<NH*?m@@Mfu+!r`'
    'E1oxlgY`de_O@k`Lzq*{@+Q!w)?gjpXrqd%m)K>|5MyDypYniDdXm8YwLkF&qU<(k!SU8e!n}i~R4vveI1`Hr9gal{jc%dQP+tL8'
    'ytA*hMA*G6GWaQ87HeSck)*^ryR1A|!xmv=r{UatfNgd2uFlPqz59_0gD6L`1)YKT&Nbgi@No1AD_v5W83ujj`OW+Jkwv+8Q<6Sx'
    'fIO-v6lGn5@E8nfdVKV{VNiQ^HdmxuKiyRPv;BKoTi-YU<lX4w5>vn-%qxq~NTM!MXF)B`Zr#)LG(3N03;A$-8MgJ`U?tp{J~R|8'
    'JK(2C<YE6hV~4315O5WI#TERx|FWAiX0d-bkT=GC)b-7qa*i+{3oVGmd9Uy?hiF!ct(#-OUty=6n+jW@8GC}D4(~rErLn}%%u+(@'
    'W+f_9CP^OV`D2@kYIwI@AD@+SIhh7Zj>8z-m_EFpOp)9M4j#Ipvbl9f-;tEv8)EEQj1%E$o#I}NF;1BQX>vglL`*{eT$X(Edy9uN'
    'JnME}5g*mNh3rr*T!){50j<(6{Ze^q&7fbc?q2C{-O;)Hlux~WiD3a7P&||gm)-2Ea4%s&gPe?-3+Il;SEJe@u_BagKD?b%JLkCn'
    'deeIg*G-2B?zF@;XVzqBCsjM3LYQ5`MH$lvceeHh_U<WW4c4LX(wif6kdbMvpe(3Hs{q7hl3n}LaXnY<>G|vHOC*f@?-S6efRu+_'
    'D{5ECWl6Kg&5Jlh1*O=a`B1#>-q(2}>(PFGi<r~vY9#%Fw;+W(Tux5hUJ1;i4l>Bh+FV1?O$cxGoq;da65err|B)RX$6q8(s#IYU'
    'xA<Y+Fv18!B|2AnH0J!cZ{as4l*7a3(7+NOyIZbFn0~USzx>f=YH6aVH`RrSJtrdu8ITrEOT4Zb)vRv6o+1kC{v9Q@-|17d;^mV6'
    'HNU)!MyY^MC^Mi!=y>EKON0c-SO@$b<N9OW@l(r{_cn9xcb}ik`R~s4{6;QP@N^2-lRyyI6!3_UcL&oJHy!SR_lDj1;jL`FA4fKP'
    'Q?%eT0mm}TsY54i2fiy_MqNySO;^OAmth1^o(ab5e-3i*^9Hju#z*j4lsGrxjE9B?5nF-~z#t3<NLx9kDSc!YTTennF^3@B<{V9&'
    '-W21~iWpSFAd=ZDY9gPUY=0VkI+_oM_<-r@pl|oXA1mp4Lu00iJ;nfThH`aKdR5E~+zB~B2@QC!)$Ui2p-%fC<r|*PR(B^A$yR+#'
    '?uCFEQ3Rl|gd+@08v#mlAAb(rJ2ORUxo#V*x$mBa$O7-a#9z1i=wW(GQ8P!X%&dt}0&#800<SeRK!3)VYS~YB{Vx3X&l^^3;Vsg}'
    'TmYP1zy)T=7%)X2R}KCw*{@E+&@|UAetHFQ40gQ-tO__I6FQ_t)+W43wWF}W@fbO%hc?#`!s-fr+*xK7`k8Z0x2@$tiX}8=hK>C?'
    'nwBX<Xp2u07j>>bHN6voupY15#2NN{I|v&NbPDYh$Zr@u8y&I)El<JCS0?CIKxy28yu0!|>N|0I+9wUnV>-&L6^C-iGfN$dKwU<Y'
    'm-mc!)Ka4x7?!Tv0Yb^JPMqA&4<I&126R36BEwKo@7>)_q#{nnfC<L_KQ*1ZxQ$hkvMmJ}^Uxn~u^`k@6%s!POqeWn_zIOqeDJ=U'
    'm-@=ra1PNwJc3;oYP>A6(1vy~SvSI?5pAom4CaBd8T@Emr18o(qNg<qmGOmcEKdWD%Fp^MDl8x!pu@~B9oi`<H3V=>FSvDGxBTlt'
    'ruXu)aTsaY{5qcTabJSL^ow$OP|g)7EJ5m>0<bIRtJi-1_hG9$9TRec1gb0uWh{G$VC=?JCY2tu5zu!YTIk(thdcd=*7Pl`OJZ(8'
    '8uxfkRZNx&%-2BIA%p<#N_S=m&Ld!m<#rx36zbxGJK0Jdgg?cbvIzq>Jjgle#za_@A!DOf?=4EQr5dl_My!73dhMiE81mCoNKrS&'
    'glCWq=R5aB7$t-SSQ+>-<mrl+6Oy1$!Q=kpFR28dyd-+95c4J<j^Cf}ql-<&|H^3Qm?Va(E0FqX@SG@ho9gym{c=34x{6ifaktzL'
    'Up8!+qxGys9_*nxlmg+F6c>F?B`o&}I~YT-iraT|(uHDsD09DTP03-Yx5Qv&E`LH6WQnKP5(=0gee0^lOa^1$``fpJwRof;KEFM)'
    '7nUc~h7Bl3M=xCR$})5&e8hD3Tz2NLbulg@RID{`lC3Hw1;D<JY8te!e%}}q#k-=609uj<wLDh55o8W$20aIwl*NqIVha{czpE41'
    'Ui>Z#!cb-h&bW4*SswD37GSe>ShH=*3b4?Ra`&n}i;Zl;S2&MT9utt}P%xHZfu9F2%3bO!RWkGK-zwG5EvEls)Wxmy*DXVvC8)8H'
    'N^m}e5};xhd?jW>Gzkl^Gt96?d&+mNe?pr#3<6`is>T)&t_O^SyS;jbH`E-R3Xh${DrL*g70(KRH#O~^UYltMG6I(roe8r*TC=i='
    '?2+y)x;9g>_M0|y>9-vmpU5_#ew$Or+88V_4Q0$rj@g^kleq8oDpcSiWE_<dxSJW<_htWmN*9mPq%FI09&|dIMo*X&p!3R!ZVa}4'
    'Fb8xNlZ4I4Tg=y;OLJuKCH?v6gQ<DE{L(oebU}oQao<x&A<8hpqZEO4Vwymw6xH)}8(4)r8^f+pop2-gv<xv2B!JW^T<7NSD9o_~'
    '3`H-py^nmIxV%9`rDIf%#b7I#iXg>zGlq`AS8Sms3NiI{Q`B%c24Wh4`uE4_?&bAi%Udl}H|{KGEn+ztSBfE>G}5-iwme2mQ3p+%'
    've#I5Mb_f!ZjY0b;n%A~B9swJjHHl{R&z{-p@-Hy$LJik9b(p1|9F^)4rZZir#(&Z=@0-X>?jpk7ZbIur*#z{v$CjVyIn|*cPxJP'
    'Q$5)e+-;kWyMf#Y`aDBStTvoA)b9XbWCpnv8lYB82sQRB4b)x!xbBx*r4IBoGx5mf0iIeUd3?{!?V|o%Uw>0=+Kc>>9)4wS{u!$V'
    '4&&O`@X0eX!w8F*1BHH+Vi4^V89pBZ1ee(iO&{{6r0H$Z)12@a894?gZ8?0|DEsS}ssj#0Er<CKdB_2zACYQD=p<)gxiRfr{ms7o'
    'ZN{`z=u6so>TufC)sfnDeZ+LZ&@jH)b+|i1>BLWJ!G7l!RwC!&qOmQ?8((__d!*wb2wfr>b%v?}|1LRsSrjLm^24_k&#lf~FPk%?'
    'Mh}r%jE08sdEO~t4b&L6LoD}LoBq`O`TdozeB(LogNzfvMOd(`V^Ohs-4sI|nM$+Z1#)ibuGzwlXHHqc)xbecYmOOq4mGZ57wlCQ'
    'Rh1duQ~3RDEc?wkv0=A)no7~DbuCu>3H%36h6O#9j7X;|tUC2j7fsWxMUV4q*owS9{#5z<<In8H3@M&Wi*=mdnHj)KaIqp8M3~00'
    'j9Js074vDu=hY(mc~@P^SW`2q2)vAZ-B^SikEivXacPi?jFgU^Y&-5<_%W2cMl@_Foiz=DDd4A#d>f^FNRl!E2RSBc5El{p4EZL@'
    ';`_2|Cwx=z&A$d}uV;X~BwA9a1zIN=QNgrBKojKOX_FKFebtrhvdb@qJsggHn?l1x5wo=6#EiX)Aj#fA8-Wcg@34C3%28Gvwz<_!'
    '_#^nE9;XmxrI6`GI>h8Rd@+5(Tz~Vt-@E9_qj?kCP`8B~X!DuNzSL?mI~HI#mwH#&a}?XuoQmp}Yl9jx-z3t#ZQ@LyQ9EuaY^wnN'
    '+>)?Y0v2LTopbH`CVKe>9mmgCOxD+}yW+8m<;M+mZ>J@L<E53@MeGi1AP0<DY#U;zaEXzi%{$kAQx!_dE-&jMG;$~=mog#@XB?fW'
    '(5jF)8plVMkrRf^-Ogo~`#&}uv&=n&X~WnBWayq8r(vnA{V(YqsZfb?VFf#vJIt#E)9~xXK)C?awee$Ub{2Sq9!nP`Y6sZ$w1=>p'
    'l>+WPPN#;;LwZ#%Ue4&@>CiARCas-{ncrXdB~x!3lZ`v0qzKEQVei7fynefUhU&02jM>*z>Un4p_)QY@Hj&qc0V6N6nBUUuT<<i5'
    '?C$v+1mfZY*2Nh@`Wbr1lA%*$9&jJxCMj_aii@}*1z7g3`$oUreziH0T>t@$ECox4h%yG&qJj}2gSO79-HeOr>Xmm!Dxa**3D!aK'
    'qbn&!7?qaV-$oi?+LCiqH7=We*x%Pb9)I2FW3J6w7d$KaKJ+&u(KKHTHno^x!TB}XquLuKV&3|OBFaY-4#@=BE<R#4K6`EeaJWbz'
    'g;ky7T~~Y8d%b@-taC~)mxV?zg$HfW@<PB1R_mjMAM-bX@r;|bYl_|H>22`mGFX0}@)MvfG^Ox`4oEphL17Y@rNU*8Hx~>-)eQF8'
    'xq}}Zl6Ng{oRRc~7Z1WOH`VZ?4FnIE=k`m1!sv;a#ISSuvoA7d_4}8v8)!g?J$TY`RHT#9m1LEqJ{6z!;et(q$WE%VbK&O+ytDx-'
    '!R+0&GZN+$UZ^}TtAHJp2N+l?)CikxdCh{J@#cq%cMu&e>_vw9z8$SL!<&Zi_7}ED>fmgy!+!U=!K8xa?Et93hN0F~4uhiGKp?_t'
    'SOnuxK?X&QZRxSu8>PRy7yV#Fb@``LLrhH@vpjstPBNiBbR2Z*j63RROyLB(_YOW`wm|Yf@Em{L$lwJ-er3VU0zJgMDmkTj<%=L='
    'JHeae|FAcgKKEnR{3>n8UaK$^lzTMh$q6GI_J*)?T?v{*grcZ|G3_l`PEGF1ztuBk54vz2G7(A58922uoKgS}H}VYtP~FT|t$2qs'
    'bMZce!17h(U>?(XjjV84SRPZhh{_*Ht<kt6FS~BlQ^s?6KJL)-GEk)c_7jVcPPM`4iM~Luf^wNeX5wld%H6-4b=hhC%b5@NJ0&2O'
    'GSW{U)cRGe0uK5<jax_D^vr2*7<qkMp~Tn6Ahc|B1Q4@5R`$f<#3#wAec5US{g3F8KvI{8EqiZ@lZWQMlEGJMu2+dhwq}<zGBl%&'
    'Ip{3mR#X~%SFkDDTdtf8Bg07aY1rYeZ8}o0h@In@C9o33-OWwRCJ7NnzS1)1t;~Qb@ZtBT(;NPL=dY~I?>0y?eQ@`*o9Pvs7TUnf'
    'm5o;$BUz$cQo~RW=GQFzHmT}7a^&(+tHY`r$<j@Qf9~f(0>bN{ia{1tj0YFTi{h&F&rbdOtn0%h%aafB9VVF$XKO}JP+#+yE-EjZ'
    '=(F=px4ysZ;EYJzhnM*i>lbLjhDRsgn~u0lLxlAmo-`s=9Em(e_h1S`+{R{;oA8%C>{{4k*4`fjY@@Bwb3)bfVMmKqkBDPX*c_Kr'
    'b@jsWZ*NdT7;C^YWh_{XN@OOaAYJV#(g+qnK`=BIXX_3*&5zl2)WSN)wBH3#>Qi#!2#Ls0)jO#V&+P{LIjHL!D?T0`2~oBZF{M*r'
    'E@MoMtYSdHTK*f3AukzG6{C&3ZFBUqv6VkwP{A9aO3*Z|hO!KH#vCS(I_9cj88!eDG`-mbI9VvHM|SPcpV~ef@)`^XsZE1?IEAaN'
    'B9*O^KNYbf6NyR2>_fJee%2}eHhiCp`00(5@ZEiH_v}Iv>mi&9V!~Dx(`AE2Zifal#w37xrYae?NvV4_v}d*<Au*#=IyOZ$QBNDQ'
    '6O>=FQ?M?ZkeCvHwo-g(JNu?cj%GF)jZ71U$`L(wz!wQ!9_o<NrXtjrn{wyNJ6WeNJ`RVCv4A<BXfWJb4;Jx3O3_iNlhK*R)C408'
    '1#8p3<-8Rzca)%e>}$>cGk$;>Gpks$7R7YBqAUviF(gjd!@@y5>^!Y6QGn9Cn+*|9VY5QeeI3KDcL?ph&TtpndrCP2QXEZbT;*)+'
    'UVBx-o^IIm^t4Wd(6ife66HpXw=?3ka5)K%MTnPqoGC^<aQLs>hbZ-mO<c(&>S4WH0AlRpI;Wm{{Sb2?QFQ|eMmyu3xjpva#~u9g'
    '8VSyxpI;=iOREr)h5;1<0-Bw39{~IuvczayGxfh_@heWBUTh!ao|TFjl|&Y5WS?MI-hnJN?E**bu2}uLBS;M@2+7}RdU!XMY!ZP%'
    '9*VjmrcO_=JrjGjE?ac)<?e^M?fd5gA;&{a%g|$EcX{J6C`aojBNgvMPoZBAjhn9Bz&X>~GaV`%IB-oOtEHML*H3>8TwZpM8bMK$'
    '!o0D%aSQv$LiqsNaEnpP>O;7vQOkg=lAtk$8C2^uko?+h>>r7`g!o;&@&6JHhWAewbLs(|B2kokr8;QX91iu)4&KNzm#Yq=udovk'
    '-{gK2Ow?2XS7DhED{z%5qY*o7f+qj5g?&v(M177U#h8#OO(Asw!e1f576t_C5C%^;-&Az}*VX^ZG+cd1HZow~MHuB6_z922*U+hw'
    'f=3@G<TPM3cVabtXd62Sk0?pG@4_%Lu&gaHET!%80-7LBH8hHWns)hz_OW|HswpRmpgtfZP6UjWits7#Ba_uj<JP4-T{cZ!|8p}j'
    'DD`gN<gK_I*rgd=OhVN`s6}nDlH;WgYNbdCYb<y6)qB9Nc}QQjHIQIa&p$+EMfkrEJQ`}o85k#(PXoz#*}-Qvxd=bqz;js2ZQU1|'
    ';gKR4E2AILhb?iiOj3BYa*#A&h54SDAJ>M6w;`9ihWS~hTeS*Vc;=>+1+tD#0(_B`n8ikOef6n)+rsXlu?S@g&U+P-7Uf%8uh%%x'
    'Ae@<FnyvP0jJ>&WAK&M*?lKxj$u*H^DPo#+5vDj}q?2+ATpZ0_)U%kySq#^1=G0o3UQDP#cQG_-<1R(+V{p!&PRooxJ>$bUYCu_b'
    'OjRBROje22t^0@>3lD3C<)Yf00;=WR#)!c=&%$r40-QCg!DytoOS?9~r_DC)J9{~0*mm@=LkNc&wWw+o7GXs1)u_Bs9|!~S53wPf'
    'B&B(q-?o)KL~cfcQ_Lb{JI|8NHKz)l!bcnf#n{|AhFnAUt_@v)at2#l4GH`y6mHE3WM&DydM-kx4v33R6C2}4?Nv|LMvcE}2kv&^'
    'FC+arq8Qi?*_UoalY-SW6<!_RD~7iK4t%Pw+{!-RDz}4SEo7mHp;{#b+<oM>;l4{m@7tN1y1X{mUhWTHzB&u9=L_{4g64*<z$jX$'
    'u#WDg2?U@#0<@e&vkhXj!43Kf!P~ty%lZ<S+e0{#M)G^NJo#J?o1zLqQo~oj7rNc@_JYNTVudtN6f2@0nf>+Jt%&0I1;fMZqhqqx'
    'g2&^sF-{Gfuc;%=!U4kJ#F_SCFo{CC$Z$NgE6ZuV_MsRR`|z`?<S*?cjJrA<P=SLUy~0CliMJc;ad5M4ZP3Jv>Dmh9haSWFLay;-'
    '&SI!rDCuLe2tQN}HG&%~+M1GHYfD^bxiDV)$>MQeN8m=Tl<;J^!Y5{Tlz4M7#mt>gK3K<``YBi`_3iuE<Zc<0;eSk9=cNP;E`ocy'
    'gq?~(Vrr3~CSq@0eUHQzt`aVkVYdtb=d+y0JOS3Qo=z|`324WpErQskI=W#WR|pv_0+C_*6}VW1QjT|QR8S^zb`eXe)r2RTZrH_6'
    'Nr4uSwyr#w*bl&L=B@unnc7FmO8aj}&@i-DS7|4u-Q8Jvw^gE{BK0)%YE-D5a5|fL6%=G_Z=C|l#Jo;;gxBujIxe(An765D5##mz'
    'a&0=S_aUgdO-u&D#CABYeh{L=YU*?DRBjJDWK4$uUC-f@EE6WS2ryeQZAL<5H$zyoUHySvGw^+iju66OSQ-fqs9@k^f<Xjog>nr3'
    't?J?G^!L02-)Mx;U9+e4YiY!=!*vSLJVbLQS_WzmtcBaytZJh~C~n)x<8ck?Znnep>xTIQ00X-<PHCvuya5F&q#L<P(G;WKm*Apw'
    'w{2vl3+#C@nWU2aLXwFyGKvvwBWXYvCo`xq3F;oh53h|D53zn=i$R>g;%7_zyn!BQ@MST)4|&ktWdr)zY(Pwn$U{CGY`gL5PvzX+'
    'ysocI1cj%eSe>A&(Mb))JMy!AH8CL+@lZyTH@EHO+72_nLXdMFoWG140OgxD2(?%WXA0kR6ZYCgJKnaN6QyO>Mo_bGgIsDT*)WZ2'
    '1%cP`W^LG6>rLfBOTYRRt=i9Xe!f!!3SCer#*omMa*XgfHg!-E5x568FDoohhpW$(TX{T8$L~AY4y$3=C=Iht@LXxi$ecZ(Jm|M&'
    'C<a)n8m~6ovWwGu`I3&DY_>R><_V*p@EI}xf_)J}RS3H9UV`Q={|G_b_N<4WZsQzIm}taAg~P)Z=3=~!yH!I<Dl~;?!F}W4n!rO1'
    'grz}Kp^cZ{^hn;m<tsQUdKIiQ$QhO_=7ou;il-_MtD$^J+TJ)DMAFqQ+xdaZx*H-zJyT37s^vhMX4-g@`_POBmoEvV{Y~NibJKR-'
    'jK!7MUv{aN6u1kLp)E0kU#O%gJWxU9>R=ZlCWQ6yWWQxIXQJ)i=aR=@k|E<`N06YM={g1h&7n(F1Uoe0uA42_Udn&oKf&DJhtqNN'
    'Q_tE<xcGr$XhC97BMEdkSD?57auJ-a%^SU)F|Am3)On^eZx$1A^#FvBQCQ+|<C&O)(H~(%;~ukcz`iowrmL>s$js97`@`_6z8qG;'
    '|0W5?7gNX3fG)J)XpG((wg?$1P(p8T3L#kAT)QFv<@_|S>4E_sB$9~m(TBvHiH(`b>Tw|MPBGMyFO7I}?MC+VcVja3pzj+Dcwvrl'
    'E*cum-Rf9`MN><#i2|;Ta&Wq{+52Ru`oNrjV;2!dFdYL>r?;Sg0MdlpMTJ{R6&b;wg!{@}TwvJ#rOb5G^l{790qARXv{7U9TJvQ%'
    'PSfUvsmgNghZ6Oz&m#sxZVgBv-JWZ`cZ#0y0F8kaZ0BS88s|$XiBaANa^1BE$eHYVcUGW=3C~7pgFEdkc41Qmp{#-jh_jN%d~6s1'
    'FXLzxUmHiyV*0n;Y!Y<z5OVafx(eD~@G;yed<$eK1Cg^vAz&MxUS7WqMz$fdmLHz#tjl4Gz6^OTMml1khDACC4IjNCzFF)g_?(Zn'
    'x%T5c(SaY+MrasKL)YyKZ>r3gD{&JgmkX1`D9pdHfTJ%vS2wM`kBr;}U}{inA@2x7L(UbgSfFPPozw-jzfKB&?R!|=!%j{id!Xzf'
    '=PV8)10MD-M#st6``DCPuZZEBSl~h1*xJQ)5oru3UIPu1H$236W8z$5#tLUfb%4aCw8dB1TJ^hy#rI3<JmzO(^3V{ZciMXHO@pqI'
    'UY3@0j-L|BEE@PJ?(T8->O0KZeB2m8h@7o?$DqA<@suo{K5lly&7xM~r%iUwpPn82qo47X4XQ)N(O#0&`n+WRwMI8$DO;E#Xwj_}'
    '%GT1SF!SEM`xgrbgZ98SGyaY7D}@`D4r_`*?V8Huqy*x+&rP>)#od988zDn#O)-5KmP0O^m7$u2iHFO63MVmPck_p?-|)U1u*9l1'
    'DW$6_qiB09S+bmU7>4tUd}c;lc&YWfR*aankI+wNj#uUu8DZ(NO-Wy4B|fb&sR^5*(0-{mHNihDyC+hZ!;->wv59#)>JwJIW|hXV'
    'h5%8XW7I%BHXR>-SQRHZ`p}nQCn6PdV||r*I6Io1<~Wfbi4j?hXW?*UgwAHo`opR_ZwS(mykhM$gk6>T2Rpw82NSq+J2z<nnqkt('
    'CNBIR3-1`EgsaQtg`w-z#lX`Bdk7_CfE3gU<<1*WfB_KRTl!RsfBG?D|Mapo_FY~q3yMjZ{30MnMU2LVV@+`l7}O?C*SgB@-iT_-'
    '<@oe1dWO^)!~GxsV?zc6CNR!jA(x5#x|K0s-oR;8hdhGDYQWaK?<o7@dS}*TARt>_`pi2+?7>dI17@?n6BXpX(hx~9i{GfX7v^YJ'
    'EPKZLx7Uu2r16L;J{@vC?U!)RuZ>7%6t*N-vt2k?*RK5rZtvIvoC8lB4Nn!M?-fp^23m$`0bO(oeME|Z(eIvWRnJT8;gj-kF&*}w'
    'zdRowF8pHnCq6EwQOpRTtBYav%vVy-&H!KJd<&lFyE%?kenHCkw6-~+Y(GE7Ki)mr5~3#TDs!bkO4WKN7=U4J9EuguSs4)N`<(n3'
    '$9W!d{ro9rVE*&v_m@kfeu^Gqro}sZg2V_)Zs~Lro`P(;$a_SN;(bM#5cuisNB&%p@#Bxvb+CVZ2(4QaBvntUYM6}r8q=It(-fkj'
    '_h(hbYQd+Dzx%Xe?HgSwl5HdpuFvWPol2t!(e_jh+JrT(JB)!@`@411v%KmPK1cKx&V{Q#xjX;K-FNSR%jruUbA(Y^xKOh6;L4BV'
    'U=*U<CAbbC7<?T6?7dBV|GiJqmwnm}gpe&2K?gX`LuVsdK`Ex6ugsQEvk&13WzOBtPEfR5Kaaz&&gu96xDj;2*xd|Q6@Y4JpoOHI'
    'Z!wyfQ5cP&?d8Sx)sD4JGcI5L@8kcK?$>zme-1BSH!xUd1wUWHtq=+<c8srb9@e>Z0g!v!?avF+)9RWe)7MXDb_Px0@o`%P$q5io'
    'gs?S&LV=Jl#SkjC&EmbG81#Sys6Qot{%p<jUpM;PWa|Lag)IvgLT<CtQcj-%IfH=0BMEgYWgAPLvi#30gKoo&!3`FkmQ|o&A=8S_'
    'W(l8U$cMWfN-1G%_pLWef-fJ~a{W3~iY(L6)3ond^N~`MTgFbxm|#3NKc%GoWW6u1#u;uf6w7{yt|+|Gbtx0%GKqDj`$uBIYeH<m'
    'o$dFn$EWONYxZXo6N~un`9UU(<1AAT$FvLuq)adzWMeMt^zJ7)9X_4>2A)5EJuE!N;dZC-X^+Q^Xuyz-GL*d`_f}$IUFoo86OtSn'
    'm?EaKpaiYhv2?7p&51B!-e@-d*<sVkF@w<|P=-QQ^Qs&|!Njw){;7WIKNfsif#fZJYIZ*SP#U~W_8~ltiDJ=kX;OK#D%`MQGt!nU'
    '?O5^kag&*^G%OL&fu4O(U9{!I^(tEXHlfSF9ZV(F4ezZsr|`K(Z~jAq>+63G)2z*JvI-L}G6<=U(WHQthCs!=g6ds|;+qiHo6WCU'
    ')%1eHM$I(FN3SD6xoJtah7!CCH;WjNgx6u9Tb*a=s%1AXuqo8^`c_EQDYz?q42ICaQ1piwCYW(CJR`qm(Nisc`8J_8ihviUx@I)^'
    'U~yPfjF2??U#SY-sy^qtVHR)b)B1UQ`qwL%V>z7WB<~5h`iD3G3W?yYxXOwFq=!W%?uS8skz#7y`*+HFEAOF+5H2v65fQ{$&Ud&W'
    '{8yxbVOJ807w*SQq>8J5_1EKOnxg9M!;2N^6`T)SkxVZtDO&O-yrj%~BDTDC;T_{+!|#QI)D$1g81oP+Go^wMn|t*d9<Fz-j^W)?'
    'tr_~7J|V!!URD>y$CqJCu23U9J3)#@855FL5kh`P+XI)F)y&AUupsVtt+{>2X&0bVS3}DmfiPf*0XTtjs99aDAf3VmBp2Sb+@33r'
    'Jpe`knXU#|<OteDL-=4Q5jiI<Ys&~jpxe3N%U0%z+D9GBYM&Y>%=L{V^(+~m#aHZU>LUgi+q}2l8Dlu**xR2diyUMny<1fMVhJ~J'
    '9wR^wWxn{Yi;Ewk(x`SV_vrdo3~tOgz;&2`kO-$evxzy3CNh6-d=o$J2)}vw*LJ&B{FzAqFLB<u6_H2s6I1$t_=xy<z<^b7DS1R='
    'H^P+1U5lM2@@$ZxNTvFinaq2+!K8p@!|=<9edHsKr=Ft_@ZNgoxc>InJ>&I)G)-d>SZW`fS(msD1qTEuYm7?sXzk_w1Im2(_<V?X'
    '`e{8b&u<<c8;&h`7p-k?PFun;@euuR|BD|nS6TSCIJ)iCt8P!FFyW<$!I{j&#2)&7mnM0&>B}hfSWJlRy|917(wh47aalH;H6=-&'
    't=@}&0LNyUL5|c!PR~tNZGo0i4AcJA$pruX9F)Vy*9{J+SzjV8Vjqj=itW^_D)f4>KqP1yLPQ`Yhwoo`J3RPCy;IO%865(0mOQ4W'
    'g30s^*nGh^5SCb)Ua_Wi{&l}0+7A-aN<0ef*{J;F(I0%<j8fS|TjPuTPkZg6XW96MvGx*Vjre5pF!lh)InPA8bEZQB!Wm*TA(`g>'
    '#Uo?bJI#yDR--jxq@Kn|Q^m-29(BzMLdu*1YpIqd+rK#MQD^97I0?Ic-+-DWXkklBd@!z6InxBL0OJs|P9iIx6$xFs;<rCMev6f#'
    'jWFF9DaUumXh##&f{15kR<O{<a4U2#puuS~03Sf#``13-Mki_A#z+~8C21R)H)7Bf4Fy?J0sBz^iLbb4b5JzW{>9_Z@4hGOhb``G'
    '9aw-=3Ju2R9VE<}Jp+Tt_{><Y&E$1?eZ~4=6S>?AEN{W>)5_BPd=7DMfBN|(&i#B&7Y=8!>S14-&73{m`2;pWbMgyhm?=h0m58=1'
    '+I%Q#s-<rK_iy{phV#y?H_&DpS7;uN1^&?(P$G;*$3sweohX@HV&#slpUf!V38sH>??o~N5IbU(xl_WJhM*2Cgj&81%8)Xv)yh4='
    'G*m`(nrp{lJBk-646l7ZDomJ#5t)iGx*CuWha&nbd6Cbo-?8v+uuY(H7iFf|O1#2zS~(F@(PUy_+s6Sqh12Z2&`^xROy(e54w&q5'
    'sr{;uY@4_NFbKgAf@+JSg3vYvl~?QN-HPYrCiH0xV#x5c=XVLmI*r(CLkEae<j5_fH`d0WWyn*I@pVw%jgik!U&gzwpVh>y@?d?K'
    '5W}2a6p)~2nl@a6fd5*|3d&Tz`(cIP>eC5aPdsWr&xd85Vfb>`=x|D0-SN!GXnexxQLz*LTwF~9LNH@hf(M2!_Ab1c%=P#*<Zj%J'
    'Qw)(s|6$M?6%XeDKyApYH5T4anE&g7f2o--Uv^VWfA0LWo@Y4j2RTQI2}o1O^4ge1<fu-~-jz4u9}4XhxUZ~Yi3#1BM(h;nc)ZRA'
    '=Oq-8^UtRatqZPey;;tD9@gf`hFK`ymfFgkwBXVgA;|#Kra*^T#*(X3Z17)t|FHgbNwM{<yLj>N`X0f;!VD)xUkP?;i~@3lF?v>%'
    'sEeWrxAS*?S0Ha_Db-d@OhZGn5WoS74$l&EoCq7DSI_0S`>B!OPuAQ4wFLg_yJrX<EOev}jRjYpGc~EEmr!|BK_uO`U?9-nBHC?O'
    'Ig@Y?O3XT{JT;cn6k`kH4f<TXQ-osyedn4hk9bexO>fYcX@`f28!bW~qIzv8rw7oZ6UloPkLjm0)eGxxR9Q3zF-FM=P89440*)kx'
    'fh(-V2)a9_Y1!CZw<M18VdIxVAY%3i*@p(-6t;x0ES&8w+SR#M1G02eUb*aBR&zNXxt>Y2@X%;ZDJ_gT*R3IT3s!1GrWgccZrZ-J'
    'H-QndZ{vd4UzO3z2sI@PZwXu5S{#nCWGHCw7k2-#+9qKrJWHIRKA5crHxn+HYqNxQflQwv5Q-&Zi>0}0#h(q(`77kk<vZr(nC?fM'
    'R^s$!!QC|EQ}K#wN2jN(&G#+(Ed3mhmq$f{?9A@#f?gH}cx@x#RtL2iB`oe4Dbdg`SFL!ri8{yFUllUiS7=hI5U5rTZysX=ffN7>'
    '+Bdb$^~>&Js|M4-)D6O9eO2W8;4Ye`6FP2fP8BWWQrzgSTYlACY_QPO8z4SFBCp5jQL`}(!%r=9!75C}qI2C`x9&;Nu;K4eu#&)4'
    '!Ue0C^m?zA8A57Blx-zku96MdV&}qZ8j8bt)+24W;$S5?&BnTEztRYBHn1H%hmazLVoRj#%AKF?X7rB%7zDqd7-ruNm&S??3K`81'
    '6C<R&?W!gGj|2U`{*V6$x7Yi8'
)


class ShippingPolicyTests(unittest.TestCase):
    def trusted_main_projection(self, root, raw, source):
        """Authenticate fixture fields; never call this native D evidence."""
        payload=zlib.decompress(base64.b85decode(_MAIN_PROJECTION_B85))
        self.assertEqual(hashlib.sha256(payload).hexdigest(),_MAIN_PROJECTION_SHA256)
        tree=json.loads(payload)
        self.assertEqual(len(tree),501)
        self.assertEqual(tree[inputs.AFFECTED_POLICY],blob(raw))
        policy=json.loads(raw)
        self.assertEqual(inputs.affected_lookup_digest(tree),policy['targets']['main']['lookup_digest'])
        self.assertEqual(tree['tests/platform-profile.json'],policy['targets']['main']['profile'])
        self.assertTrue(inputs.AFFECTED_AUTHORITY <= tree.keys())
        for subjects in inputs._AFFECTED_SUBJECTS.values():self.assertTrue(set(subjects) <= tree.keys())
        # Installed workflow authority changes only through a complete enrolled
        # tuple, exactly as shipping_context overlays the reviewed templates.
        generations=json.loads((root/'.github/package-workflow-generations.json').read_bytes())['generations']
        accepted={'npm-consumers-sync-ci-v1','android-owned-npm5-sync-ci-v1',
                  'protected-producer-original-default-v1'}
        matches=[row['workflows'] for row in generations if row['name'] in accepted
                 and all(source.get(path)==entry for path,entry in row['workflows'].items())]
        self.assertEqual(len(matches),1)
        for path,entry in matches[0].items():
            if path in inputs.AFFECTED_AUTHORITY:tree[path]=dict(entry)
        return tree

    def target_context(self, root, raw, source):
        policy=json.loads(raw)
        lookup=inputs.affected_lookup_digest(source)
        matches=[name for name,row in policy['targets'].items()
                 if row['lookup_digest']==lookup and row['profile']==source['tests/platform-profile.json']]
        self.assertTrue(matches,'actual source namespace must match an unchanged protected target row')
        target='main' if 'main' in matches else matches[0]
        # Equal namespace aliases (Android main/VR) must also share the complete
        # native reader proof, rather than choosing among incompatible variants.
        self.assertTrue(all(policy['targets'][name]==policy['targets'][target] for name in matches))
        return target,self.trusted_main_projection(root,raw,source)

    def test_shipping_manifest_is_complete_and_backward_compatible_registry_is_unchanged(self):
        root=Path(__file__).resolve().parents[2]
        registry=inputs.load_registry(root/'.github/test-suites.json')
        raw=inputs.load_dependencies(root/inputs.AFFECTED_POLICY,registry)
        manifest=json.loads(raw)
        self.assertEqual(len(manifest['suites']),60)
        finite=[n for n,r in manifest['suites'].items() if r['kind']=='reviewed-patterns']
        self.assertEqual(finite,['documentation-contracts','release-bundle','embedded-web-qml',
            'places-native-qml','recorded-voice-qml','snapshot-qml'])
        self.assertEqual(registry['schema'],1)

    def source_context(self):
        root=Path(__file__).resolve().parents[2]
        registry=inputs.load_registry(root/'.github/test-suites.json')
        raw=inputs.load_dependencies(root/inputs.AFFECTED_POLICY,registry)
        tree=inputs.full_tree(root,'HEAD')
        for path in ('tools/test-evidence/affected-test.py','tools/test-evidence/AFFECTED_SELECTION.md'):
            tree[path]=blob((root/path).read_bytes())
        tree[inputs.AFFECTED_POLICY]=blob(raw)
        # Both the source PR and its exact installed successor run this test.
        # Authenticate the actual complete deployed tuple before constructing
        # the distinct approved preinstallation B; do not bind R to B instead S.
        generations=json.loads((root/'.github/package-workflow-generations.json').read_bytes())['generations']
        previous_rows=[row['workflows'] for row in generations if row['name'] in {
            'npm-consumers-sync-ci-v1','android-owned-npm5-sync-ci-v1'}]
        previous=next(row['workflows'] for row in generations if row['name']=='npm-consumers-sync-ci-v1')
        future=next((row['workflows'] for row in generations
            if row['name']=='protected-producer-original-default-v1'),None)
        if future is None:
            future=next(row['workflows'] for row in generations if row['name']=='protected-producer-seven-target-ci-v1')
        endpoint='.github/workflows/pr-metadata-context.yml'
        approved=[future] if endpoint in tree else previous_rows
        matches=[row for row in approved if row is not None and all(tree.get(path)==entry for path,entry in row.items())]
        self.assertEqual(len(matches),1,'source must match one complete reviewed current or installed tuple')
        if endpoint not in tree:previous=matches[0]
        enrolled22=any(row['name']=='protected-producer-original-default-v1' for row in generations)
        codeql=blob((root/'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml').read_bytes())['sha'] \
            if endpoint in tree and enrolled22 else '3a273057a38255ca368d3028594fb94227ba7c3b' if endpoint in tree \
            else '6d55d0fe4e9edc86204c66e1fa3967681793a2cd'
        self.assertEqual(tree['.github/workflows/codeql.yml']['sha'],codeql)
        tree.update(deepcopy(previous));tree.pop(endpoint,None)
        tree['.github/workflows/codeql.yml']=dict(mode='100644',type='blob',
            sha='6d55d0fe4e9edc86204c66e1fa3967681793a2cd')
        return root,registry,raw,tree

    def shipping_context(self):
        """Use the actual complete prospective installed S, not source-only B.

        The native inventory includes the new reusable workflow's membership.
        Its protected certificate must already name S; this fixture never
        rewrites that certificate to make the shipping positive pass.
        """
        root,registry,raw,tree=self.source_context()
        generations=json.loads((root/'.github/package-workflow-generations.json').read_bytes())['generations']
        historical=next(row['workflows'] for row in generations if row['name']=='protected-producer-seven-target-ci-v1')
        self.assertEqual(historical['.github/workflows/repository-checks.yml']['sha'],
            'd9fefd275d9e3c6977cf9350a1945a6bbe5051b4')
        future=next((row['workflows'] for row in generations
            if row['name']=='protected-producer-original-default-v1'),None)
        templates={
            '.github/workflows/project-tests.yml':'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml',
            '.github/workflows/parent-qualification.yml':'tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml',
            '.github/workflows/repository-checks.yml':'tools/repository-checks/workflows/producers/repository-checks.yml',
            '.github/workflows/pr-metadata-context.yml':'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml',
            '.github/workflows/sync-validation.yml':'tools/repository-checks/workflows/sync-ci-selection.yml',
            '.github/workflows/browser-client.yml':'.github/workflows/browser-client.yml',
        }
        self.assertEqual(set(historical),set(templates))
        if future is not None:self.assertEqual(set(future),set(templates))
        for path,template in templates.items():
            expected=blob((root/template).read_bytes())
            if future is not None:self.assertEqual(future[path],expected,path)
            tree[path]=dict(expected)
        tree['.github/workflows/codeql.yml']=blob(
            (root/'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml').read_bytes())
        return root,registry,raw,tree

    def bounded_context(self):
        """Seal a small synthetic repository while preserving real definitions.

        Real whole-inventory shipping/legacy routing and protected iOS proofs
        remain separate. Repeated mutation cases need every actual authority,
        required subject, CI exception and currently reviewed import root, not
        thousands of unrelated application assets in every negative plan.
        """
        root,registry,raw,source=self.shipping_context()
        policy=json.loads(raw)
        required=set(inputs.AFFECTED_AUTHORITY)
        required.update(policy['suites']['device-control-plane-full']['native_independent_paths'])
        # These existing importable mutation subjects must remain edits, rather
        # than becoming new import names in the smaller synthetic inventory.
        required.update({'tests/device/self_tests/test_voice_roundtrip.py',
                         'provenance/artifact_identity.py'})
        for suite in registry['suites'].values():
            required.update(suite['closure']['required'])
            imports=suite.get('python_imports')
            if imports and inputs.python_import_digest(source,imports['roots'])==imports['reviewed']:
                required.update(entry['path'] for entry in inputs.selected_entries(
                    source,inputs._import_patterns(imports['roots'])))
        tree={path:dict(entry) for path,entry in source.items() if path in required}
        policy['lookup_digest']=inputs.affected_lookup_digest(tree)
        native=policy['suites']['device-control-plane-full']
        native['reviewed_reader_digest']=inputs.device_reader_digest(tree,native['native_independent_paths'])
        if policy['schema']==2:
            # Keep the versioned main aliases coherent in this smaller fixture;
            # shipping/all-seven source certificates above remain unmodified.
            policy['targets']['main']['lookup_digest']=policy['lookup_digest']
            policy['targets']['main']['reader_digest']=native['reviewed_reader_digest']
        sealed=(json.dumps(policy,indent=2)+'\n').encode()
        tree[inputs.AFFECTED_POLICY]=blob(sealed)
        return root,registry,sealed,tree

    def test_shipping_five_controller_case_omits_device_without_running_any_suite(self):
        root,registry,raw,base=self.shipping_context()
        _,_,_,source=self.source_context()
        self.assertEqual(inputs.affected_lookup_digest(source),inputs.affected_lookup_digest(base))
        self.assertNotIn('.github/workflows/pr-metadata-context.yml',source)
        self.assertIn('.github/workflows/pr-metadata-context.yml',base)
        candidate=deepcopy(base)
        for name in ('attested.py','postmerge.py','producer_workflow.py','sandbox.py','sandbox_host.py'):
            candidate['tools/test-evidence/'+name]=blob(('changed '+name).encode())
        target,trusted=self.target_context(root,raw,base)
        native=json.loads(raw)['suites']['device-control-plane-full']
        self.assertEqual(inputs.device_reader_digest(base,native['native_independent_paths']),
                         json.loads(raw)['targets'][target]['reader_digest'])
        plan=inputs.plan_affected(registry,raw,base,candidate,trusted,target=target)
        self.assertIn('device-control-plane-full',plan['omitted'])
        self.assertLess(len(plan['required']),60)
        self.assertIn('attested-runtime',plan['required'])
        self.assertIn('test-evidence',plan['required'])
        self.assertEqual(plan['required_setup'],['host-full'])
        spec=importlib.util.spec_from_file_location('affected_host_policy',root/'tools/repository-checks/host_selection.py')
        host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
        selected=host.select(candidate,plan['paths'],True,trusted_tree=trusted,base_tree=base,target=target)
        self.assertEqual(selected['reason'],'protected-affected-dependencies')
        self.assertEqual(selected['suites'],plan['required'])
        self.assertTrue(selected['full_host'])
        self.assertEqual(selected['include_platform'],base['tests/platform-profile.json']!=inputs._AFFECTED_SHARED_PROFILE)
        self.assertFalse(selected['affected']['reusable'])

    def test_preinstallation_source_cannot_inherit_the_prospective_native_omissions(self):
        root,registry,raw,base=self.source_context()
        self.assertNotIn('.github/workflows/pr-metadata-context.yml',base)
        candidate=deepcopy(base)
        candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed preinstallation controller')
        target,trusted=self.target_context(root,raw,base)
        plan=inputs.plan_affected(registry,raw,base,candidate,trusted,target=target)
        owners={'device-control-plane-full',*inputs._AFFECTED_PRODUCT_SUITES,*inputs._AFFECTED_SUBJECTS}
        self.assertEqual(len(owners),23)
        self.assertTrue(owners.issubset(plan['required']))
        self.assertFalse(owners.intersection(plan['omitted']))
        for name in owners:
            self.assertEqual(plan['reasons'][name],
                'fixed-subject-or-reader-not-reviewed' if name in inputs._AFFECTED_SUBJECTS
                else 'product-component-or-reader-not-reviewed')

    def test_actual_child_namespace_cannot_be_claimed_as_main_or_trusted_default(self):
        root,registry,raw,base=self.shipping_context()
        target,trusted=self.target_context(root,raw,base)
        candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed CI')
        # A real child keeps its extra import membership and native readers.
        # On main, a synthetic neighboring import proves the same refusal.
        foreign=deepcopy(base)
        if target=='main':foreign['ios/fixture_namespace.py']=blob(b'new child import')
        self.assertNotEqual(inputs.affected_lookup_digest(foreign),json.loads(raw)['targets']['main']['lookup_digest'])
        for old,new,default,claimed in ((foreign,candidate,trusted,'main'),
                                        (base,candidate,foreign,target),
                                        (base,candidate,trusted,'unknown-child')):
            with self.subTest(claimed=claimed),self.assertRaises(inputs.InputError):
                inputs.plan_affected(registry,raw,old,new,default,target=claimed)

    def test_exact_metadata_and_source_reader_bytes_are_independent_but_membership_and_modes_are_bound(self):
        _,registry,raw,base=self.bounded_context()
        paths={
            'tools/repository-checks/metadata_context.py',
            'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml',
            'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml',
            '.github/workflows/pr-metadata-context.yml',
            'tools/repository-checks/workflows/producers/legacy/repository-checks-protected-ci-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/parent-qualification-postmerge-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/protected-project-tests-ci37-v1.yml',
            '.github/workflows/documentation-push-owner.yml',
            '.github/workflows/documentation-checks.yml',
            '.github/workflows/workflow-security.yml',
            'tools/test-evidence/source_admission.py',
            'tools/test-evidence/source-admission-test.py',
            'tools/repository-checks/workflows/producers/legacy/parent-qualification-metadata-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/protected-project-tests-metadata-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/repository-checks-metadata-v1.yml',
            'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml',
            'tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml',
        }
        self.assertTrue(paths <= set(json.loads(raw)['suites']['device-control-plane-full']['native_independent_paths']))
        candidate=deepcopy(base)
        for path in paths:
            self.assertEqual(base[path]['mode'],'100644')
            candidate[path]=blob(('changed reviewed bytes '+path).encode())
        plan=inputs.plan_affected(registry,raw,base,candidate,base)
        owners={'device-control-plane-full',*inputs._AFFECTED_PRODUCT_SUITES,*inputs._AFFECTED_SUBJECTS}
        self.assertTrue(owners <= set(plan['omitted']))
        for path in paths:
            for mode,kind in (('100755','blob'),('120000','blob'),('160000','commit')):
                changed=deepcopy(candidate);changed[path]={'mode':mode,'type':kind,'sha':'f'*40}
                with self.subTest(path=path,mode=mode):
                    try: result=inputs.plan_affected(registry,raw,base,changed,base)
                    except inputs.InputError: continue
                    self.assertTrue(owners <= set(result['required']))
        candidate['.github/workflows/pr-metadata-context-extra.yml']=blob(b'unreviewed neighbor')
        self.assertTrue(owners <= set(inputs.plan_affected(registry,raw,base,candidate,base)['required']))

    def test_unavailable_graph_retains_the_independently_selected_legacy_gate(self):
        root,registry,raw,base=self.shipping_context()
        spec=importlib.util.spec_from_file_location('affected_host_rollout',root/'tools/repository-checks/host_selection.py')
        host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
        candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=blob(b'new')
        paths=['tools/test-evidence/sandbox_host.py']
        without=deepcopy(base);del without[inputs.AFFECTED_POLICY]
        for old,trusted,claimed in ((without,without,paths),(None,base,paths),(base,base,paths+['README.md'])):
            with self.subTest(old_missing=old is None,claimed=claimed):
                selected=host.select(candidate,claimed,True,trusted_tree=trusted,base_tree=old)
                legacy=host._select_legacy(candidate,claimed,True,trusted_tree=trusted,base_tree=old)
                self.assertEqual(selected,legacy)

    def test_changed_graph_cannot_expand_an_independently_reviewed_ci37_plan(self):
        root,registry,raw,base=self.shipping_context()
        spec=importlib.util.spec_from_file_location('affected_graph_preserves_legacy',root/'tools/repository-checks/host_selection.py')
        host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
        candidate=deepcopy(base);candidate[inputs.AFFECTED_POLICY]=blob(b'changed policy bytes')
        options={'base_tree':base,'trusted_tree':base}
        with patch.object(host,'REVIEWED_PROGRAMS',host.program_digest(base)):
            legacy=host._select_legacy(candidate,[inputs.AFFECTED_POLICY],True,**options)
            self.assertEqual(len(legacy['suites']),37)
            self.assertFalse(legacy['full_host'])
            self.assertEqual(host.select(candidate,[inputs.AFFECTED_POLICY],True,**options),legacy)
        with self.assertRaises(inputs.InputError):
            inputs.plan_affected(registry,raw,base,candidate,base)

    def test_each_device_component_reader_data_discovery_native_and_variant_keeps_device(self):
        _,registry,raw,base=self.bounded_context()
        paths=('tests/device/catalog.json','tests/device/self_tests/test_voice_roundtrip.py',
            'tests/device/fixture/new-resource.json','provenance/artifact_identity.py',
            'tools/sbom/verify-artifact-identity.py','libraries/audio-client/src/AudioClient.cpp',
            'libraries/shared/src/new-header.h','interface/resources/qml/new-component.qml',
            'scripts/system/settings/qml/new-data.json','android/phone/new-native-input.cpp')
        for path in paths:
            candidate=deepcopy(base);candidate[path]=blob(b'changed component')
            with self.subTest(path=path):
                plan=inputs.plan_affected(registry,raw,base,candidate,base)
                self.assertIn('device-control-plane-full',plan['required'])
        historical=deepcopy(base);historical['libraries/audio-client/src/AudioClient.cpp']=blob(b'child reader')
        candidate=deepcopy(historical);candidate['tools/test-evidence/sandbox_host.py']=blob(b'unrelated')
        self.assertIn('device-control-plane-full',inputs.plan_affected(registry,raw,historical,candidate,base)['required'])

    def test_optional_ios_adapter_and_historical_native_root_headers_remain_bound(self):
        _,registry,raw,base=self.bounded_context()
        for path in ('ios/audio/IOSAudioAdapter.cpp','ios/audio/IOSAudioAdapter.h',
                     'ios/audio/new-private-header.h','cassert','QtCore/QCoreApplication'):
            for shape in ('candidate-only','historical-both'):
                old=deepcopy(base);candidate=deepcopy(base)
                if shape=='historical-both':old[path]=blob(b'historical native lookup')
                candidate[path]=old[path] if shape=='historical-both' else blob(b'changed native lookup')
                candidate['tools/test-evidence/sandbox_host.py']=blob(b'unrelated admitted CI')
                with self.subTest(path=path,shape=shape):
                    plan=inputs.plan_affected(registry,raw,old,candidate,base)
                    self.assertIn('device-control-plane-full',plan['required'])

    def test_native_independence_is_closed_bounded_and_cannot_exempt_unowned_headers(self):
        root,registry,raw,base=self.bounded_context()
        for paths in ([],['*'],['../cassert'],[inputs.AFFECTED_POLICY]*2,[f'leaf-{n}' for n in range(1001)]):
            value=json.loads(raw)
            value['suites']['device-control-plane-full']['native_independent_paths']=paths
            with self.subTest(paths=paths[:2]),self.assertRaises(inputs.InputError):
                inputs._validate_dependencies(value,registry)
        value=json.loads(raw)
        value['suites']['device-control-plane-full']['native_independent_paths'].append('cassert')
        forged=json.dumps(value).encode()
        for tree in (base,):tree[inputs.AFFECTED_POLICY]=blob(forged)
        candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed')
        spec=importlib.util.spec_from_file_location('affected_native_policy_guard',root/'tools/repository-checks/host_selection.py')
        host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
        with patch.object(inputs,'load_dependencies',return_value=forged):
            selected=host.select(candidate,['tools/test-evidence/sandbox_host.py'],True,base_tree=base,trusted_tree=base)
        legacy=host._select_legacy(candidate,['tools/test-evidence/sandbox_host.py'],True,base_tree=base,trusted_tree=base)
        self.assertEqual(selected,legacy)

    def test_reviewed_product_owners_share_only_the_fixed_complete_lookup_proof(self):
        _,registry,raw,base=self.bounded_context()
        candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed CI')
        plan=inputs.plan_affected(registry,raw,base,candidate,base)
        self.assertTrue(inputs._AFFECTED_PRODUCT_SUITES.issubset(plan['omitted']))
        self.assertIn('host-selection',plan['required'])
        for name in sorted(inputs._AFFECTED_PRODUCT_SUITES):
            subject=registry['suites'][name]['closure']['required'][0]
            changed=deepcopy(candidate);changed[subject]=blob(b'changed reviewed owner')
            with self.subTest(owner=name,subject=subject):
                if subject in inputs.AFFECTED_AUTHORITY:
                    with self.assertRaises(inputs.InputError):
                        inputs.plan_affected(registry,raw,base,changed,base)
                else:
                    self.assertIn(name,inputs.plan_affected(registry,raw,base,changed,base)['required'])
        value=json.loads(raw)
        for shape in ('unknown-owner','candidate-scope','missing-fixed-inventory','extra-inventory'):
            changed=deepcopy(value);changed_registry=deepcopy(registry)
            if shape=='unknown-owner':changed['suites']['producer-api']['kind']='reviewed-product-inventory'
            elif shape=='candidate-scope':
                changed_registry['suites']['device-jenkins']['scope']='candidate'
                changed['registry_digest']=inputs._suite_definition_digest(changed_registry)
                changed['suites']['device-jenkins']['definition_digest']=inputs._suite_definition_digest(changed_registry['suites']['device-jenkins'])
            elif shape=='missing-fixed-inventory':changed['suites']['device-control-plane-full']={
                'kind':'repository','setup':['host-full'],'definition_digest':changed['suites']['device-control-plane-full']['definition_digest']}
            elif shape=='extra-inventory':changed['suites']['device-jenkins']['native_independent_paths']=['ignored']
            with self.subTest(shape=shape),self.assertRaises(inputs.InputError):
                inputs._validate_dependencies(changed,changed_registry)

    def test_javascript_and_performance_component_data_cannot_use_ci_byte_exemptions(self):
        _,_,raw,base=self.bounded_context()
        paths=json.loads(raw)['suites']['device-control-plane-full']['native_independent_paths']
        for path in ('tests/javascript/README.md','tests/performance/README.md',
                     'tests/safe-landing/README.md','tests/mocha/README.md','server-console/README.md',
                     'unpublishedScripts/README.md','tools/jsdoc/README.md'):
            old=deepcopy(base);old[path]=blob(b'old fixture contract')
            new=deepcopy(old);new[path]=blob(b'changed fixture contract')
            with self.subTest(path=path):
                self.assertNotEqual(inputs.device_reader_digest(old,[*paths,path]),
                                    inputs.device_reader_digest(new,[*paths,path]))

    def test_fixed_ci_subjects_bind_all_three_trees_without_coupling_product_owners(self):
        _,registry,raw,base=self.bounded_context()
        candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed CI')
        plan=inputs.plan_affected(registry,raw,base,candidate,base)
        self.assertTrue(set(inputs._AFFECTED_SUBJECTS).issubset(plan['omitted']))
        self.assertIn('documentation-contracts',plan['required'])
        self.assertEqual(plan['reasons']['documentation-contracts'],'unreviewed-import-or-missing-required-input')
        # Apple retains two additional audio Python readers and a changed mute
        # caller. Their genuine import variant must keep this extra owner.
        if 'recorded-voice-qml' in plan['required']:
            self.assertEqual(plan['reasons']['recorded-voice-qml'],'unreviewed-import-or-missing-required-input')
            self.assertEqual(len(plan['required']),33)
        else:
            self.assertIn('recorded-voice-qml',plan['omitted'])
            self.assertEqual(plan['reasons']['recorded-voice-qml'],'unchanged-reviewed-dependencies')
            self.assertEqual(len(plan['required']),32)
        for name,subjects in inputs._AFFECTED_SUBJECTS.items():
            for subject in subjects:
                for shape in ('changed','removed','historical','executable'):
                    old=deepcopy(base);new=deepcopy(candidate)
                    if shape=='removed':new.pop(subject)
                    elif shape=='executable':new[subject]=dict(new[subject],
                        mode='100644' if new[subject]['mode']=='100755' else '100755')
                    else:
                        new[subject]=blob(b'changed exact subject')
                        if shape=='historical':old[subject]=deepcopy(new[subject])
                    with self.subTest(owner=name,subject=subject,shape=shape):
                        lookup_change = subject=='tools/test-evidence/producer.py' and shape in {'removed','executable'}
                        if subject in inputs.AFFECTED_AUTHORITY or lookup_change:
                            with self.assertRaises(inputs.InputError):
                                inputs.plan_affected(registry,raw,old,new,base)
                        else:
                            selected=inputs.plan_affected(registry,raw,old,new,base)
                            self.assertIn(name,selected['required'])
        # This CI unit-test leaf is independent of the actual product tests.
        changed=deepcopy(candidate);changed['tests/unittest-runner-test.py']=blob(b'changed CI regression')
        selected=inputs.plan_affected(registry,raw,base,changed,base)
        self.assertIn('python-test-runner',selected['required'])
        self.assertIn('device-control-plane-full',selected['omitted'])
        self.assertTrue(inputs._AFFECTED_PRODUCT_SUITES.issubset(selected['omitted']))

    def test_fixed_ci_subject_policy_cannot_supply_unknown_owners_or_subject_maps(self):
        _,registry,raw,base=self.bounded_context()
        value=json.loads(raw)
        for shape in ('unknown-owner','candidate-scope','alternate-subjects','extra-map','missing-native'):
            changed=deepcopy(value);definitions=deepcopy(registry)
            if shape=='unknown-owner':changed['suites']['producer-api']['kind']='reviewed-subject-inventory'
            elif shape in {'candidate-scope','alternate-subjects'}:
                if shape=='candidate-scope':definitions['suites']['python-test-runner']['scope']='candidate'
                else:definitions['suites']['python-test-runner']['closure']['required']=['tests/unittest-runner-test.py']
                changed['registry_digest']=inputs._suite_definition_digest(definitions)
                changed['suites']['python-test-runner']['definition_digest']=inputs._suite_definition_digest(definitions['suites']['python-test-runner'])
            elif shape=='extra-map':changed['suites']['python-test-runner']['subjects']=['arbitrary.py']
            else:
                entry=changed['suites']['device-control-plane-full']
                changed['suites']['device-control-plane-full']={k:entry[k] for k in ('kind','definition_digest','setup')}
                changed['suites']['device-control-plane-full']['kind']='repository'
            with self.subTest(shape=shape),self.assertRaises(inputs.InputError):
                inputs._validate_dependencies(changed,definitions)
        candidate=deepcopy(base);candidate['tools/test-evidence/sandbox_host.py']=blob(b'changed CI')
        candidate['tests/unittest-extra-runner-test.py']=blob(b'unknown neighbor')
        plan=inputs.plan_affected(registry,raw,base,candidate,base)
        self.assertIn('python-test-runner',plan['required'])

    def test_unknown_root_import_shadow_cannot_inherit_any_omission(self):
        _,registry,raw,base=self.bounded_context()
        for path in ('json.py','sitecustomize.py','tools/repository-checks/json.py','tests/device/new_module.py','namespace/__init__.py'):
            candidate=deepcopy(base);candidate[path]=blob(b'new shadow')
            with self.subTest(path=path),self.assertRaises(inputs.InputError):
                inputs.plan_affected(registry,raw,base,candidate,base)

    def test_existing_ci37_metadata_codeql_cleanup_and_lock_plans_never_expand(self):
        import ci_profile
        root,registry,raw,base=self.shipping_context()
        spec=importlib.util.spec_from_file_location('affected_preserve_proofs',root/'tools/repository-checks/host_selection.py')
        host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
        ci37=[n for n,s in registry['suites'].items() if s['layer']=='quick' and n not in host.PRODUCT_QUICK_SUITES]
        paths=('.github/workflows/codeql.yml','.github/branch-cleanup.json',
               '.github/android-orchestration.json','tests/PROJECT_TESTING.md',*host.PACKAGE_LOCKS)
        # Preserve the exact legacy37 contract under its actual old namespace.
        # The new seven-target namespace deliberately permits smaller proved
        # Qt-free selections; SevenTargetProfileTests covers those separately.
        historical_policy={**ci_profile.load_policy(root),
            'generation_kind':ci_profile.CONTROLLER_KIND,'epoch':ci_profile.CONTROLLER_EPOCH}
        with patch.object(host,'REVIEWED_PROGRAMS',host.program_digest(base,root)), \
             patch.object(ci_profile,'load_policy',return_value=historical_policy):
            for path in paths:
                candidate=deepcopy(base);candidate[path]=blob(b'changed ordinary shipping leaf')
                package_paths=(path,) if path in host.PACKAGE_LOCKS else ()
                options={'base_tree':base,'trusted_tree':base,'package_paths':package_paths}
                with self.subTest(path=path):
                    legacy=host._select_legacy(candidate,[path],True,**options)
                    self.assertEqual(legacy['suites'],ci37)
                    self.assertEqual(len(legacy['suites']),37)
                    self.assertEqual(host.select(candidate,[path],True,**options),legacy)
            for unknown,regular,paths in ((False,True,[]),(True,True,['README.md']),(False,False,['README.md'])):
                options={'base_tree':base,'trusted_tree':base,'unknown':unknown}
                self.assertEqual(host.select(base,paths,regular,**options),host._select_legacy(base,paths,regular,**options))

    def test_fewer_groups_cannot_replace_an_existing_narrower_preparation_route(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('affected_setup_dominance',root/'tools/repository-checks/host_selection.py')
        host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
        for legacy_full,affected_full in ((False,True),(False,False),(True,True),(True,False)):
            legacy={'suites':['owner-a','owner-b'],'reason':'reviewed-ci-only-inputs',
                    'full_host':legacy_full,'include_platform':False}
            affected={'suites':['owner-a'],'reason':'protected-affected-dependencies',
                      'full_host':affected_full,'include_platform':False}
            with self.subTest(legacy_full=legacy_full,affected_full=affected_full), \
                    patch.object(host,'_select_legacy',return_value=legacy), \
                    patch.object(host,'affected_selection',return_value=affected):
                selected=host.select({},['reviewed-ci-leaf'],True)
                self.assertIs(selected,legacy if affected_full and not legacy_full else affected)

    def test_nonempty_or_changed_platform_cannot_enter_partial_route_even_on_both_sides(self):
        _,registry,raw,base=self.bounded_context()
        changed=deepcopy(base);changed['tests/platform-profile.json']=blob(b'{"schema":1,"platform":"android","suites":[{}]}')
        candidate=deepcopy(changed);candidate['tools/test-evidence/sandbox_host.py']=blob(b'unrelated')
        with self.assertRaises(inputs.InputError):inputs.plan_affected(registry,raw,changed,candidate,changed)

    def test_protected_producer_declines_dynamic_subset_before_any_runtime_preparation(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('affected_producer',root/'tools/test-evidence/producer_workflow.py')
        producer=importlib.util.module_from_spec(spec);spec.loader.exec_module(producer)
        registry={'schema':1,'control_inputs':['fixed'],'suites':{'finite':definition()}}
        tree={'fixed':blob()}
        policy=type('Policy',(),{'select':staticmethod(lambda *a,**k:{'reason':'protected-affected-dependencies','suites':['finite'],'full_host':True})})
        with patch.object(producer.shared,'prepared_tools') as tools,patch.object(producer.runtime_ci,'validate_environment') as admit:
            with self.assertRaises(producer.PreExecutionUnavailable):
                producer.selection_profile(policy,registry,tree,tree,tree)
            tools.assert_not_called();admit.assert_not_called()


class DependencyPolicyRoutingTests(unittest.TestCase):
    def module(self, name, relative):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location(name,root/relative)
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module
        spec.loader.exec_module(module)
        return module

    def test_only_exact_ordinary_new_leaves_are_ios_and_android_independent(self):
        ios=self.module('affected_ios_inputs','tools/ios-build-qualification/inputs.py')
        host=self.module('affected_ios_host','tools/ios-build-qualification/host.py')
        android=self.module('affected_android_inputs','tools/repository-checks/android-build-inputs.py')
        paths=(inputs.AFFECTED_POLICY,'tools/test-evidence/affected-test.py',
               'tools/test-evidence/AFFECTED_SELECTION.md')
        for path in paths:
            with self.subTest(path=path):
                entry=ios.Entry(path,'100644','blob','a'*40)
                self.assertEqual(ios._kind(entry),'independent-host')
                self.assertEqual(android._kind(entry),'independent-host')
                self.assertIn(path,host.CI_HOST_INDEPENDENT_PATHS)
                old=SimpleNamespace(entries=(entry,),revision="a"*40,tree="b"*40)
                new=SimpleNamespace(entries=(ios.Entry(path,'100644','blob','b'*40),),revision='c'*40,tree='d'*40)
                with patch.object(host,'REVIEWED_CI_HOST_BOUNDARY',host.ci_host_boundary(old)):
                    self.assertIsNotNone(host.ci_host_omission(old,new))
                    for mode,kind in (('100755','blob'),('120000','blob'),('160000','commit')):
                        altered=ios.Entry(path,mode,kind,'b'*40)
                        self.assertEqual(ios._kind(altered),'application-input')
                        self.assertEqual(android._kind(altered),'application-input')
                        self.assertIsNone(host.ci_host_omission(old,SimpleNamespace(entries=(altered,))))
        for path in ('.github/test-suite-dependencies-extra.json','tools/test-evidence/affected-extra-test.py',
                     'tools/test-evidence/AFFECTED_SELECTION-extra.md'):
            entry=ios.Entry(path,'100644','blob','a'*40)
            self.assertEqual(ios._kind(entry),'application-input')
            self.assertEqual(android._kind(entry),'application-input')
            self.assertNotIn(path,host.CI_HOST_INDEPENDENT_PATHS)

    def test_exact_metadata_and_security_guide_ios_exclusions_keep_neighbors_and_modes_conservative(self):
        ios=self.module('metadata_ios_inputs','tools/ios-build-qualification/inputs.py')
        host=self.module('metadata_ios_host','tools/ios-build-qualification/host.py')
        paths={'.github/dependency-security.md', '.github/workflows/pr-metadata-context.yml',
            '.github/workflows/documentation-checks.yml', '.github/workflows/workflow-security.yml',
            'tools/repository-checks/metadata_context.py',
            'tools/repository-checks/workflows/metadata-edits/pr-metadata-context.yml',
            'tools/repository-checks/workflows/metadata-edits/codeql-metadata.yml',
            'tools/repository-checks/workflows/producers/legacy/repository-checks-protected-ci-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/parent-qualification-postmerge-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/protected-project-tests-ci37-v1.yml',
            '.github/workflows/documentation-push-owner.yml',
            'tools/test-evidence/source_admission.py',
            'tools/test-evidence/source-admission-test.py',
            'tools/repository-checks/workflows/producers/legacy/parent-qualification-metadata-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/protected-project-tests-metadata-v1.yml',
            'tools/repository-checks/workflows/producers/legacy/repository-checks-metadata-v1.yml',}
        for path in paths:
            with self.subTest(path=path):
                entry=ios.Entry(path,'100644','blob','a'*40)
                self.assertEqual(ios._kind(entry),'independent-host')
                self.assertIn(path,host.CI_HOST_INDEPENDENT_PATHS)
                old=SimpleNamespace(entries=(entry,),revision='a'*40,tree='b'*40)
                with patch.object(host,'REVIEWED_CI_HOST_BOUNDARY',host.ci_host_boundary(old)):
                    self.assertIsNotNone(host.ci_host_omission(old,SimpleNamespace(
                        entries=(ios.Entry(path,'100644','blob','b'*40),),revision='c'*40,tree='d'*40)))
                    for mode,kind in (('100755','blob'),('120000','blob'),('160000','commit')):
                        altered=ios.Entry(path,mode,kind,'b'*40)
                        self.assertEqual(ios._kind(altered),'application-input')
                        self.assertIsNone(host.ci_host_omission(old,SimpleNamespace(entries=(altered,))))
                neighbor=path+'.extra'
                self.assertEqual(ios._kind(ios.Entry(neighbor,'100644','blob','a'*40)),'application-input')
                self.assertNotIn(neighbor,host.CI_HOST_INDEPENDENT_PATHS)

    def test_complete_source_reader_complements_exclude_only_exact_new_leaves(self):
        ios=self.module('affected_ios_reviewed','tools/ios-build-qualification/inputs.py')
        host=self.module('affected_ios_host_reviewed','tools/ios-build-qualification/host.py')
        root=Path(__file__).resolve().parents[2]
        revision=ios._git(root,'rev-parse','--verify','HEAD^{commit}').decode().strip()
        snapshot=ios.read_snapshot(root,revision)
        paths={inputs.AFFECTED_POLICY,'tools/test-evidence/affected-test.py',
               'tools/test-evidence/AFFECTED_SELECTION.md'}
        added={entry.path:entry for entry in snapshot.entries if entry.path in paths}
        self.assertEqual(set(added),paths)
        self.assertTrue(all(entry.mode=='100644' and entry.object_type=='blob'
                            for entry in added.values()))
        before=SimpleNamespace(entries=tuple(entry for entry in snapshot.entries if entry.path not in paths))
        self.assertEqual(len(before.entries)+len(paths),len(snapshot.entries))
        app=ios._boundary(before)
        own_host=host.ci_host_boundary(before)
        self.assertIsNotNone(app)
        self.assertIsNotNone(own_host)
        self.assertEqual(ios._boundary(snapshot),app)
        self.assertEqual(host.ci_host_boundary(snapshot),own_host)
        changed=SimpleNamespace(entries=tuple(ios.Entry(entry.path,entry.mode,entry.object_type,'f'*40)
            if entry.path in paths else entry for entry in snapshot.entries))
        self.assertEqual(ios._boundary(changed),app)
        self.assertEqual(host.ci_host_boundary(changed),own_host)
        # The historical anchor is independently reconstructed by the complete
        # immutable reader audit; a shallow candidate need not fetch its commit.
        self.assertEqual(ios.REVIEWED_REVISION,'2fc894a0605103843b36653f250f854714a963ee')
        self.assertEqual(ios.REVIEWED_BOUNDARY,
            'sha256:439c4efe0b3640c6da33d75854296063b60f881f0cfeb0c4a5d77fca728a786d')
        self.assertEqual(host.REVIEWED_CI_HOST_BOUNDARY,
            '14052515fad3917fd66a9fda666acbd82be124c209687b24d92af3694c2ae283')

    def test_new_policy_uses_existing_native_browser_and_package_host_routes(self):
        native=self.module('affected_native_route','tools/native-tests/check.py')
        checks=self.module('affected_repository_route','tools/repository-checks/check.py')
        packages=self.module('affected_package_route','tools/repository-checks/package_checks.py')
        paths=[inputs.AFFECTED_POLICY,'tools/test-evidence/affected-test.py',
               'tools/test-evidence/AFFECTED_SELECTION.md']
        self.assertEqual(native.plan(paths)['mode'],'skip')
        direct=checks.direct_browser_plan(paths)
        self.assertFalse(direct['browser']);self.assertFalse(direct['native'])
        self.assertEqual(packages.select(paths)['package_set'],[])
        self.assertEqual(packages.select(paths)['tool_projects'],[])
        self.assertEqual(native.plan(paths,regular=False)['mode'],'full')
        self.assertTrue(checks.direct_browser_plan(paths,regular=False)['native'])

    def test_new_policy_is_python_only_only_for_existing_ordinary_pinned_leaves(self):
        codeql=self.module('affected_codeql_route','tools/repository-checks/codeql.py')
        before={p:{'mode':'100644','type':'blob','sha':sha} for p,sha in codeql._REVIEWED_CONTROLS.items()}
        before['.github/workflows/codeql.yml']['sha']=codeql._PINNED_RESULTS_WORKFLOW
        before[inputs.AFFECTED_POLICY]=blob(b'old')
        after=deepcopy(before);after[inputs.AFFECTED_POLICY]=blob(b'new')
        self.assertEqual(codeql.select_languages(before,after)['languages'],['python'])
        for shape in ('new','removed','executable','alias','neighbor','legacy','mixed','config'):
            old=deepcopy(before);new=deepcopy(after)
            if shape=='new':del old[inputs.AFFECTED_POLICY]
            elif shape=='removed':del new[inputs.AFFECTED_POLICY]
            elif shape=='executable':new[inputs.AFFECTED_POLICY]['mode']='100755'
            elif shape=='alias':new[inputs.AFFECTED_POLICY]['mode']='120000'
            elif shape=='neighbor':new['.github/test-suite-dependencies-extra.json']=blob(b'new')
            elif shape=='legacy':old['.github/workflows/codeql.yml']['sha']=codeql._RETARGET_RESULTS_WORKFLOW
            elif shape=='mixed':new['actual.js']=blob(b'new')
            elif shape=='config':new['.github/codeql/codeql-config.yml']=blob(b'new')
            with self.subTest(shape=shape):
                self.assertIn('javascript-typescript',codeql.select_languages(old,new)['languages'])


class NonreusableRouteTests(unittest.TestCase):
    def execute(self, status=0, product=(), include_platform=False):
        import execution
        registry={'schema':1,'control_inputs':['fixed'],'suites':{
            'selected':definition(),'omitted':definition()}}
        observations=[]
        def run(args,suites,cancelled,result_callback):
            observations.extend(suite.name for suite in suites)
            for suite in suites:
                result_callback({'name':suite.name,'status':'passed' if status==0 else 'failed'})
            return status
        controller=SimpleNamespace(ROOT=None,run_command=lambda *a:None,
            Suite=lambda name,layer,command:SimpleNamespace(name=name,layer=layer,command=command),run_suites=run)
        with (tempfile.TemporaryDirectory() as temporary,
              patch.object(execution,'checkout_identity',return_value=('a'*40,'b'*40)),
              patch.object(execution.inputs,'load_registry',return_value=registry),
              patch.object(execution.inputs,'full_tree',return_value={'fixed':blob()}),
              patch.object(execution,'platform_suites',return_value=list(product)),
              patch.object(execution,'capture_execution_environment') as capture,
              patch.object(execution,'_runner',return_value=controller),
              patch.object(execution,'_write_receipt') as write):
            value=execution.execute(Path(temporary),['selected'],include_platform=include_platform,
                receipt_path=Path('/fixed-receipt'),_impact_selection=True)
        capture.assert_not_called()
        self.assertEqual(observations,['selected'])
        self.assertEqual(write.call_count,1)
        return value

    def test_empty_platform_context_runs_exact_subset_without_runtime_or_reuse_claim(self):
        code,receipt=self.execute()
        self.assertEqual(code,0)
        self.assertEqual(receipt['requested_suites'],['selected'])
        self.assertFalse(receipt['reusable']);self.assertIsNone(receipt['environment'])
        self.assertEqual(receipt['results'],{'selected':{'status':'passed','fingerprint':None}})
        self.assertEqual(receipt['platform_results'],{})

    def test_started_failure_stays_failed_once_without_runtime_or_full_retry(self):
        code,receipt=self.execute(status=17)
        self.assertEqual(code,17)
        self.assertEqual(receipt['conclusion'],'failure')
        self.assertFalse(receipt['reusable'])

    def test_impact_execution_rejects_platform_inventory_flags(self):
        import execution
        with self.assertRaises(execution.ExecutionError):
            self.execute(product=[('actual-platform',['python','actual.py'])],include_platform=True)

    def test_legacy_owner_forwards_dynamic_selection_without_capture_and_never_retries_failure(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('affected_legacy_route',root/'tools/repository-checks/android_handoff.py')
        owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
        selected={'reason':'protected-affected-dependencies','suites':['selected'],
                  'include_platform':False,'full_host':True}
        proof={'reusable':False,'environment':None,'conclusion':'failure',
               'results':{'selected':{'status':'failed','fingerprint':None}}}
        shared=SimpleNamespace(execute=Mock(return_value=(17,proof)),digest=lambda value:'fixed',
            _write_receipt=Mock(),inputs=SimpleNamespace(load_registry=lambda path:{'suites':{'selected':{},'omitted':{}}}))
        controller=SimpleNamespace(android=lambda:SimpleNamespace(_shared=lambda:(shared,None)))
        with (tempfile.TemporaryDirectory() as temporary,
              patch.object(owner,'gate',return_value=controller),
              patch.object(owner,'host_selection',return_value=object()),
              patch.object(owner,'selected_host',return_value=selected),
              patch.object(owner,'platform_owner',return_value={} )):
            base=Path(temporary);candidate=base/'candidate';candidate.mkdir()
            status,observed=owner.project(candidate,{},'a'*40,'pull_request',
                junit=base/'results.xml',receipt_path=base/'receipt.json')
        self.assertEqual(status,17);self.assertEqual(observed['conclusion'],'failure')
        shared.execute.assert_called_once()
        self.assertIs(shared.execute.call_args.kwargs['_impact_selection'],True)
        self.assertEqual(shared.execute.call_args.kwargs['suite_names'],['selected'])
        self.assertFalse(observed['reusable']);self.assertIsNone(observed['environment'])


if __name__=='__main__':unittest.main()
