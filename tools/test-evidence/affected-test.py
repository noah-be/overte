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


# Fixture-only projection of the REVIEWED PROPOSED SOURCE snapshot, not protected D.
# e66b8ff3e735c0908446f40be23a0cc9d9883ff4 / tree 0a9d7f624d55141ef0c882b7a19ef947667e21c0.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = '60c0011c0157c6eb855de0138524cd9b92ad0db3f6439bac3d27c7ab9eebb388'
_MAIN_PROJECTION_B85 = (
    'c-qa~+m;+h(jDmgd5pdm8gV}8DQ3-@`&x1E0Fo?JR@Z?|N=xrPpG9VY;NPf>$Si7RB>g{|Al2>};bCsJZSQUW^B@2Ga(MarI({A='
    '=BMLf{&f8JLwfr3@-#d=FX`!@zdRow{_)@c=Rdw3=k$;N{*OG%nyUK8fBVPt*TLTw?VP1NYnFNL%dGD6ISoVK6w8veb2W`ARc+Db'
    '@&DoFkH`2g81IkcKmON$`@ZaGq3P?V$K(BB`eS3YaV+ONZ&K5@**v7FYueTtS=MGt*^G0xv`sZ+-TSLO4%4s0m-Ol1$ERPH`{Tbq'
    'eMx@p@NzglJZ~(X%BC!ey6T#x80NOf>t?Qo)MiCjmHjkVZ8?_h*uTH{Q+hl;A6|}6e|(z0rs>zM73;~vTc&(!^DZ86N~vG!YRRg('
    '_e1+`D2pnM7as0QdVcxz{CapvpXT(K9_I8g9n#jiZJ(86Rpe!Avbt?@%jCt_4Ssj;agTXfEp6Krd)D1rE6eM8?5noRTgPUs+NNK+'
    'x+}V=EBd@%hBhzzp&i~|>+MxOd$~{P;pNl6UWfa`a+ub)`p-YU-M_zjGZ%AN6{#AV((`SyCM&8s&+B&1%dW1*xi028wYye-I{uQT'
    'mrwEApD!=l^+h)Hd20KqOGQ1E)szj(oaUj)v$@TOrl>93?^*Ug57ot`+okp0l#9pS<!PK8+@>#!EFXp`pSx*p+qti*<v*7mpDZUb'
    'O!o&*`SW!6{7ZWH_3-fg`O6UR`SFkUSIzTbs>W&Zf~%?>i>jNOsmR+p&2{I2FLlaWU(z+JKKkWe_~msS)H20a+LdEAwZ+_JOE-=l'
    '^tcqQAk}3lP1AMj9>>e8F2mAhUTT{!eqWLGLspccLpAlOtEP4trlIc2{F+stULP*5IptN;H1jg_W7V~O-q4p#)_3_>rZE-OJZ5cL'
    'maEo`lYBRQeL8+ichA%D@$#?sxn!9qJLF~4IM-9^hq@fvtS&m=Rz1!A+~wCj>vabY!?*M-aHqScG&~+2zFgeK+&R5dlj^1tHB(-t'
    'GVhD38m7_bo!3>><W)Xh{~#V7zuis8hvjg2{dUMx)0K78bor2rW4UW1tH);OeA7i{bFDp=SFa!U@_hIEZ_9Xb{n0tgs%oz5)+JGA'
    'o<u$L*;Ke8oygKt$Wl2DSFi5`x+*WOou;Mi1|hTd;kgT^cFNrrVq0BJLy>oaZIkWz?GaJ_J^b<cA-zPTyL&pmzNEYPFnoD9KEE8M'
    '%hASdJPuu|@_MRM<@NVnN`tF2s~b^on#W?u>%6~u8?W=@#f6K`ZJF}Ijp2iz`*`|x(oFd>7e0h#bP`kB?q2wG@Xo8RiCG-Mm-PF~'
    '<p5Os*xNJ|WnFfqYuu*lKDA>#`x^T+<=Gfn+U7p)2YKPk@!MhgB<%fmcy^=u06!0}^Wo+0eB;F}d-02`>oinzF~|nXMKqk}s&~h9'
    '5fk&Kj+f!dv^Vc&{VL<*xF25Sl9!`Y+mw@Azv(OQqnU?M-0bBV%QClRw&Z!rBwN|-n|YN^UXGOWH00e>G~JTbe)~{QMeAztnMn8Q'
    'ZmEa4DvOlgyoX=Y(?hzyTi?>fo%GVWwwc?;y)SuPs;pSXxoGOh#+D}aZR`9N%gsCaHatkT=Q}yRqx|&8-Pgl&<SG|;mBq!?ELAsV'
    'X%a@-RJ+XFqH=}2w8N~eJf+)rbsYUmzikAwW-6CCpXyPxtj3~ko!+6$=2H5UoFH+miGO<gE*{U7$8f)X)lb9payhVdbJZ1XRdfoh'
    't`XJix@@PplP@~fMV0k)D!Q@1c}sGt<^J&H>&xy~+qC5(qsoS=9$hWTcb?1TJMkwT&|GF}wxu0Eu%)eZ%LAyhsmodwXxXSXi^#fU'
    'SsqF6?PXorb!9Q%yaj2;EZ7}>^I_k8e?*tF0B2<wvwl&(c?M<IcH;in2)@gh=i<yH{$#g5mgg7W)#by|I~r{)J@#ccO)jCOcWx&S'
    's#Q+5ZC&>D2fm`0;pt1-eG4oS-fWm=*~ij2Bgu!IS8eT(wDE)*`9Yth+uzbDTYb9<#^dY5JZuCS$3z8|Nzc8OELQ|Iv;SK+lj?VD'
    's%*&B303-=_O#=AD$|npbw8@fsxtL+J!RuEPkHVnce7(05ocPm5AJBaqwaQv!Ks$N7r6`5#n=_#ojHx2ldZ}b%Cc0xFVd_JzPI%7'
    '+u`Z>@Xfz?dUcn}x*~9%eo19Hj$=JFu847HU`<ULy0P%g+~{-pu|4g+MZ2MDhf-D1He>2wG;^i8m4GQPN4am~gSVsV@7vDZK@#}o'
    'bbD-Mg5%gZQ1GfL6NpDIYwVk;?_3t8J8eu$VY?sO+D*6o*aEa9#LoEAw@DT<MV$y6$tSr;wN&LW_tW3Bwdwe6#YwgvShEbN>?QJ5'
    'p9_@nK08UX@NKuvoR5opwkzkqXIIbZxAd@4RV!Khsg4(@h!g-a&#TLF*GEyN4jNht<ip4Ivnvuv539Zmh+$4kKlRPv#vQW8$3FpN'
    '^TrF!mAN0>$`4u5x5J(@-Y;1>1i(-xARg#$YC($m2+>M*R~AFc=b>6Ywy*0`BkygHGr~dYu?(1N0WMZ~Q&f(4Q+9<NR@pLsbYJqL'
    'yXh&xc3%#|{qqJopyaBm!bRKlqqJ>VJgmqG@=>yzm(wV9n)?s$X-`T}y8Im+{|8z$<hgHNRt?gJ+>~9TK+T7CE{czB=7#J|4mmD)'
    'lQ)eoOxZltP}9`bOO>Y~cjXlB!MvD0wz22q>l09GI(|)X>*;bfXT3R76b+tCploR_`vwr-M+vY@{p_JlAf^v)DYDAD9VIM;NxlZ`'
    'E81FRwv6tX0_rlCMV;WD!c&+1wC{8Mc9!9A|GEM6c2zf}A=N`x)x)G=(#mZIIm=XdOjB8Qy#`AD!E^oc?QuEWr|;F;<<Gx$={Mz|'
    'Is*rZm<?FQV;SYUSwONnJ4M}m@N~aCy*|IVNq$X#JZ(XvzIpkj@4FgP?o9XI(bNM<voUw5Qnyrdmp)PvT(OzRva>R8VWLIfE#BTz'
    'h~ZT=X1=g#tjfBFMeMu&&mi^rpIp8z<`Np{SU^YH+I^v*&t$T7KGqUh7;UZh)a}c#zr3#DE<JraJU_2J#EZ$;*!TJo(dbyZG|n)M'
    'RvJBKV>Pr@>NJ67F=yXT{(6kJe>`pl{J5ai6W!3a)l|(>T?lRJ^Ue)EXZZ|{^O@{h^OUw+4xM>F6+XOD`(utQ3h<qB02kO~ap&l('
    '*~7dqe|m8F|Ca8C`P<?0O`@|Q`4Io|v1l6I52(bvOnPjk|5pOIDh0#Ng5bRB9xyS>T;j^ID3IDIO^w37^2I|z0zR6QYr??3v-IPa'
    'v^&R`$~+aLB42$NRjUrrTxspeHGJ$@F^@eEerLV-W4~w5r_|1Bi>jRG63Sn<RTTKCmpzw0Wye}Atu~w6D;7T$rql5$-TmTvd`OpT'
    'hzPBMnLbCQ8Q(Td3uW%JsN8$as79SSOv_G;?#CT`JN}l|V$>D1aTVrp$+jq#Z0yP*U|ea9q%-bDxLB`hZ#5qJVgDYkiz?IPiD#wH'
    'I@9_pHM;6CUrG&KUs`ejB~*c_ANQ}nGqmLMqIN_JaQNUTZRd*%#4TFqKE$dM-sRop{)JERWydpD19|V7xrOVi$g^N44ArQQuJHl^'
    'P`S;u{^zwz|5?IbzC$#!GilEtbqy?}EoAnc2M^HCyzU%MA|YFDU;f<fn;u^;KL_7kjw#_!y>+w@b%vX)ffBpt^b@*Pqou!LBm34b'
    'ms*oEm-T6OO1@;Ni|?T<{6RNB7f?Fp?D``hVPCl%K84}wG8Qx<q|8NhS=}m=kXP6CG@(^Egh_DhWE%54-n@l<Ponkwt(R$f56A|{'
    '8w0k1hd-!~lbc;~Rm(GO*v20(Uyl#_0L?i3iUgoex6-gsgi?+0p-xDh9+T?W^Qvxm7*FX7Oh=(I-~Ib(czoQ-vZgUp{w@xMP!JfH'
    '%W<p+Jz*6&#+dU0-?`yn0G2K{VVg#s)>uqBH&@YG1Pv~_ZN(TN63Q#>OFN6VGXY_5LeRHEKa@c(Su`WkoVk%I=vE~;nCnrOF(@$0'
    '75C9iS%LmSt?Au({(ka^6{p)d4FLrXc7i)MO-;F@8an;*Plt!c*O$-U`u&+z^+|^R>EB7>4OUYTUEGacT~w*w`g;B*nY~gGv=)E}'
    'xO?$fih4(u^q1XO{ZpEQ`1Iq(qV%{MUgFVh14n}@QJSU(3DVc#R7}2JWl3A9J@koFoZ21W=zAO6BJC``fXJUbmLjkQSLi%<i|V7*'
    '`mD!k5x}|~l$rIiej_(tUQ(*&Y({pf*()MM2YghEwW%Ay)%AcU(hkecCEuX2h?RHV!|?R&_;mN`-`mJq>cWTMj?{61hfU2C<sYcE'
    '@7g?H(8O}Zs4%{FAE(Om)0r#r`T1%3|C&6qy|Mq-=p^rN<-{q80&C4QH}Fj9ZP(4ZFL{o8T1mNv2A%;Z_x*Y{LxW@2ePBCp0K&Sh'
    '%UN$VwgoETG>NG~s_$3LQQ=Q4(qa3Md@cw_H*RJnah^^$GU@QV`}oX_?^PO@3Q$y$+{P1@iMOWq9_HE~$r76#^sCK%jjxCM`Go)M'
    '1zbh84iPA5ym_WamCb@c+qQv#z{s>)%HU__AK%;=v-{z(ZSYWhcJaJ~gb800QkO+HSd#%GrzwK*kf*--_{I*}Ku>Qk^-Mayj4bF='
    '71(o~Zh4NEGw0FmC^d`=d^-F>g!8=X|Aw7CxU=pxJ%%T(zRRa9iO?e~TGv{t2Rj!%wfR9xBWjGASKGL&$NJ;DIwd_~#19?X%a`gn'
    'AbGXGMei;XsAeDJ+&gMc9JVb~0P5e3AK%(Fv1^uRIQtGh{=E2IbejGMP7z8qkfZCNUK{>~&+?qEAHJ=X?CbdWb$H%jM<Y!(!o2NG'
    '>exUNWJm+R7y&?u>%s}r_V_oPvC~z!3%+jkIYkNB&Qt&p+irzS7nJd=DW)K)6&_rcKEA2v!<UsEaUcaz`R@2AYrvw*P|*j_u7J4R'
    'GIpJhLF;Og=z3uA)%3q%Z)>KrqwU_MIq##rhWy$)d#Yg-QG$imN<?g=G((^NhL7M)2yl5ji~cbdC`eXn0~+eULQT=A3;H?_Kw7`l'
    'jd0_3-uCeMx~o#Z-=cbd<va#l)w!8)lo2IRw??Q1)HZK#ev99CwO*7Pteb$Ykh9%~gE&?B6eZqpEV%Ailp$0=Z2s``IfwYmkWPq<'
    '%F>nNLPmvvu;R0b@gM|I9j&~Fc2@OA_p;+ND==z;)Q6JMLK*RPb=pVyFm(fTa~fo$`q}M=w{or@{`#?PM1U;HrKQz58AcF$SrVKf'
    '{V)El(hG}@3IP10Tf1UQKtX_ysEDsc&!Z)(%##1*#eg$KYtsfio?WOW=fhJ7h|W7pMS5#Rtbpt=y=-H_i*C-6O}e2<+ivP3pXxIR'
    'L{q}V;pEDip)If3!&VWiN>hXsUEL}V6a*A`WpJ6bm1a^51!YSrxBqwVY&7ZjX4DMTq8E=YR1%%^YItM|DH{THt_zX(KRcYRzu{ro'
    'LM;-_TadVhD2ny|p^1JN(b9zUGCKVsdYpd7;GB<>T3nVn+<(49)&D`Fbr=6^qhDuP2e`!ajr%N(@T;1l#ObP<atx+;*$(OQvOzh#'
    'jLG!#f_APi&?SiwRV4<kihB(0iZfFRczRjo<z-F@&-$M?dcA!))&aAO3qfIlGDr*6D%wh2s)+uHXlDM&j|%uJJp?NLd3bs`P)<pd'
    'SEkF$28UdBK4acNgIy)$I9WdF71faz2d%PLw2QRME-tyA6p6XN-=wqUQ4473Bm7P{QW-w$oPpe$q;T)1x^E%|{OpeXj|ES}kjv*}'
    '2xPA=Gb}ZLZ>!DNAV4|s)RI1fQ(Zi5{J!V$`0egDxAwf9(tt6^Li5_E4IF{-qkh3^2s9Bv>rrMnk8}UC=JhFCnbU8Fc#G=0$Cp@r'
    'PokHFI020$081Zyip4srE@i$;a>RenW=+pwYteald<pH$8e#rpMNjX~=jy3tUL$T)2gMx+T_*i&Sb{Lxwjq&3-D=am6`#MWsvi{v'
    '-~ae>U@M}dI%S=stEWM<gS-Ml&+VYa0M0a4%5fTQ+`;4H;q}|yo{dbw*49l*?b^mI6CE&dY8}a0#Co(~6o#R`awEGQ0=`V6y*7%s'
    'RS-o<l2d^kA^#YPW}Lc#+JV&Y+O?<Sz5C^OO5xA6$L+IEA{;0aHCsRWwB0a;<^^~?n0y2&dd!_Hf4+7%D`0&0C26>CwHy(>P>e$+'
    'Jq4k-ihK;Cq3TkzkWWLBVQ{Ll-CJ1C!LE0KQb3wqE&^Im%_!g@`k|DL_CL(Xdw^*byWhqCKi+}P#kY+mk!(9@1x8{<Uh8+x5dd4E'
    'Ry$o)++r7Ky_S2IoYV8Kx>t9{>Gl5b`>tmXR*j|gtw1M@ln0GRDXw$USLo%qObAS}lN-12<?;3ID}LmCdftFF^%Q5tW1UlNV`aB_'
    'RZ2`iI%V|M3LHCcBV~WXK9Hha@2Kt@JR>a{Q2}ubhqPIiX#34kG6ff*A}6P=Da-ut+0Y6w?Px{^7+!~Nqnwsvnst7uC2A^UQiT++'
    'Fa__bY;N3@i~9*P;`#8azkU0=i;0&i2sNdz<UqaD1jy9t$Wmm^oo?40vS=-Y;>P`)5QyQAdjTzKq;z=iiv263nj!wmj<Thx>*&tc'
    'C?tuEM-};dt7Xr6qQ3RBx_UpnEd-8<cBJTfwFDLom4s(DtHFiTN%CF()K%o?`}ua9e%<wP4_)+d6xD5+H@G_ZJFc`4@`omB3D$zl'
    'f0_0!e6AM9!^6DAzEr7(GE6X=a=LV96bTezX>I~L%LP{=)T!D1JwG0%WA%AC{QeTC{|bIyj%%UWk<iH_^d6%u4!VGJGEfi5u^L3y'
    '(RSCZ|0iW?_qC!-AA)YGd4x3<eQNb`#mS|@CDI#hgWU%xyKW;-VYTwKe-mU(N+E5<U<ZKch7q_LW;Y};L^63tfC_loy9xiTLDab7'
    'j;|u6nnQ&Q1nWl>BA2T4)A=N;SQ0M5G$=`L+`%c|+5J31(V@x>n2QKl5w8!9I3g$J^Fs_*R!A*fwfnCB?dWgsR!gI(RyU%Pv?|lR'
    'D@A}YC~R4z{1z3K&`Bw9f>pS^_PBGw-pB9Ip=&j?eF!A5HE?KMk!6ijf`z&;C~meEB$)Z*f23W~D?N88LwxYAD=&KKL*rDy92z&g'
    'OfQFC>pyHQxk}OA>hcYpa32baUXM6W`u$awFs66{gqc&Pf$J|5hSFBR*{74%d4fCT0C(JqB0AQpZz3RB%LIR~PulIN+Pm2LOONMv'
    'aQw%+)4w4zxZlxs4barlomK2?Fj~YHq>fU#?&0GmIcx>O$DG}=ox?*kesM0w*M(iz-Q(-{#)Y}OCn4YE3&e#^fbS+?&#ZITb)2oJ'
    'Is(QUaq~a4r%<=iOQn0)(iU@#X-Q}i8t?+>4lFgHbMpzJz6aBkb+FflpIIVZv7aB>H`0S8y&S$>zNXxP80_>T%3kW=xUEP4eH}W!'
    'KA_N;$$#hJmR;R@I=a1SD>QoxSv2XVTz$vL$AikTgcKoKaUr+^SinQ_TlVm6Z3k*eZ0(_dV?kdaJOC!?BRtQA?ab7D>_;p{`yJ<7'
    '_7L_y_V6_CcoxacREFY->zR`RZpV(nIbn%F$}l(N3;>C#y=5O-qfw1NzUsm6Ivi^5UL{Ov;L}Di#B7xEbM~+!?V@gpTdV1BIvgul'
    'b9cJ8PG9!r_mjDs8}*><6?<z8kPMWIvxE|W0XW5}Nw<AHu=(Q?0N}ive|@{(Ak|4`$V(6q-6srz)H@abFI5`Sl92B<RkY84!&c(Y'
    'E@K8PR+?77I<1^CencLN7=sv#Io_r|aPDqyZr@9=GM@*BWdpql6chTLhbDz61h(Z(fp6tAGMbLB33^FNw`}Bj`1VMX_8k1+Q)_>V'
    'xbJV^i7G4}2mO@BLbkuCc(l;Q8YvK?+M!7|#r~I2rq4SnfGTPZuu-cg&T|f5JlBU{fT!HT2y9v5R4~BtmQ9?F$8@g{ySxYdv5<+('
    'up`HW04@alE#w#Eqgf7I$GdCye>T(C;pI(6GrVkmE1Ad5$udFlJLW?!7k@KG@f(Ra_6z`FM(x?X{&$ndvvm{*_v;2ifRF&-O8Px5'
    'zE!jhv@5X}NLtu5c^m<$bo+zYi3EGPU5;a@B{frns5U%qBuS{BXxq|HE%$orbZU5BNR6U_DyFK*OA7ei8;KY`{W0CAbKW*hzL3b@'
    'UcRnw0QYITE(;wpN<xzfT`oKQL?9@#K-@k^9D0F}fqeLz_O!#;3u%Op9ua;x8w#_e{}b4&ia+gD&;TC{!|rd{(0t&!_p-rwFG$!Y'
    'y)=#9F>Jn?AX-iAUlaC_qlI;~L>c$D?C2@|>vb#UBQwX*5#jiGF?o!nk|PjycNOj1j^vgwrfNUBq5I>P!^1ADrO_sH1*W*5SzS8W'
    '(CSL|A8c9nly1l>I4>XF5%l9ZG#U?6+I5(q8-d`ieMH?-Z>-N7g^C{HI7=cz!0cA~@RQPT{H~hb+LQO=?Wjq#oZ7AsjtU*0AYNvX'
    ';o<i#Qi?QxbWhLe#ZC1Ew)-$VK7T!K?22f&!WD$<>UTEbs1k2+mTOkQu$Y4&j-vgy?dtXM{y1EQnwLP~74WP?v3dD`C`Ax+7Q|<r'
    '=s@ZbnyRMw=$>AVzov&XZT51q1;Y(i?4({9YS}p9p=gATL;lp41n)&`Z@hU!^ZXQO{8LKtZ#-;r1YKLoM(P)o7ib>dX%}{O%tCM)'
    'yNbmw3i-{U(m#ks#ogDJm&aX!Nl4T;EmmFyuLi-O!umu=aKGSKa-nK?x8}`9H}pI`9Uk{w{kmFX!!8sOQL8U$R3(2vSYDyZZ|)$W'
    'BJGyq0~^|=nd*_`;Xt6GoC}$;N>+8v9)U!QZ=}nGh^iiM{@~~1w?Uj<ua7^yzAwk?+&LX6W3X@|Ct5Lb!b;p5^j8TJn~5-X`rwxC'
    '4<WVPfz~Ngx++mM^W<JAWT03xWSEg!R{$ZpQ1ggL)!(rnRZTi<83BcZ-OTHKazV&MNZYWl;zMI1gJ4!fLs089`{0H`&ct7CSA-_+'
    '!<0bq$$Zl=Tjdsb6W<3>KHSr0B3W2PdFz%=jHB=0*bj=c%df5um$FJ4&xBx*M$?40(YIIR@ZK27yi}*z-?gpyD=Om-OI9g~*A`Az'
    'Je)9-u@<Km637><^L8PVl-y<aH|=ZLwzmnV=mc>T9Yaf0;VOsOz04aCN34WKwzM=K+)&)AJFKi3vqU&ruwKLG-&dy{(MK;%nTno+'
    'loaiu{DZqWu^gX#bT1f?o5~6-SA;{UMn%a=CqR0Y2d|sBn8RFHCvmvIH2vVN&iBXb!_J4LV+)s+-@4leytA6RslyWqoCgGtp$|@A'
    'Q+n&Rz8qhU!6}z;pZB(rZ6mUW;58N0*Hy3_5h@WVMg@S@qQM0<#^}w_JCKFo;|6Sb`5PN~Z^-zCW{uXMR%)!e+<a<^CSbDmrpEVj'
    '>qhR6^J-^xGLO29_*CIUPOFDP(ytl-mj+s$nn>Flw#)t|BKHUO62;K@C7r|fuB!y>kO!u%ctzC&hLnNG6&ev<Rrr&&iX_#^$2PW#'
    'sOR-dn~s~Uh)B?+hX@n=Y<m>oDTw75cSMDXxM+p0;LxpmI>RD=KBnz0HF>Xs&D$X)aZnP53rkRU^<^DpF)|KyetQ98Rd##l_qP)q'
    'sid%BIufv*<^*SZPR(slZOQL3(@=ebY<_cE@^FmCQJ{JB@1EEe<2QGo;r&m+RZOc;Avgso3=1c4O&)S4UN|?`AICL^Je5N@v#%Rb'
    'k)nnX10rc2#$+*c14Rk~5sk+bQyM1VW4if<1ue$0R`Uzl`;Z!t)eu(6q5l>MxZ`O0#~)DaO+26~hpbJ@M|O0!hPZqA8m@bnx5ErL'
    'i#~;AC5z#b)>~iK57RVyUf3}djW?%8=aNhvBswA-Zj%l|o9kQ0zK2=$5^f3xM~B?I&^;(*ldY!4&G*=Plg|6@j>65ZEx@deW4`=V'
    't_Y;olGn{<t)=tD?1b#)_PwlkJZZ<?ubn8dlH+?fs={i5eefSA`cPTZdg@@vKg|1RKDeXbzU?sh2=5T6i@{GtD&W+e92!%*8QDt5'
    'xRqIAJxn*}LBDm8xc(Ms+E#jR<P{LD56HTVu@{!^!XDC{71cF=X=PGBd|)T(_u$J%!+N*vsKtAeg%~`HctbOCNmPf1?zma~tAq*@'
    'v%8OM>aaeYwD&RTZXg<jD>7mYYD;+FVO+6@tHK}#1`>uWW&g1q9e31Y#{EQA7R+6fNM`)mTp?Xj5rk0@zIjB%_IAiKcJdM!!|`c@'
    'a#%&OUWThfi@eP{lk8D^HZLs|MO21MNB}>uk24u?+R_`M*<lv*DTCp&3}WFsY5uT}E9Wpp@yS!tj_D&?`F>A{fE#(vq+(`F3E_b9'
    'lCd-y(;U8)0-;l)s&||F#Q%=XY<C9%V4)VGSNB!7fxu{2Qmul2fDH6~i6=-JKd_mQ7j9^$gtCyogu5PFzq$;wy(uQaNtLl<Bwzy%'
    'f^quDE?&Z|^DanSn^=@`I9j5b)zT>msr~303wIE^AWDMFR6HMvz29?)gcCyJzhU;oUxU@2v0Aw3y@sJ@;;m__RFzCefc8hr&1u%3'
    'x#!*5*xV5EbHS!Z1id4d!A`xXnERw{q2zRufj;3*f6FE5!GvZ4mU80QZiwHs-nb7|F%)qOFE&hL_>(I##`md&F=gf}V5i4>Ry=P8'
    '2kU>{>}|^=hcKs@<xQYVt-(6H(MA<jFR{y_A;!XZKji_R^dy1(Yk%SmMA>c7g5#}`gn0)|F|!eIN3zwUA~2uD5X8n~0eb~p@y@>1'
    '5@GkQ$l#}VS*(G%N0Jij?6UG;4O@hforZJo0k+l6yE->d_U=b245A##7IX&UJJ)<8!NbuftaM3fW*GF9=Qr=?M;7JYO-cH&0rIGx'
    'P?U8I!ecO`>G9F)hC%Jw*<6us{d80D&-U+WZGGbakawexOH2WWFt02^BZ<05odvZ#yLC^~)A0P2E#$-TW!Tn#gOzY+`p{6Y?0}yl'
    'k%#^3j2)(4K)_Y-6<6@%{>yI8n8p6#K;BpkDmDMj^uGuLve1G^oc9VZbBJc8*t$6e{1tZExv8)fnz1Jc>hS(!QW{JA%q%6eZdRf)'
    'Ws>A!o<Fv!sD^jj_3>FLmy>Cr<T#AMjp@Vt$rQ<L;NYPfDw|t(^c_jry&=Y~#W)e3)+z4Q7~_-~kR}%-LBu5V&t=Iszqfce!?SMp'
    '74cEMTgVR8!gcr=7|<&H(l3>#)(ra9>h6{P)*YS8Px;jAmlzhX0mVa^aM{hi3ilEgG|0(IjN&b$@ztodNUR7Yn-6d2)Xq8XzuxrT'
    '!gbSOf;%m7&6zbB+DX+8s1RnCa8bte!JVzWfxUZ*S%Y;by!7S>9b{x$D<})9(JBCOnPk`gbX?C>dwTx*`VtA_{`&-UDj?-y*NWOz'
    'a#_;saq}V$Q9&s-Xg(CLyZ3e8$a=J&-y-Jpx*AEp;4Mhu4wsV?w^stQsDlhLvo_aIbQ8i`eP`fHwS;$E-+yFB$MF|QlPXo%#4Uc9'
    'H;gdCP>If!9*sFa?pyec3FYvxIW(}u$L^ME5~iQ*=`Vk@nOd4C>P>ZFV$aElK?bCS(-N<1Mm4M3ucwH@x_?KB?RWYVt$4ZQf6Xs1'
    'qfsg#6v_;!5IP?D$Pys|GS&gV$GHAjcl^|H<-N_E``za!bN;(?J-?BQ6g-{6^&}7kHU&H)<lVuv#Z8C1;JsmYet0We@5hl1-xMu4'
    'O~A1XbL!AZ+kx+jmr)l}VAB;b=w%o|lxKqR`k#Z``@F$yjqwq@7A4M2IOCz=LBy6I1TYB00n%2EX-Xg2#nzJ$QOqF-w>d`>r#Hp8'
    'v?2zTFo<OKikiqLC)=M!pN{6kAwFPwI_TT|@W)EJ-q4t7VvjL^o1t7ClwK8c19w7BP(lOVYqk3oWT?|VNco1Rv(?>6MY2^NlY1dx'
    'Mic>PEa3<P(?)>O+{d3o_s&d_TCUp$Ywo+JA+o@`FY(u{K6;qmQq;_mDl=;$lt5ftvcPK%4bY!4rdsyXUB3(e{qu$uTX>7KF&6-5'
    '7jS_YG6qc1$5n$rOZKbNFf`3|i=SRW9D`l&0jmPe$b=4Qk+lhLQtc=#a6Cp1>Y>dwgs{3oA9t2ng?{E-(`{>ckYWjqnPFqUj;3V_'
    '5!&LD#6_L!PfhPcAgsshHgSeM-wwit1D!%U1@aq4&qjwVLCaHc^OXs@6;K*?An&d`kNQrWp7u!t^O%k@YsI15@yt@kB2bsn<mEl%'
    '9ktZx28N~Uc7RYatP>~q^8<*DkpW!~zQ{0C)O&Zg6RC)kF<^qR|4&WlE^cF$q-;w;#ys=~Tr3E6RE5M30uv@n9lk=P5g)uS=cT^#'
    'HJn5A507A%g&Hr5EVQ9rOxBI?Xhhp8EQ5KVYz99X7iqlmjp%8OLS=lR8_Uyxqw=%<iV6!z2k0>KONVv}N(})V(+h50*De2gkm<d='
    'Y#c^fHouN%eB75{F#V#O9+Yzh3QLfBrvU8A`RcWw|9#l%PRE4YAb~0iLK({*A{e_dl}V+?Yy|Y3hZcJG+Tl)rqBVUB>ynsTkj6cp'
    'Qx%h?0`oP{bqFDVyV9K*g7XL%V!55i428P*;7+zu2jNfgrfkB%4G(fox-k(JWysj5)q9JQY^lcUw-KwKxn4V|6^8uu6jIcUG2t0x'
    '!}-pA5k?7N0agaS40*cZ<%A^YQ}DR|_)99mCohR!E5y9XhvWC>`{-g*@jo(}IVOpr>I$U38ayXT-KM&ISHBz&tFB_zc-$@b!<P+P'
    '=4d@@kq3Kd4y8c2CB;RbQwhtx!Vbm|tm5_^ophnt9?IM=TT^ma>Mb!?naiJ$1zF-LwuAyENZ-0@F_XdA_x|?nU@aagh|h1&?1kkC'
    'wP6Fw(a{T+ys`|P2_G@tJ(rz1Y+a1Y2o-D1n`Em>Ndd60qnZZotKT=qMDeaDBY>9VK`oCJZv>gcnL*EiCS@^Wwb+71)9>oUwHLq3'
    'f-scXfitchXO@RNrUlrn9oB5yvH~phqujl!&tfB+@D<MEl*a_5ITVa#Sm5Wui*lFxN|nrf`?pH<bBpP}7<F;${B_IFW(jI+q!OGD'
    'p#-Ry1z(BT5KY1Y><lxk(Vp_1>z~l(4THd#uBx#GgzEt#;cl;<;SDuMr@~_=u}aypbH%el;7v`tr`Kj0f{ef=MQ6e+kk+hhB73Ae'
    'i>}R7to^3VT>5PX$0xE4sNd$)u{H(^OhXy-l4JHJ^(5|ly$Th$2pLCZ1ny?W_I=rZpVGynG-=DOoClqbrqL571?aqTq8o#4AIt%r'
    '#Ux=f@)q-T=h7S*d`W*k`e14vFTZro2VD@MV%+x>Qiw84@F+!KotP%jDMj^s-3C@6&&IGTR43dBJ}pBG1PLIu3fH+gJPLE{07KD>'
    'Z0{pqCoXRgQRx_!V=>qYrXoo3-Hf4Q@D*FAi9$?$-4rz(j)9m)p#J@Fx_fzj*z#5j)r~s~T8mgt#+717Cyli2uq}@fQ`AAzrtCG='
    'U6HkTy4&OAWcc+ekqBkP5+f<(qtzUfVd$YX&oMfOZHJh3)ju94qJvrJ+G$S{d^!Zc2|G$f*2P3^>uFuZ$E+-B*=`q-;~k5i{Zvo('
    '1b5r!<8B}~f<Dg>6RQnp4fQ(!7@0wCg$Ae<6GDwWO9OS6Kd$@bR;dF$%}hLUd4Q)DNgm&GbGxWN*Vo@voAx5Vq=#SGn}5ctfy1~q'
    'Hhl8T%rL?t=0Kqzr5HpzMTXCZ0KsK8L(_-6DQS9J^fV_tMn;aoNm~wIHp>1wrs{wLQOjXIL>_Vg=|`m65jx2kSZ+)^SAVlFf15Ea'
    '75b7ko;sX%b#<h6T^})BFf@#Bb{+1HP&)CGTCm@_g_X#8xM*yP^2XO5!5-;&2tt=gMxCLmz`sjQUKYj4ru^`2#dE83*URS2sL?~D'
    '7NenIe4cj-SOYbN?GVd7)}}voe|~@EE8lod`yk^4a1j<P>sVB*UN^;1N2by&c!8W-x@)$u<C#-da5Zp{)0$(3okNW)+68-+MO9^n'
    '_Y{7A8_Rw(PHfn1o~BatYF&#Je**u3lVL$mB_q=53ad^%)J4;DYtiHU8nz;@k3UuZ{`fO{F+++c(_$T`cV-6g5?riE1`(!lEMwO6'
    'X2pD3@p-j~e%@7=GS<|LDgrMfUpE#Z$Kz?eXIvWOA|s`vC)<vD7k&&SuMrI!N@q=jU<&wYBi}|TACja@z(J0Q8pK6}K106AviQF2'
    '+6mtjeDkk?+Upr0FNu~EYJt{CMpQ8E5YPnqciQBHe_wSayX^9dVGoC+-=@$oQN%25I5A_dB1p1#&_-ax$~&yyxpI^hhiz_k6aEPP'
    'sK+TpSt(?Ckq$BW4PQ*3FxTHa@Aodc@@U?~Hq>n)2ikn*vM;ro%#H;Z&ZXWJ_8i4FHK(Gw<=UWz%r}X2Z<{#NXVi{c3fn4xKer_8'
    'm4Jm<Q|Da!zKLGGLC5j)6_fRK>#lgLV)=1H-P>u&;CN{zb`iV78pr`-7TbmxDqLbDX!Fjs-&BQCvdhc52#p+y$)$`4!x=|sDzqvj'
    'j>hrPW#oimbGLKZ<^GQi$1HOXVcIZu0U5d{$7xt9YyV4nM=Dg}Tv)-*<qq>|!8H7OF;Ff5b#43@nw<q6p~uoiiP`~nJ?$avW~G38'
    'kJG8)@{nGYi<dKccseu;j7e*!V&?Z3e#z9^#$@BpC@I2nXxO{(FR$M&pP@Qz4P*8-m3kgp1b&kQy-nn`VZg|XEatZ~JJ&l6A-jA2'
    '27$QvfOT<(kbZ{Vv1I7fm<Qa4xJgQ!gW@7?NCB3;>%P%%w_k0JWEVgHBTK>3A)<_dwWwf3$e^vWYB%Fzx_afEk;*5lbAok{{OC%G'
    '5k{q@_P3Enn6~8HRE^7~ANKe4kH=p(`j~68)&<Xsz7PG)NHon?gH0`FSa5!g_NewoiI}&(p@{O)ghMhxwu_HgjnAGN030q-NMTjy'
    'c-Ph5^<M8^4(puK%VnX_OW{Eqw7d}Tg4OzH;m7<<U_9ey?V4iud3qcCxeS)yr~CwH3r#6}p#xHmQBar!W~p%5<IM$wP&I>ncJAN@'
    'hvZ$$8)qcF;l+dS%S|=>Xam6m=DGb+pfGx3CNb<>{_Km)S^fUy>joMSVh^6Q92MzgbR}6OsZYgceYjwgAhMIH>|FSH0xxZVN-%qO'
    '?Tmyug%>K%%PL?8<pBnk3N^xJTVAuEXT160;vGbX3wx2FzHdjX&G4ony#0kOk~%n>>#*OwZZN4}c{>1VuwkfmmBXOuHV}w#8WzDg'
    'RFFYYV_SM`_D1RN?nOTsQC<G&)DTnC#w-t?vXe}x4;=@cI^&Ky8dEsI?!ALgm@Sa}4?M?TH!^s^kY8DFvp^3quS!m7Uil)(*iP^!'
    '`9JK<rO*ACHNQ$5vezmM1?3)%d2+%ChrJ=}Tvvi75uqrmU`%^UmQ$1a@^AG_*@G@zhfG9La|TXr45t*p!;O3c08}^gRV&`%%v`(='
    'A+UTEIhe<EULz}97M919Eu!*AQfoBs$jh!<^_1}(o{u~9ybKhnzx~7_q*HA$dZI7TtDsyak(s!fhjRDtW?gn#|8nNT{Z0wUrHu5`'
    '2ep1xtAK;PPvh1RH$8LO8%ACqS19rIF$gUi9Rb8_kCi=fIPpnxYG1ZmLH{FqB#_i4V$0r};^d*ZuVnC*n(I}fk*(R~j10|aV-7k?'
    'xD}NK-xX}i_LeIr!^kiaeHwPSYnzS~EMn(4W(llBad&eQvq?gPk*~DOc`GxZ3Vite>GXy_-}x(R^ScewOds4m?Phw#riC^zb7kYz'
    '#z>YZm((!SgZVWJzfGz-j~uyt)atP6MzVBM;h+1tkbv+ysA7;s730Ch@uIkD{j*d5KI{50$@1hwe1}P<!`YhA6V%r{ri;qUCi?7r'
    ')2;6>J2)c}_u*y!#QFtVu;J0k_ogE*(-2{OhbN6l6-OeE(LI>L5Vx_}<R<)O54#rjn6>xE0NZG5^qf$&eAv-q)g$5<6gJ1@R9(Gr'
    '{M#GU5XKttOc@InqY{}3DM(j)iZp@+P!J5w#o4+;PV-}S9ksB|G3|E&l=_sMI6@*aRP|2k!*jdAeh%vT#)^-JM?#dXL`>-vn9CSb'
    'BdZutu$KRZW5`QJRK;i`Z`&OGY;5I^7gX>@s1h_ytD!7|oiT^WqmH?1ScVP21Wj)?0ZtYQ>ycgi^QX4YhP(y?LTb|>A5P(Ft4L+*'
    '<WEKH$V6h2G5e6MrJr?*zYX8#B7S-!C46_^+daFG#Ciy)f|#&X#dO(Vk=vocj4=tIo~cU4ZBpu<4egn2NJz{mm5xnOP1MuI>;&bP'
    '>=dlaCM2c=psf@i+RnZylB1bTMkCXNp>jlz9q>g$mxnr}w5bU7<)+;E@=n$%jE}=%V=Q3KCmIa5)`LZSkWzG1>ST1LF*U&mL&4g#'
    'Z#i!T%pE1@9{XDJ|BN4C#>^_#tVJ=Mt|*H_e+-Ee_ONhJ4?9omOBA3q?`A{9Q`oE!bYI7?>m5RSuQS|*_MTGCfD}hl8do_RyVqWo'
    'u%{a~Jw2@xA@uCFoJ6@%<L!)iEnH55V-ezI9%qVC4;=n0_aREXViQ*~iF#Ns7l0W1xX!8PUO&VfNL1ZGg3-=+XKs%@_;Clnyhehv'
    '=jRv6?9wWPq+vjXfPiM_+y?+Zhb%D~*G&DdS^SFArx)7?xo4$fMkSGj8rdfpmUkdaO}oHRyDL_|?g&zY3PSRCnjYSbC7VQGkcXnK'
    'h^f;PY|q4=t;-f2e7XB!Zu|cEK*;e>(=znf*j?Uu49d~^$w<Zf&{OEwL*u4vH*n7M_DqKg2M%15$ZDx(%JtJ91DBWGqef8Fq%d!+'
    'ZrsBDu~0sMHr!&=vicD2Y1A?xt0ZWQVFuMY4J5yI8~aD1E+KvwZ~Skf!SMd+Vop7vQzVLVuT%#Oo5P{r*})rG=5p0x^c8jj;+x!$'
    'f{B_c;3_OLVg;@;Wi(=kP0-{&wy>`WiKx$Uq!<%2r75H?K=>;p*usEd9m3!V=bMV||GN5LnTD$m$wmeYya=Nl13%%h_!>G@Qt;^G'
    'gq#M9=1#1p4{c)y;SnV%_gxr929~uYhNZM!UO*GXsfI=|P}45|&^~rgNHyg|5!45S#EF2>QV~AoePptFY23P$r^}|P>wj)02BqHZ'
    'o4gg51G_Y%i%F<D2(_p!R&u=5L9G-iVU6X^zIqS%H4o{_wgwVx>iLJLtO)-Xf=5HmI0NIP@@XI$FFW|mCKutS8+Z;&xvl#`Gdxlx'
    'V`cOs`miMqmPrb)Rt}N|tT5j*^W)kO@iydg*DycJbgNb&3(wrNvOw0+Nq{f160_K7uCG3oZ(G<sG!~(3!FjJj(xQB8>-8E38iX@*'
    'OtaN~jj=a3?&JG>)?G&9D7hvQEk#VTF2WRNjC4{?fs3Qri+UEbIE&%h&74~6(u)Z-=q`pvZQP~EeGJa|(`lLUr)PXPM-3>;j;YGS'
    'fXOPcx^*8hW8q=Vuv}D|Q$V%6+ZZu8=UMoTRe-Z*H5iQ)cWKuq__W!keP=JH4BL(#b_n56qZU<-!Xk|5y&9Dl>H}dQ{vkGmlcY3n'
    '^V_zvhse!HaEe)kZ0A|hx#m=%Q}~EupctDw$B=92-nF3%P|jd$t093ug~F{Ffy^wSSI<SL)B$nPX<}pisJ-gx+NkkY?ZDkG{AHwH'
    'M-&6wA^XyeXi~76royY^d&Te;z=2Qom0Q{8Tjh2ztc5HTF;uIBfV+>}Hr#iK=zTkLQ<vA~+ROdn%U5UN^?adzL(tsN6&OY96xPw*'
    'G=Tt=M}U@-XtqI&Hn>4wA$YsjW?5eXb9)F!(nx;qmM5R<VN+BgNNV`%_d>T@-d?a6QLK;#ieg37BeTC=yA@F!zhHQHeRNFLTJU&W'
    'HpZ!e^EGv(SvWvAoH)}y3?@-X7a5L+c4axu*FF@ZVjq5XmHefhgmG7g11fOPqgQxnE%A0^Jq~Wxtqq!ZF<o1M{Lo`qU&u9{%vlU|'
    '3nhI_7U74gp+<0nMO#zSYi)_^EEmRWKUqBP>j>P)l@gvTSNO#2juLM!rkJ_&$p`D0Q$GbOrM`V1o7^p9GW;LY)_ExbgNxvvE@7u)'
    'keFH|sEOEHSKlMCg{y=MW!NnP!1*laF;9Rstfv#qOaj_5X^S9ssg7>g#}z^bi$G+Ueg!U8p_Jnt8x@p^oL$6{YBk}>rW<y#Q&OM>'
    'q^&CtCiVj`n|bShDO39>S!w?b2^xm>>MHG|w7WYi@3u-bRHUAUUX2R16HaF{uY!V%?X6QlnV8oJkMP<(T*rl02=g`-En>W$U#?Au'
    '^*#huw~5I>nAi@-)ek~+SWSJ-oyzTDhm7eEpzAq&l4Zig76E1}rp-u*>}CjywyQsoYX-hg(Gfy83`--y0Tm3KOfZN*tx%4^zg0b4'
    'o&KJ8;2Vt)x@-2del3j{cDPO<nulo4M9V-8g0*lPn^kR;2*qt1c|5Km-OYBGe%&yC0AOIZ#wiW;nm3?8g>)lVDVk#R`x0D~?zWAr'
    'bb&oDCX-aMUq~`>Mn*A$Z6poo;$#LjCPCd}_~EtD;vv=#Y%z!vSo~~>pEuA04ZbXf_aP6uyKF!|n+=Gm5qZdGgKaln{i&SWo7eS~'
    'iJ<T_6sr?-H9D!mct?J=uO=phA|A?!^5(X^T-#yhR|s;>gY%bh1E74<2B8*9;Y{J1Zo*!>Xvf=jbE35D+6ZbEZjeh2B^#zutsw9^'
    '-mDEfYrUyFXz5qKqE-8O&d+yhK%ol?#TXJAQ;rcn$EFTSA_Di|=4FND>2USAax0IA>G*vo+hH{<8>L~^37#uW8JV*Oln4E`48;IT'
    'RpZr$TXu1JFJID;lg$=K(>!7H6Fwv6U$8Gis0u+B-b>KD<sTtv+n)9C(`}r?2@{Q&sBn1L!d#5EakpwnNrk2mEx2zSToZVxfv_}a'
    'Dzx$Pn;yyAw|oUhMX!Q&206o$#k?@_RPj{hVKtO5N!uG|gGjo%WjjA`S$9LEsAq~vMYSAA(@Yz0avz%U;PNGbw7)6be{R~&o3XeO'
    '`^zr%k^*-@GPEUT@C%g`g$F9ATpjE}#DuUOp6s`5=1jER`&{xEOfqDA><ALHGhN3ZpgDAjieQH(+;y|%+DrM*`zM(D`*1pre(G6!'
    '2^T+53@u0uY9xUU=L!@zKrVvQwRxkrGo}^GjylhD=FMUvt{#98G73u^ZafonF#02mXxw8K4%k<w+jQ0S8<|;pet#HV)tAF6_}?Vq'
    '_+si98qkFn9F5Ui!xkYU1xn}*P9X$qn`<}Zznq`uHC-^kgG3S$KKhWjGqEu<Sv?NK-6@7z@}&`PuHDFf{%%aB9`t>K0WZuk&P79`'
    'xmz8JuxM%tHc`N}Q4UUbHhZ58RUer1Z|ow%2&Q8I>hu=$4?vo5yQpwWsUjozlW<?Tiwg|fzm%D7nm%sXIskpmjy7tHUTeM#$7$NU'
    'FjZNu{ZOL5^?AfV$gKehq}y|?_fF9h9-uL>g6(`vU*mi!B{9kyL9V+N0XdUh@6HO;FyYxKZE&ZZ#V%~BAe2?`0C86Gn2!wu;AI@G'
    ';%npRSxo=7n@xg_9zu>jR#!p$3qFQBg>QijWgv3aC<JW7)646(!N@jb*7Czsopm{E(U&35#YjgC)UZg$py8ue#5aq*1fTQKHrIZf'
    'Cpz$B+6WD!Y3RCr;Z2npb0uz~<Z@w>7=`&a7I5@s=jx`__mPpi089;PE#w_xXvn#u6$|vtp_96x_SZ?_uYC`zd)Ub-WDk@b<ebGp'
    'WWdAz#ppO0dmo!p>lHD46AL_O8(X`$E+UQL#A~2I@`i^PZ%mv^%vj;fs1A_Wl(zUPTdRJzu=svSoyYuaOdcA7^iEsPy=l-@(#z74'
    '&hb-1nMDIX#oaybUVVpIn~xhK2$8cj?-;ZfFP@Uc)5pzjxLMRn{Ito=`O~vwfAllnvO#soIND2+TA!E9zt-qREM*H*1TDJNLfKmS'
    '6lUJLcmHDHV9*}eX2!oUex-23(qT<8s9jT;oRmOZ_qplzt++d|aU*0%ttqAt!*a-Fvoch(F!6BNPvImc>~8+h^&8%o1D06TCZ%*$'
    'WfX0XB}<mG4#RMMk<ZL%3oo^P*NPFd_7VE&%<;<HA|otawkhdrti-1^CN*I*6xuKKrY87@W%oo1b68T?E;cbwM}5Mo*R0Yw)({}d'
    'bBr3O$EM@s53AxNM<4n!>_ntuZmh2|4`)ZS(;O%ABQYY2@hlvUjL_MvS$|k{=M6y`l2@#KhOnzr|6u3W;9vrGZs#TqKr>7_*~Eqa'
    'W8od6lyG&qyfAc~x)^xcU=N{W43L6aq1<@`3NQe|drO~c@lQV{?4Mq?#=gsoWkE41lV1ensEE<naI7h=0fXAa=~`F$-5XI&xg4Lq'
    'MbD5rW4Qn0e{9Hrzy!v*E95efU$-*m%Nsb2>X1j!SPj^k_Z?+_T<^@93<PA$OP_gXh&|Zpcff4cccOyaR~jNoX7L;K_QD+Pie=Au'
    '|MuF^ku)AL#iv8gr~MM{`Lz+rjKY=#Yqkpq>)N&7!0jDdfOFu9qv5H7^u5BV)IiHHEuf1|p^r#0F#6q7t?GG+J$zCgE~dl&^Oxu2'
    '!-ZcA|HQ||G>RD^bagSTp7}}&+8N-BoNvJseK*Ik$}dP6pVl@fl<nuo_{X~^TSC-?U1hEmNU2)y1OqV4jYF{_Ix7PreV>yb<2cVl'
    'uAe`}49tJN{Qh!j)KAev%(QrCPmmZv$t|63!c&k<7kQ7!QM|7x69PZI{m7pSGJgDVx(@cQ521Byf~4w6RSlC-Ut^l{YMMe+^!}`>'
    'SS|R}@pqqAtbL;^MY4_L!Sz|api^lSA=;kGL7T9~b%!x9Yk#+HdX`sx!sm$I!nttuCwJ#Rx%=)Na5;UcV~#LN3l~b39$fix9E?Jg'
    'y9Cz(1cQ&`pS`z<@4xpc`m#^kfe^B#BIp3;dFX5;D=5YE^Oe~WYW5*Kq0G7a*$Il4>*sO!)j9qCA2)(-7`vO{ssd0A4YZJy^DRab'
    'GYX>-w7tC8zS^<YX~yNt|9$+w()}6_{?Fm%>jnnvtl;NMxD`Ty#g6e+&ciyFE&y_GyZw1VdRkqRWcvE)%+8<*JU(u#AUOfzi4e9%'
    'P$&=*rWiuSwpqM46oVd+0QINj&!4S%{_95hZ=N07Lvd~i*254@Je4=TI@;^pDEFkRS+%j`Da-%7GUzsjU>jbFGv|UU!fuGhaFDd1'
    'iqR^C%}B7)yPpy+ezM*y3BG(_%k}F}DY8sMPt(3<%|}X2ZfS}s`}{1ZA3vp}{bao_uf`c}Fciyvh^{ES(RJzJahb$A)BPi{;58vO'
    ';Li5@*5gz5vNij&iHSvg_xvCe#&MQC-<XyWuX7y3K{n>HPVat_)8W&}Z{Yd!*TceN9By|SpZ0j%hz1PVC_~vBa&ILT)|C!hHX#Wn'
    '4^zZc7L=eBJC=^MwmA_d%p1+dKRawXIc6|A1j<mzYF?E?D42Mb)<4xx{l|h&E0Db9PtDGUA4-GQ$v%XqF;OfUE=?+rR)rf@Y)0CW'
    'r5!82K5jDem4+n(I?%HZs*ARqxL!qT-zIb!xPz&ry5YUm<`h2H=*@pfaDDyHVVbr1O;%yTMFt`DF`5*x(h#V)S5Up{P<#{Odb9ae'
    'tD0VL*r=JtFh|#spxm^iTSEz6hMPr<NW$wd(5=q1bk(w(7uXbPdVMRT>J;1+J_bW*U?}=S3=_<_7@m<|v*@W7zkHie8wKnirn+V{'
    '_+W8ZRE&@``d_IE-l{%l_TI91L!Z{q<I}%h!5qusG$(n-%azWfVKU7I^oAu#7?k2`P`juY!$2~04%7Qj`Ms6*&_oCqn9GO=;w<Mo'
    '+z|dN(!j7Q3B?QdV<u9?)xY}dR$wBUkN&9{+2Xs=fONXV-KGI3A&RgSh>^rFh-(+#Gd>o8-<eI#=SD?}!-qFV)*XT$LqSUvA>Vg1'
    'z5kn^pI_4_1Q^-N>Z17gGHl5eYJ_Je$ek)<LeeTi$nR)-;1aW%8Cez<#Qm-{x9>RZ0(9zXX!#@fRYMHG36w+4>S_h)6fPjS@UG?d'
    'Tyg9HFapSQHOMqH5fu<c`_(3kbJDW5j4%YcoeREfWuB;gUL&i0YMe0FH<Hw|WPBE1v8Snz7+`Gk-g;+@;gn<V$cY#exm8>+?(ikt'
    'z<G=SIh6V0zb-C*h)Sc{wcMlYTQRsX;{exT20|j7_RJ>cFq+8xz41-_xFh`L;a}VBTJdKh{l9*UJc9fJG;CA)fcS{`dBA{Ga4C62'
    'V>iN-$6bq^Ch}~Mph%_qn3>FbSz-%n9AWrsTg(ZXGD2J&wdUQg;T+fB{<>$pUXZ3~ECNgIgEQ+A*P-Bm0A-C)X&$Y;ynjHM4<DZo'
    '5l=s@$L0CW!(+p-CGVoO?agURI3^yVAMStfBjzd#{}xBLy?WK{sTA5lLrjJ?>L-F}&>X^66S<y{uZ(YlpDN+j^-F8&&&TC5hn-?H'
    '=01nPl@4LdUt?vjU}2WaV$296SaYbV_peSS`0wYS96r8oa6kofkruI!#dF1WYE~6`y;vX;Gz}pl5R=3Aue==|FmF6uBkN<#o7AMH'
    'WQH-soYFZ&)b+{+u7)etw9dcoHzeEY3Un5T$`F>;fFdR=QWQvF70$7WRI0E3+C|T@@vRXob?|Jp=6${D(imyvi=`=1JmRQ#p`9O_'
    'E1q&>3_GWJX|nY~h_Hw(10&Oa)=c1lMgG@BtdvgC5?yh)V2?UOFT+XL_4~`lFbuec3muQhoL;jbU=Z$s6eL@a5=*Ei3@n!Y%RfAR'
    'i<O^^Fx?m_$9KnQM-$Y7h-YS2u+YYED|9cQ!D%yi_P(+GYoBkUleBIF0Hy-re>9l2Bd4gCB^Eg5h+b`sy6H*)Oc!FR{foz+-+fQm'
    '4_n;X$Q36~9u3Cl9VE<}Jp+TtA__h>XykQyo%XLEHj&G{!15N{KCLXx&*u>L_NSju;@r>Ybm4Fos~+~X+05C~olnSJXii0>_fS@&'
    'raVR51#Cv52^U`bzkl0*Hk@~Ey@58<xI*)AEbx!UfD&OeIv)7S+&aVnmsq)D>nAhHcY^6(+}uS_{oEYl9j})alEEXi9VF+W?~S=r'
    'E|6}|5f7CSo#xtc*inb2FueBts4!s`Mr00JEdw>0FzP$wr(5{U_5{@3V4Hr0yC^fwR^k<&)5?jMiY5~a+ddA^DV%2C{iI?PW-<ri'
    'a=>JdD>7Fh**0+lU=V^K1l1Nt1)*&UDzDbjyZ6({P3Y4Y#E{`>&+lRxs?&(QHgtekMULDudSh)2T82CY8D9tG-TeId>C1Sx^|P9o'
    'RUWJl6JnUtivkjKh$yoL?KvmZpcoRMcR#EUTzxu$>xoD0=lQU#GYnr28y!xGt1gpz)vX>zkBXh}=i+J_5P})25<D<;v3KFkWG)87'
    'WlOaCFfQmhd=-Y=(&L5iKJ*u=2h<;iy$k-OX1;vUPci+u^V52s;kX~<94RIsO(Dx`V-}I4IyHM&-h_W(9hf9V5O*pyB&!LK0GLw$'
    'zBf`K$>QK(L;c=@>soJ?GoOdGd9q;^inpb<GAAv#^hHQAz_cmQVNr)%onnLk())+?uS<%pZ{5YqFgsB^q7(yXo?9J_Rt#ZewZVcW'
    's2}R0Xu`Go7X7Y3-q2F2t(usIhGrpvdys&FCFVF0Hbk$U%X63JeQWN3S_1#|-7^Fa7J5`3?AKZZB5qd1P@(duf=Ie=!9bwDMYP+P'
    '^(w^B_7j(5%XVgAmrD>I+HkfupQPbFZ&q8ebIp}Uyr=P|H>k{UcpzD{2z`j^wV|9IK#x0%_beXMQeU_329o86#uz0hI8m@G>Nt`Z'
    '1}+^#5v03gnwE{tbxYzXA2t#ioWIrNqlrmy!9L)A5hlZku`ydpj=GHRH^JUn_ART~087PP#*@nGwgvI%Q3qct*p4woSK(EIZi{N)'
    '+MB=#*|*w?{Z$#gj8Id;@RqQ(t#Q+1EEx(~KJH#^lQ0yXCC*SE%vOV&2^Y+@Swg!&rq2)v#Zu+IG*_+ovjIAPh1|J($GjZV{fN^_'
    'oW3l$n}&QUVo~kr^av&LeTzOzKgZ+cQIQ}!v-`TBm&E~I+X%STL2X6}i+e^&H1x|=E8cCQ&N22EUlHvqG$~aGR4XY_9%BTN?SMhF'
    'Z-_+KFT0Da8cYXMH+&~tgXXx&tsbE&ScXJzl*C4Xjoo$2ubPVu7Mgkk#HV8B^%y<sz`GfKs@MdpFcpi=b#vXiCq=`CzeB-F0#^wa'
    'tYXsZy;f!jX$_)mE8%jLtcK3sgSDoiIGkra(&a#r)vM+B5V;|+PjKubapFIUJfyG0=+u|BGf-?s{}_Nl@Cyg9hQp<?Vm&gNAtpvh'
    'dD~S>_#X%QfBhf-53w})@c'
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
        if future is not None and tree['tests/platform-profile.json']!=inputs._AFFECTED_SHARED_PROFILE:
            # Source13 keeps all original owners. Only the installed Android S
            # fixture applies the separately reviewed exact six-file handoff.
            owner=json.loads((root/'.github/android-owner-transfer.json').read_bytes())
            targets={path for group in ('legacy_workflows','source_contracts') for path in owner[group]}
            self.assertEqual(targets,{'.github/workflows/android-tests.yml','.github/workflows/android-vr-tests.yml',
                'android/common/tests/android-workflow-contract-test.py',
                'android/common/tests/ci/validate_ci_contract.py','android/common/tests/ci/test_ci_contract.py',
                'android/phone/tests/phone-release-metadata-test.py'})
            for group in ('legacy_workflows','source_contracts'):
                for path,item in owner[group].items():
                    self.assertEqual(item['source'],'tools/repository-checks/workflows/android-owned/handoff/'+path)
                    data=(root/item['source']).read_bytes()
                    self.assertEqual(tree[item['source']],blob(data))
                    expected=blob(data,mode=item['mode'])
                    previous={'mode':item['mode'],'type':'blob','sha':item['reviewed_blob']}
                    self.assertIn(tree.get(path),(previous,expected))
                    tree[path]=expected
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
        # This deliberately synthetic fixture exercises main's bounded parser.
        # Full source/shipping contexts above retain real Android13/19 profiles.
        self.assertEqual(inputs._AFFECTED_SHARED_PROFILE['sha'],'d63537504c20204de9d35d9be61da72a56df59c3')
        tree['tests/platform-profile.json']=dict(inputs._AFFECTED_SHARED_PROFILE)
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
        if target.startswith('android-'):
            original=inputs.full_tree(root,'HEAD')
            owner=json.loads((root/'.github/android-owner-transfer.json').read_bytes())
            for group in ('legacy_workflows','source_contracts'):
                for path in owner[group]:
                    self.assertEqual(base[path],original[path],'preinstallation fixture must retain every actual legacy owner')

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
        doctor='tools/repository-health/check.py'
        paths={inputs.AFFECTED_POLICY,'tools/test-evidence/affected-test.py',
               'tools/test-evidence/AFFECTED_SELECTION.md',doctor}
        self.assertIn(doctor,ios.INDEPENDENT_HOST_PATHS)
        self.assertIn(doctor,ios.INDEPENDENT_EXECUTABLE_HOST_PATHS)
        self.assertIn(doctor,host.CI_HOST_INDEPENDENT_PATHS)
        self.assertIn(doctor,host.CI_HOST_EXECUTABLE_PATHS)
        added={entry.path:entry for entry in snapshot.entries if entry.path in paths}
        self.assertEqual(set(added),paths)
        self.assertTrue(all(entry.mode==('100755' if entry.path==doctor else '100644')
            and entry.object_type=='blob' for entry in added.values()))
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
            'sha256:8e66f6e9de251fe1a19feb867df56a714fb126cd8e66e22ba370d03af4f90aec')
        self.assertEqual(host.REVIEWED_CI_HOST_BOUNDARY,
            'a66799656e1f6f64e4f48fee32cb1897786a3735e7d15c254652b48447afd08d')

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
