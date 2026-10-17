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
# 58f2fda5f95cb5013377402fa6dbc604066cc641 / tree 2c130750e80f2417b7be140a4eae74be7e7fd371.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = '0eec5976e1725b644d2bad12aa4d58453dbe0d9c8d214506751a679ea43d912d'
_MAIN_PROJECTION_B85 = (
    'c-qaK-FD;1lAZ7U7=1lDg#;2nVxGdw%lBOQ2Nk;{QHP|eyJptByT1)mYSn3pnILOy+n(vu)$Nl>02vvvWA7dR`P)D4x5uw9;fsGt'
    '``tF(?f!Vm`@7@bKON@0|Hto#-P3RX{-3`+?o$5k-+wbrGg$lEzx{Uj>iOGtOieb;FsC$iO+T5Gy`P45o|`e*7;?5_>x}+C9Dh9P'
    'zaTv9!f*feZ*R*67K&f*o_7!1_@l5|2wgH}$ip-?$>->Xab%6A8JoEqLTcu5u)cAhulDTYH-De+{@Crm%@4aj?(Q?c)*rXKr$b@!'
    '+znmZ_SOw^>(khpen{5mv1y&{rkL#5g>DSf=Zo+2^X{-c?)E?K;@2F%l~(K{4{wepj>hQ$=bWdxw{v6D#1EaE?^>I~g@=30hvVJh'
    'WqZtbDL?0@l%L`@m)3PD%{=GS4=#+O=Z!|&d6$Ci+tKn%o5tB8&Nb_n*79=~!_>FKI2c}UKX{gIn_%14HYrRw#^7@>pRe`$Di6He'
    'eSSLL{qw~?Z0BuU-s(SoJU)EB`jFbx**4oSbUfdo8JgDi#`I${o$GB#eVbAqt5)Cde$VlEr{8|KysVqr#!n`XQ*^oQV`pQ-@6O2&'
    'rb(mmL))|LRI}{gKdOsMkMqd6>1NaS&g2mJaEGaD8^cRB$;C8|X|nc%cN_LBM`VZ(Tb}Zlxc%~be)_h3I()hJde6^4K3~-sKA{j}'
    '8?3csXst^_Y|Yr`)H@#d+-Ea#lGd#H%rEDKUtZVFW0!SGT^E`-w#hZK3xNk6=5{1VxhC_8ty^~&F0VTKd2D#8qnY`AZ8Q0%?T8LG'
    'PTAQw&OZ9yb!N?~`<JJSYer*-VMw!|f^{Q5&rjXZOwNQZhuqo}nlaDwsx|c`Z{pYe?lEr;arb=rS94sNh9~PyHw=8&F;Bkl{MhuZ'
    '<81XYP05*c&wAOxlYh(y0(ai*vwz+`-Cx{Ba(umU$o*i6n%UUgnW?qb$H4J6y|sg}Ca!-FPtT8=xO<wnm)9S?$%7-14bFJex@fpI'
    'nm!EPai-gb&5i7_TfM&S<+S<p`y4K=ANbB1Yg6BkToQf5lj!}_#FiV9FS6q)G`S0Y_4<5)T$LBs&T;OXCuH^<Jnq6cMiWd&Z0l|G'
    't#Jg~p{e-oiYR~hA77sGQIT%5-@P33CT;!w)9!HG#>>%$+c<cat?6T*Ew6uaIeV_orXPrUF@@Hf-b|~v@sge|F5Eh9v20py3=Vvn'
    '^z_-u5Y3!g4#FJx67x7#FMRs&&Z{qpnLfc|{_}V_0QDU9G5fabJJ)qto9d@LhCXo`xl>IOl%*B-@!-h|kGschyd&&=-yXP8Ie=gM'
    'OWGbc=NnJA?8Ot=_u1Rjda}W8CK{$>C+--hm}rJxFM}sDUcH;;RO)a%_!n}?%Ta0^y2!0ROqTaCBp-;IlWV7WPGi^1#^i=%tGRwN'
    'FQk)~BV~%-xY!PEZhC&Z?_)c1HE>Kw_j)(?KH09#=IT9s%loJNuvy;H#hpxT;DMxZ;NB;Boo&<3A+<wq#%Y*`JdGpYZ#!STlSltV'
    'x}7%U_<YLyADge+gL0LNyJ~cC4YPHj$&oNJ=AO%pTa;YEbnLJhEl=tCUF`z@()U6z8)8Q)8v8)Bw4ohGzFyxosUv;Ld_lyqLI3pn'
    'T|A#F5C5>7>b;N0%Yn@$>&U=cM}g%AqI%zVV@!^Gk<Xfhc}lr;VY+%t<W%#+_WtX!I@S(jH<M8{-u8j3C3DV=GovH^=mDj!p=O)M'
    'aKn~L=@t*5Z=!2PD$s7A+H93|k!A5nCf;7-I_J7JUA+a;jzqBAe&=9s-X78AEP!vthi00o-*^U{8y#^!3<Tdf7(<+i#GmH+$8tDw'
    't}cHp6Q9PYrNh*@7`cSziSIV@phn8caqPRPzu^=e{r)~z-vToUZ{uSk`<Ms5k<7t1cI^2`Mm?c{{9tPG^>68vt-f9bVfXTsd?C>A'
    'nNWc>r02Yr#!v(eiT~RV(Y7WGw(*8K!RBAIr;6*T%d?sKDNvKyE>EeCO_)<OhA-JAK4V3kI5#)$Xt|>{Rbepp<nOKF!sKFfEnq;('
    '!SQ8N<@m1a`aaC0SvS77{Pcah-#tC@FP>iA<+837&NI!q>p}>99JnHaAHbT1>|Fppn7PqYciWz-Z&By%=sT*4aR}Lg(In83mIRFQ'
    'GLZWY9C&tQf8BOATav*0)9q2n1VeCqP~cUuArJ>%R+xr3IWCKiJ1yk7WxKa+?W$Woi~w3B#C+rPG-k4ps5%jB#6)rtJA*l;DgL6Z'
    '#ognAlawCVF#Ft1B=UAL1WLV6N779AX17B!VdkE7UHUb<I^^&9sZdo@vQDwr3#5o705m)=*BGvkw#yDQv?GxF+xAlx2}lp^)Cpop'
    'd7k1lcy3(Z3>^LlAZrF*sG-cgaVzh#qQ`B`H$Kfx=LIly84wTXE{=VeOaRf!?5=BlHp$!hwtcNnjd*XKoDm$P2iOGWngJKB8CuIH'
    'K6I{Shqjr+t@|QB+QfYZ+dXdm!=Zo<P;yz@a?!dekhaY;4@)_L2_(A)FqYIQO*ikUCMD>&{P}SBKcGe47|uLdHIP2YP3Hy*RO83g'
    'wzqBOitLRXGR$T$!@vonZ1z2<X&(F8n(Tq8L(4sA+IZW>4!f5<pjO;{&EVGYayG|$si7$HJQ<;EId#)uIy<QZnB$aqXc36%#w{tU'
    '+*FjXAWY<IfPL-QQ<=?yd!_|-NnP7#a8JUMYd-Aztl!S;w+}A`px0R!v(LS6Z0{otlabukle5H@#}vEHO*Bx<jo<b0@p;}p<hN?='
    '^6?+J^auJTBqn1^#2kQScr1Z@w-F>uXQ%Cl8^7-3{^fAwCi#|s>`TxnXP*30J)DpY-}J;giW5L-6AT|!cC$?`-%=5**o?C5rZXd$'
    'Xgj%?w>P)MaBD-u35&sY{R9?Kcm1D1>hnLjd|RXrG?32%bad>wFDU36GTGjQo<tUmws+CFx(xgNWeInA|F}IImLB58WGqY*{RlNW'
    'W|u<((-=vk1Kln^+U#foC1Ot9PyV{o+u!X<0bdt1^@Q^itvj1y-xAuW&mA{-YD@x-<CxT~c}iO@hfXuamV?*P{z%HA0KT&U-~u+8'
    'xpU~Nv4>QbKRt2zf6p7A9=Dfo5;_|sAH+Ws+F_vk0V<K^NRO@K|8)RdmV%+OAULmD112^NmpEma3ZyaSI8fMIPCO`x;G;;nMi{93'
    'mfoMF>Kr3>CbxkipZZW$D;=O@Y3-3~aM+uc4k{pgWxe>m-&1px#zbvlyOcUm{(iJ7@bg6W+;Nootf{4`&C<AH@l#<Mcl*5go$K)_'
    'U#=k(S_x+KIV{ciaTrEW=BZKTKGBRCs8fBMD>1tFJ9ylE&r31N6;!wi4Y=gkwsR9)=LO@E){u1SZUh&bsM<#w50kIo!@8&vBTu~P'
    'IM#IKZAYW44`%LY=yK9B7f^;O5T{VTer0GeX{L5`UbQwj%IG+8Lfq6k=O9`~cqi}f>K8u6mx^aj4a9q=ncH%GwT4sZ$fW~)bQ&)p'
    '090<Nr~kQj>Ay<Y%XbKk?1r?*le!8E8Cx=Y$AbsZZ+P7XoP>mIzJB?0w=X`wTz(FmI}=^YpYqnBg-~a3lMSH6+;j93+(@Hkx?&@B'
    '>vwZclhcs((d;DoB1@e)4_(V2I1joov>`R?KLHZ<h0DQF@cYYHPzc<lt-7q-Dv^-a_v|S`tKcKd1V=}vky5yN3w2Lo<oUB+L(|(s'
    'Hh{e0VH@!9J@s+sW+%Do$uq9l#*gFI-BTT)sgIu`0Z_*+G%P4WxrgvUosb<pCaPnem%ZX)?DIXC4uwkE{IU1X&!sFYhKBNY=A$4K'
    '2m|AC485l(Ohpc3jPC_}=ZX&lVCixbb{MGB1{NcoOIEE#puw4LTN@N2L3v60a%J&$CLq)%1k>mz--%o@(~QWe;YPBcTbAS?^?@#<'
    'C@}Mi`{=5yfc`>H(;F_8=O+hPadbPQ7Zm8(3Ea6DhpwU;I{osy?bGwi@e6PL;moSKBg4P@Ba?Uot5FeM+zq`tRjIu7<@<w6)>A41'
    'tqBkT?w)xpZC{Zk{j?iazspI)r}rCE>9O%gJ-RY*<f#%#)2Km2`tp1gk<&|AGFoa6`ovjZZ3Q^`*~UtwotYD${E5fX3TxmBP07tv'
    'A0w^LKE#;-<|-&N%VqsaZoIrCsT$v=vQwJ9L<Duf1GU(gA^SOwC_ItT&y`EQLSu@R8{UK8KkoLM7yi9M*3!2e1nx*WF5qEth${bp'
    'S|>LeGeZ+I6r+Uk+I^fV&$}~M;>%$l|6h|w${YK?Mko1vD<@8g3alm5EZ~`>x6VP&<Q2g^wWM4giYT1Lk@L&5@dF$?cf)pG0fc2+'
    'm$P0Q#uh4JjKowzD(9D)!@{4KNr%}7$>$8==*rD3B+k><4Vly*sz0AJa9&9Ra|;yJW^UsM%Y?T^?d?;~ACV;v74)m(zQW7)A)WA_'
    'TELaa<{$#Keu4o+kE%%ofpHv#fPj(FZt29&G`DZ=jM=?=Yy}<)$4<|SkPzW(g48wY2GeAKku$VnJeWM$+c&nQ4YYrKsb|vpWn_Uq'
    'RSSF0(JeRda*|QEqoZNm!l#2@2;tng=@;zmi973orib6t>bv}vWg>I{i>7N$st0yX^rX!Xq!ggWQ1j9@c75n?-_<GUAx6CG&|bb&'
    'gNNib0xt6I8Uj_~K&FXLjV}(iEvNvfzYDi-ZB6V-<QaVXeE9I^iQlcG=?}q4p_B%)x*pVP{udm}bGp8LTq@a@@ch*u3hZb|lLKL%'
    '?M3QXp$TM29>5p^03|LLj!4_#7kp!<tFQ{b9_e!uCBSxK3xGJf1u~tXj5k9YMN(^da815_Q-|&S!j9M?1)=h-IFvoWB9|dWAAq(6'
    '#C3CUj>ACfDw62(z`$4Yf5YCEOsAsl?s77d+G~(sC%!$ZVJe~w7TQxH!bZvo^!XPYf>$BH<?YP$k70oV$&%Ut4LM+;L7EFPaw9;R'
    'eknJ?mD_pU!<TheCH;ODrT5pRAh^nLGr>`YC;@dVfLegsn(^wl__nL%qAaj(1YJSS=05bqDa%nL@dn2N*9~nap#sF_o1f1)#9xMV'
    'Br@tct{g68s1P8m@L7oQKnO&2Xyp@Vr|oauOT{s3VbqA!2PI<!WrVj&r#+Alqiz7*jOcPa{p|7Pt(@zJpATCh0yHX@=8?{c4?yf)'
    'hu{p-|IEMD@xs(m0RX>sYb&+{C<x#~RD`dEo`;qwWfu9LX+4}Nv^JyQ@#aD`nYMcgh|W99ZGLS<EP$+!$1)Z?)6JQiNH>(y*2PKr'
    ')YO1L3>}y_I5}mFAG<YsC>60(X%r!?>qp813IY^)ow&@jl@d}63d#|wT>bB^Y&6mDZBR4VnO;0}p$^f>L=6wwf|LycwV?}PrjI^O'
    'u0Q`Ymr#q`(%^^0<y92Z`v*<rhap;ukX`~`zeJDmBL-*MMQU-fO#kp@16BW>L~EmeR_NEUEFW+O(^vOd4&YZkiW0sqJ9I%z@eWPi'
    '<z+=Vyo||AX@+)AU%+J&A=G{_XsNh^v@3iw9RZJCR(E-sQ^K?S=R&V{>OwD=CCvSZxD8SzNi;=UN0&;`KO>q+AN(l6U-?O>_!qxF'
    'Zc$E=C@)NxV}V0Xc8-7%nH#t`u=voJNUx|@S}a;+JJT+rU3PKF<x3$k=kJSjHltdAhCYPf2uG@c&zc$_w;@xwyVy^IV!%gt?B5nV'
    '5koG2Ctk>2-!-t*0DMQ<i~|HHzW8pU8t6}TaV-44L)blTzH@7*a!Lb?IZ;#h9Bsf6Fn*|CU^TOcXbsDd%rJ#Cebl@@Wh*Iv-|8(='
    '-#s6-dQGC&NSpwTM1Um+K5H?Ds*5t8OESQJZxT&UUs^Qz=cBYUON9B`iafn{dQ@sBUL)Kn2Z|d!T_*b1U<riLag;<7>eiU+Ry@3^'
    's-Gze-v0P<U~AP;jg8~erKf>t2l5IKx?u++4B&>wN*AKPatF`P+n2{p%|@cw+H{lhxU_M*jNBM;YOmx>u^w756b9d~+(^|!fG;!9'
    'UJJxqE28KK7|=qFAph{~5Tf&_9grHXT|4d`xL<as6#h(mEPwk*goQGpW}5;>n;WL3c>%mGCLe+ndd!Y2Kds%(0vK=ZGY$7r%Mqd%'
    '6l2Z;-F(8DRXzrz!MZ%mlN~{l!QiOMs<*Iw2UYI^N&(X3ZYH3KYK8(HL|;m2wg174cn@G&ZS}kO|KlCdxp*ur3CY%xR=`MXkk|4%'
    'lLFvKsHL4wRXoBjp!M3-E}8P-8{MnTF1|c$|EzlUz^YoBz7^2PK*|G+hf<u*$z-9I!)1cNM0RrJ7Ve*4HecaKKIB6I)}*JHC?0!*'
    'Y8zJeXlzGf0;JQax7Nb3<89>T7wiL4G}k*+_X5v|77bAW;usv#VV>3YODdVfMX<=pQP*^x`869_0H%s&w7~FQx{WT*ZA^52QA_lw'
    'kdZ26y}~TsRX1F@D=zLm%!tGG8-M%ycNY^csvxK-lO+ejWMKwm8tKTQ$V`rISCTB67D9XFeohF4|M5UTQ;n3jpIxy(L#hqLU$UcS'
    '9{OJ0`5p>M#>T@ce;;Ytn=bd)9;?;+F>N4lM6@HVo2VsV(V&vxnI&p)LTV)W?ml!C`FKB%yZEi@aC@g74n_6YnE|d2{2i_|3Hhao'
    'n#Ecm^Pgkw!slu+Y@bqzeMzM%Wf;LM8g%J=qmV!$ETuu%nIX6$LXAW9d4Ar;o&7Rz|2zuyU%=1HaZQ>X5<2n-dXFlLMHe8Q6zTzT'
    'ObtTTF}ii@|3#UqzE&vHz38Sik6?|dPffjSadNS6iRg`vV)p@*t=q_6RxA7ZO(0{U6r!ytb^s8a4}hyOyFn6zNX9q>r~oguo8Z4y'
    'M2!`9yj4n-q(TM+n*tOfE>+S`zE5NobB0S0JtgUtJ2>S#)z3qU4ys(iT!?@v;^~7!93dyh=La!dXCbvXTYcAm-|@Gb#nMRCY9Tt2'
    'RyB0*IwC+2g{@J_&!U7S=%grc#40SW9V!=`IQ)Ec(6t7%eGo{%)__BMi!3X|3>M0Tf#RmLAcC16|B<VtSM=OL8Fb*eu6WV&B#l!G'
    '<}h%>lj#}IYx)nRB^N2$Yh7N@2~Sc`O!SCNrr&Ry3}XsU0GT;C8o2x=!cZy&oI0H}ohNW71K<v~qE*M5>KhRdSxW?e?@!w8XloZ+'
    'e(CPq4%UC%oc;|mgNKT?t3Xpe-9*KX4aNxZ1yV;xxz59fo5aV~Lik9{HQU)fsqqWvBD~Dlb#0zs!Ydc%@}3C!T)u#~pcBA%5wIuG'
    'xpNL@D^wkV@dDiZoAxAi8+xhyz_nCju3=gtEy4i20CWc|6`^zE6NLI6n5OH+Uh^MWBCXiZyY>y~!JLoV$II6gcOVRQ^dpqLsDpJ|'
    'Apzuc(DCH}Nn=L-oBTDqdf@5M?aigo%v)&Gq>qOB4kI5Plz}Bg5kf0Yf;#{U@DOv&9v+u=AT5c~9$IiL&=(LM04CB$@H{STzL|c~'
    'eu%};enYxu53=`R5BpT{EHXD!C&d%4XM8EZ?XY9uoM4H7lpzhs82}{Wc+Ea&jj9@dexV0n^>I*hPgKGv4LI6R3}H5s^5g8mj%XLT'
    'S+~|OUG;G+V9n-qZ=Fu|<@eKYHxJZ<WUsKdf<Q8$TsTWm0$>2jv(4t~P7m1pZVv!(-pxNB9}1*8k{RSB5D>XfFa)CBvG{*cr9oOE'
    '<a3)+w5MON75&*|%m9m(VWeN37fu;|L_8K^48&NN<71wLbGtNLzZbDG51x;ufZhnj1pPMBq#z0b+u}_D-;&Re(KvifpqJ!)%|;IX'
    '@fl6pLHyuTYrjO?=WoChsj%=km|_ks+5Sw$LklhRkOE;;^U>t1V*gRf^i)v+Sk)ZBMk76OJm=tx8~P9!;8AYD2pqA(v0#AVnoXQO'
    'kN7|#c6kr*$0QR;U`Ko=2;d~(9~;>oB1A<n*uc9R>yJ(R>W{B78h<RF74d{Yvc*xRyG*JLt^&}_%>o&f^NVzuqCM1yvp18+vvm{@'
    '?$-iB03iW@E7R{8;ajO~K)Vw50+JSNns^+7R9t-!JCR^dx63X_ElD#~L^c0hNRps_Lfa<&q~+d6N2dnQ3sNIBP>HG3<Q)q5>WwId'
    '#~<+_pYygDIU&m5j$aoyfQMYJ%cMhwk}x!cE-pLziGZMx1$6sB;-D7@GGP2K+EazG7o-t<^bq08*^n@c^gjZ7S^eom1r6W>!_fVb'
    '4W%uvd&dIfy+y(v>7~)=4YK(fM6`<7zh>A&d|I%sW|eWjWJmk_&zDlnhs>-`hX{wC7bcHNDscqjKv}hK9g<swF?PIlLl3+A?Nb%j'
    'GSDXD3e38ovAX2T2CcSa|6<ExPst5w#d*1PN1z`EX*8Z<uKJijH-z9WeMGvYys^m)6e{!(Ln4WgfSFtA<|jqN@l7>d+7s`Gw?j=r'
    '%V{JK(q*FKBjRPF3=e+qOiGc{t$RA;BRADO*zS{mK78F3c7<ry!W9JBrQbQoQAKYtk!xBpERqP~P_%#9u3nxWcK$NdJPU=VfX7M{'
    'HZMLPlp+vwW{A&pqJ`8$XtG0l>z<CgZ~5s=o4uTDf#Hf38>v@(Pd1M5kZ1%Q2l>;~A$V`Ky>Ru0QrZiR-{-7<<Eh9I<l3TaMEwHg'
    '1vC%dsgs=@W+8AIoyB4o3i;Kcl7FB^#pdhr_*@m32#NGf+l5zwR|CPo!uo`e!2JTp5*Mlg?^ZM1x}ihdZ=Y+fe!5y=z%CRdqNlz@'
    'qe}7z2#Z%J<u~piQjt<}-msxE&6FOAkplr0WopTcsbs0Hu}46ng>NL63nHpMTz%lv?$Hycm+Rv%ukXw8+VGuvlrgYyl@l!(Il@Y~'
    'H_%^6n6R0UvD1xPde};8TY=V5rZ}5XHDiiBqmTi`N+81+skxR^(MioiM6$nPKU6h&TQUNYgI&VwJ#s;ii6Cu*eWinji3|j@Rt-T~'
    'r_GHUlAH;DxvB__xDTcT1fPa84Q5NZ1-uF02co>((-K)VSVed3mQIYLw=?!mad!FD^>Qh*^Z_v;@TAdbLPz!ODRS`M2*|vsPMcq~'
    'E&UZLV}&IvDG9GlPF8q0!Ayp=7)Ovme8C)V7i1D8cjtc5zUH#Mjhv!0h$GQaS|STqS!VZS-Vkw!m7tL$TACX-q+7MZ${J%9g`*kP'
    't9<@Bb+jWU_2MW~q31wKQhUhUxSJEpanGSU!hkF)D`2@oI3(4uC|S`7AiXl;byF?kFemFI94=s*-ngst{qgct`LO8Ng3FTMa<_X*'
    '*dBG0gC`=K2M8X9K5zmyrPprjes|o7Q%=Ht-diEthR80#Yi?0rTd^D=R6?K#6acgqM~HGTMz4<ELKeiw6>NF=j0L<m$oL7(G+ITi'
    'q_N87#!;ha0!*g8N#lFIb|VkFwAfjl%%d(NK2}cTX!W3wOp6A9O9NURH4$xZuwCqL6uEEMi;AK1OFD<|s;dOp!3fi)c!jFT9FI<j'
    'TuUQ@S0#V4ks^ue<hG41BI>l9w74s_B9x$!9zvMF&vt?W97QaLafhgoB2KN)1su9|PiI)<ug6s0(qJYkSTlM_;y_6-T$n}Or7z2;'
    'OpMe=ZLTjsSQWdy^ZTm=M=U9<Oh*LU(VW299;fC}R9octFw>y=ifn#$TJp40<49;8`gfjKiScW=&*1$>aTW6-R1l{i%djv4*BHr}'
    '@WQ#e{@5)!<f$BjGy77AiYRI@Vt`0$WK5=^8&IS`Ak=uwn$i#fAM@2WEYPApYifQ%b{$d!WaVX*Ed4i;0Cyak{`vzHdl3&P%SSfm'
    '`Ia4>tsyqYuX5eHydBJd8}%tzmSj;bX%p+y^@C}uo)_#G6pdG>M(2`@I*8~9;jm0PkT#dI4*MR=Y9irA!N8}3+`FZF(2`A#G&Qci'
    '$CjHk)!iK}H#=<s%-V3wCx0bZ1f-@VPd6KDEjnMAogjO;elN=%kF=xqv?EHi<oLWBszMvVKJXt$^g(5f){_nf`3Lhph8uVE{jtK}'
    'L*5~vE)0HZa|=%G$f03s4*^?gjax}1);?aH2Yq)+T)zuVE2a00yaGg<1X*_)d%@C9_K@6Js;=>urc9dr4LiwyiZ8E*b+zp%i%(1z'
    '!r&pm8%mH%R2?#Ohntmu6`?}J?CzFLZI`E$Yai2OkZ(u1B15c!+9D4;7*|-tSsBEDfyj`hn{M0DuA&}e+>f#{F?X3nlHku83h53N'
    'fsBgan=2xY*F&D#$x#@?ZeO4rS|#h9TpdQp+jwUpdn7(HFD<vND#KY4z#H~)CIiNj-VmA{%wl}X!0@pQ!ooMw{J}o1OEN{_$fKkU'
    '`IfD`-BU!sLY@<;m@%dV;Q-}D#xgXR=HOdNAml5ds^>Q6i2sVsl)HlfU{VXASLalZLSSfDqFM$10c1emm+=J2;fBpfURcmh5y~Wg'
    'k-HwYetjpiy{JiWq{^^kNWeTE1R>tCi=*5+HzIKru_(%6wM1!FlTMM4vLCv}ggX#B5ha1lsCaIPy>B^0h7*FuzhL%+zXn!&jMajR'
    'KG87bnef(Vs#r^=LxARw=Bv}JzjDvb(%38r`EkKUj|lV*xeV--7p1vRv@Iw(`H}&B<W7IhCCP)4W&$kb#IY@i-)OzzK4>)*G02Mz'
    'rZM;vS0rZ{o(_mJ8CHF6_56Sp&#S?~@}G;nZ8AwObBaXX1awJju$MPlprV>c>>4%1urRKtJisSCNnn5OPrQOC)dnqaylEuCyaP>P'
    'W+TKMlC23U0_L+Y1YzT00lNaO_+(#8iBP>OWbjch3u|E9Basr**~Q8OYuHvsb~KzP9^h!N-qpEzQoA2gVIazYY=O>z&N<CDm<e$7'
    '5ms_Z(ad1bmoZoG=RJ$Ec2gvMumOy!Cn(Bv4dgK>X}S(Q-7rvl>}*z~TOV#p|EzvbOY0jB0P=3=<0Pg4hhScfLL(A&B6TBbd2{Wa'
    ';@%&=Vhj1SJNmNz8(0bM%p?s3mL1@ykjQ2KnqY@fFF?Sh;A>a#<NjqgXUw90I1q14gG!nI#`Hgh0kY5*kvQHfc$tG}T8gc!W5Ca_'
    'Q{|>)E0kbQAgF`)uSscG;y27vg4T_dD48;nWS`P)n^HAgZP$m-N;jWO14)i$49=K7EPWb^<WV@dbVJ>6?T+4%l<Ey(?AnHi@U+jm'
    'S2f0|VL%$WAQD8Fg#2@|<g4GC9*#fI?OqWdsdrnlLu%n(eg+I^CH<mbN}k$d&`+(-y)s?9qjUL5KJ{|1VF3jw9+U|#JF~CkUV;S;'
    '<m6eScsn(|2C6M2RtP1Bo40dn=j`gQH+pY!-Q;5ecbaw0F>6xVNva*7LNL1w7bWByceeBfYWJjBgS`}9^yUyckde_^fwDj~Y6Xas'
    'NxJdFaXqW{bolymRKi$)p8%Z_kc{kFp>}n+EYa-Y=7l(f3W{O_%?HJ6^}fy<Sw8K<Ys8E%i;?sZ-U2Dy_HuH<?UjL9sDl_}#@e`s'
    'LN`HpOWzsr#m@4Mo2FZKv<ttJG*P7zHsKaOrGgQL43*HiqDRA=AMTs{#t7x$VM!WT#K+t%YZ9gp_Vm*q6;n$lit?tMOzd$o!XN{r'
    '1*awWk{H!2ZofQ5D6I86%GiGAJGJ7;CI2<Qyo^Rs0YRZ`02QR;As?9)5<tcr;CImVhjqt?mMfoa=G^Z-KbiC2o$L9_TakWl<}PC%'
    '6;tO#A!P)p#gv5v1O^WMXQ;I+=+2*PrI`A2L4dHptd`D)IynY4Q6c7w1>VYM4aUB$KUYT|fGE!d<K;h#+<Pc6TQxocuSK55AZI*i'
    'cpzf42mu&`!2zPJtZ7QO?4tA}h$ze<klP%eCgQrRacQjvm0%Ew*(=mUd~%xlH2U;uK5cb?(bIvxJ@_9B>AIjX6OUK}xG|LLMd_tt'
    '9>AR-Cs0BIy!X`ZE67l%eIVuY`?J;ENkvkskCA&pz*H0g(3s^21EviDisnB2Iq2REQ>5l~+rXN8v-ipZH~0E$sgEwxTNE`(sWN6w'
    '2qhq{&5iI{h6d1|VN5mIk6XVB{`*tGicQ`kqvis@*#)?O84?6jOuA~|&m#M!)8L0;-QuTLpwFP{J;15}XT*dK(jwL-c$3nOf&~tb'
    '5eIc?a~VQtSLox;GArq4&NW?G%L6GEp)qFIuwMhyGGTht7LOz@)VcgA>~{!+eOR}NGwk{LAru_wD73SXUl~0!I%F0tkAfRt8PTl('
    'rQr@3xAJ?W?}XD+oixyBI!dAy2jvdWEb3SY)Sa5Vc+c>TM%3sG49n|w0HMS$6DRBW0f>zu0}`4!kup@I_s-ppNQF450TUSee`q>)'
    'aT|*yr7Q&rM*0I>ED-7px+WkXQ&SVX!9Y4jeBgbV=6>aCIEUzWkD$sz4KIsE+EAy-x(bhsXj_D3U>;C5#gB%I6jr_wdRl={sS{dQ'
    '9t}8DeyqP#VFA(sbTIRa4s8^rhT9a=3*5TaE&sA5(>opuA0t{eejT3ix-Wsj=ocCEpg31RVG*e}3b5<a>a`DlY)jo~O~@4ql(Im|'
    'SnMIh*ws`fDm~0bfWD2i(A8_po&H2?dX#mE<`(2o<2hw9S!!Xv3SB3G0pPZDXS_I%07F=A8_iJY+Z%UM)CMt04HE#@!oZaWIZnEo'
    '2n%J1u~Ccn7D}?&hV|Rf>SwN3CAESfKNAWm)Qy_(3}l1z9ruNd5@Z3^310?zTJdru3Az)H`^QhI1U`A0=(Rx1MLryUf1D4eP3eEg'
    'Xp$z0LDeOYa%$i?q0}Ah^}G6gw_S7<i^gL!KluBCEwftBw8+ICN>U2QElC%>K_yJ?B|8{~V71rp=%fpU?LnD)Uz(DGrQWQ;%DDUy'
    'vOt#b6q}`h5$T(*nr1RE_I<j3JFpgaD2UH*kJ$_J9%@4Y%Auntm%Of%&IBJZx_ex9%wcmHmmw8vk2guFV9Em6mr+fg_SK(-F;RF|'
    'bPAvy@}Loq72XJB4!#-aIiN|6W~{a)STz4how)Skt1Jkm%ofhLbeyp~#ABKO+l+q6wpo?{3;NMjugb9~WD}gi6r#}tq$CAnCkuQd'
    'UKDpJr<9Tz-~Ljmer_@Si%}PDo!?4^HnXU)N+obU1SNoq+2Sja7@~==0Com5tf4)b%JolZbHN}`(^Y9~0m4lHBXYN=p1~U`sZ+sY'
    'M`D$mxpKv`Lf}<RThnV}8Uh&smlQe^%mUGxb%U};bZ6??#CGX76?5s=9qjhVHbDJ~Q^!UP7NDTkykyPZL_G=jy<db1xCk+hiV?WQ'
    'jO}gNKThf5jx?!cSB?iA9Zg10Fe!k}D^7GlY<n>W=qzRuHb&mUe63s>M+Q#PUyoi)&E4gfj`M*N5lZ8}qofd>Oz=>OfOWz&0iB|#'
    'PU|+X2zd&_uAn->jlieHYaob#R4doHB#%M^JAk3+ZBzTmmx;>-A}TsY$}tVL0tO^V;k&7!WAstjLXRkfsjo#*!*(acRDt@>=eRk('
    'Je9oFq`KkG0<DEuj*Kg7NGBR;wu5cCMogg&ibdJ0)?JV_J>Bv+IWqiykw{1xF>53R`6y^rlvEwM5azd<UewgA`r|1gI!J`BN_!gd'
    '=^y|`*ilquP7}3RkJgnAGiA|;?RHCYT(S7sPxWL^uqm65a|3ZB(C6`*SltR4gW}5(qJw8<Xn?e0B-E%`8c=usvF?|%N-y-ZVd4>&'
    '2k_KPl85g(bGuM~F0X&EMSGFo^V2u%&A-5^0f*t*DEQ<tGlLNpnga#>C~FXHRECca0R)%C3{4JlQPT9f=xI*4Mn(p4(&p`bq3rK9'
    'RR=f_YB`t>A`fx^(hsHD3Z2Lqu-u51tH0Wpzs{H@6}r!br;hjj;_8Unb$P_-f<eRZ&F<yy2uer%L@hW~ZebyEZZ8_!0?6WP55XSN'
    'u@|9>NQOFtssjF9=F4kToD}7UuPdHgomDRzXGR)5h}1M18jO$Uods(^jlp&Z%RQ`3KXiZoeC3sI+@O6R;{@PBSTHYRQDOCRQ}|w)'
    '$}qzV#JR<-*+RuLM_GZZ0UvT+a!jrabWRiiVy|LRWtrg}<@Z-u_K|U7zS=yEN|9H~wP^7t;6LDG*rKN*BcjtKt4?~TGfmUdqPz4W'
    'TalON50$^~f96EYAjKoo!a9!L88d)qaj}#PLYRhQsaey-iuttSVX=rlRMn*zYtoErg_qH2U@U@x$20Pt;nF}ZVx+WsvSX-S_*qI`'
    'Ml=+Z&NL0g6qwZ4800zxNs>%}4_Om65Emiz@utYKcw2Vqgck+h_}75i(=&j)M6^VqCbW)ZgbHT#f+moE=OQQkZPkVBQsozeJsceU'
    'F-yaQB4!@t#0+~Cf+Y41v=Ojj#XGF8Tv=tsw#=;_<d47~O>hdKth8i$N{2A{l`keo7}sB8rrJdp9?h%R26da{K*eWH_C>8mW`_kB'
    'oJ;0#z@9^~jhd69dc?JX8qySrbg!E@(`Tq1OA1>n;E!7p>=gkEVof^dwC@M?@)>ljpHDH_uUmJ)V=0!O3+i4+O9qY?wu?@&Th>5)'
    'V3@^@5<|%)h6F8DuKlViBqh7NEEgdohcvmAo+ZCtyc20vkT^1q4_$^q7?xb+vh%}_f@2nQ55cs-*a^s>d*nC+mddpMNqPe+RK&Sp'
    '1(nNf(_+Eozg-NJGk`j6d=1TRgh$Y0aVk+Az%EbQ%Wjqwu=aC0HC&$Z3+3YFj2=84Gz=J%_AeDPet+^yM!n6LY`8O&6r|XbuU+`}'
    'm&eQBP%m3U&AvvZZlp!PZxTW8puAQFjChf0e#=m~-f0Ng=I{staq$7u#qpAUO7GZV=rk}7c#^n@l-K~pDQ=Jg%(d&j(r?SJ)<Cio'
    '5P*>-!IF;%Weivg6$}wlv~{f7nQ;+UuUr|aII?t3U>#(Bv?axmQE5l}n~_E^ZIN@MYMhIH*l+9acHatp%%xe&1&<Z|B>hc5G>xwY'
    'HnlLr#Q9~khpmkgnzvq1L~&^3kc=Rkix06HK6~5%z~Mv+Qdp{Uc-OXey_bjMc9~Opxh!P#l00Zd%aec?SZz`ZU-LHs<1ucgUDH;7'
    'Pp^YNXV3C=%1;1oLQ|G6v>;`Tf`UoFEEQb#@a6)8plSy8socRkhvcf|8D~U#gBK5kU))sXM=JymFpt|W3x%O4#w3Qy<<GvzIIBM#'
    'zZTE{i9PV7#ZeKR3|&dAlBiFK&-CGN-R~i?BUPzf_z;1Y3ZN30J$G$_gc;?9isz*j>_B+{1B(h(VRP)(EXXr19$a__>Ttnc#898J'
    'L#vJ9O<vyqge@d>;A~unQ}w!HQi0`F0Mx*SQtMI<14WNQAmlVm1jC^M85C-4mJUO0lzwwBdS^s+`KP0Xh{LE^9vo%9WQ6*l<3Oi;'
    '<9zBkW5@}%_6|N_wt(b6;5mLPWbgz-{K~}50(#KADsoEZmCpnjwj<so{tvae^tm6i<X5>Md$lqYB=;EP_(#Kv+FN$63qcbRAyJfq'
    'G1rzXrzZF1-^w$^9(2Zah>1wloWiLY!$}Ij!&SZk0Mrj@)ruQ9GZ*he5LkQ_aWL0(UPe}MS+G1z*;bW5W_kmSJLF~SRy}1r+rzFx'
    '&&!Y?)ZhHXR??|aj2`s`CMqZ{6J;h`&AzMt-B_2M*1w$j;C@F5h)WsLPY%>_sulqU`aT-BeBw;cjJ09p<#~Y;U!Fy1DRcxNX7gCF'
    'CzcZ*NlwqnrdFW;p&kiH>a5sOdsCb|H0w$RPAPM}I%s4|c9|eUW3-V(XOUY`$KX4hET`IX<zyHsBhkIDaMxx!l32ui$C@Ru5XHHh'
    '2hApt2*WJ2%v8z@Pz65yxj(((FB|@fwfUw%nwiAiquq>NaTq}xFmuJmYt%><l}pqxs0YoOg<mICokxyb{?vL|b>mCNO$Gm)p9>No'
    'uLG+=7FOfIiQ{d%YW=fQf1P!`OtN_L65qijqr*8eqes+Nqv@jLWf6V0DZ2Ijw1YDu@gOhrJ=QOv1qF{zd~Y1$G8!US-@%iHNTpB0'
    'Xmk%uVGy@46uAjM?V)O69y9IzAg~Q>4Lv8QS{!V(Sm_br7$lqHF51-#>)$R=Lon6=&m?1k#Yl;a2`P{+?J1-YSOAG&$XuM#9deo<'
    'Q}wCII)`b$Ge9Xvi7yTz5i(Tjojl2Ndw~5c>Uv?t=j}5>lu{x_=_Jf0XlkU@fP$s`XE+9VNr0-THgehK=%cZf?=L9vMo=ZtG_}6#'
    '#Lh@Ed8A`bHB5#LfC)5RYyzAt6qZkR>Cd0qK9}({h8~KVLZ!$T62xVvFzhts4A?)RVWYM|=v#W42Rg-%{%tPe-76{K&3&(Wb|DgL'
    'FQ)=c*s_`~3mAc+OUqzJO#<i>s*+G9rPgeyX0{<hVvJJJu~Aeb>KQdVf%1#&6j&FV5KReyw$k3Tow_NKftgK=Mn)3`l|wytfG;F;'
    'M(U7`O)1oOMY;3koh(xrpZ&Hl7LX4H?ucLN!Bz*76dfvc=IdchjTm82u!{CA=dA#9s|2mFuVwxp;|DNf#wwOsi^OzvMU4vmAc+&~'
    'VZuT0W8K0>6`*L|nGK<*P^=K>z6RO#dTH<J3_EG>QOYqOg->&m!XS;+YcERJ(+!*V`(+{oJ-d>VC~nm7b^^Q>Tu#KXka!u7Gm23j'
    'IQTEQ52Dl+n^?&tn!tK-0npgTWllZr^<Hxzq3Q|=hIWQ`W_j$v`yKrLq6DYr=eL>JrB*^x8Bjq$fM&;cF91GCmZ-)xrv7UdU-9+P'
    'i=9O7S*Vz*BpRuaIfAmh1G1!PCmhwSSbg0mh#Hh2ME;JZ2k*uXn?%4M9tw4ZrcOt&Jtp>)E?el}^XA>$_WJoikmEs3JL$1uck#wG'
    'D2LWhgH(Kyo`QZoXk1*ofpex;GaX6}9B@sP)uNi|mZKkp%ah$hjX+V8W!`A7+(P|WC=S3Vw-{<!`VidHP|E;WNrHlg8Q5hSh*`Uh'
    '`jM!!#P7r#{x_mQdH*=gsR!sJ5~<wlsDpfQIMgRQcqPkRt~wZf1v`PPf!q%T6BA(tSHUtvtbnUbr$($Vf+m04LR}LQqCSozZOD)*'
    'nL^412>uEZ%)$V{bO^;0Hbq7Ezpnl>({S-2DP+Ka7c$CW;3s%2d<{BPq~Pk~NKONc#+_*6P1~p-JVHq_oC}7L0n4%_3`@~=@d5@B'
    'rv@~NLQS2yX&==SQkil>5i|)x!ifN*rB*)WlQLO)X}EP!p3X&6*S~K@gHktjlecs^V3)?|VkA@!gqo;Lti<t>4yvU{ku?@~_Ub*r'
    'uX)P%Wep^-DbHV`vR3{t%n)Iy8P33PQt@d(GTu4xnIaeA!wno{DOb8LXof3ALi|WSVv;SfSSDFstvE<BU<LENu}Nz~#OsjDs$qUC'
    ';})$#BhTEtut1j4NdRBSN(PBA<La;Sbqm!)V<D8yaNeyXEtGF#zg**h26ATBG+WxQ8hdl)KHlcDRvC>$$z>wZ+-jP2D^r}HbdsC`'
    'E)LCJsArnR+4{AcIknbFFCx^SjfO@Q?o!Bo7@XrzN6QR<dW;W~$na#@nyTzQOjZ)BYxkiU3r|ai#YI(|0!qt!)QG`k8u^V`fU{vS'
    '7*&cpk4qCg7TdI+?B$eUv!ka9Asp1GnW~1uLPqqw8Y(ZS4+sO{AHs&<OQJL%&2?L;A#!6R7&VI!+j%VMxaO!rqkP0+pfEN!X~;F`'
    '-rCRwP>#V?sUZP>3JN#P2*}JN^we_-m2^P3=xAcY_@Vad<Jze4vvy!pg}(&!>k!3&?I8Q28=*;o)if%+Ugs5tHvt^*sb9I3I^Qa8'
    '2ZpsE3xya;s{{e}q}*2SyNKvHJ89^<wYm2Eu)Y7vxA1blP#+;^7IXzj>G=wKbvKzn0F;LS%^=YnMT}-}1APVYcGqTE_rlzs<VdRI'
    'cQfxfuG^xhf*?u5mwqqk_K3F^SPW6DB@HBswW>!Fe_gv3qB#5l|Mc?AXR_3SyWLzErv{u)Q-?GQ4iFqpIMW;qOrjuNG;lm<S9US2'
    'eJG5IefsDs`Kg@*<F1zjD&QcGp2CCH65eiDj{`T;trbnYjcY5AcRhyXg{<*pZZy<QN_tHe!4H*&8iE^Gv^`3CT3f_*tS-aaBMXmv'
    '9f2EiB?(VsD10=#qk}i6DQ4XH$On7PsgGi%^w;mB$lYR02LFd?>v$;v2Djp#&azWskQlXysEM$*R^KDq!YbiHC%a_;aD0}H<_Ta8'
    '%hM4v69H|=v_&9xQ5{{ej}<}&76FmL^h>yyg;Eahm{CCuk<%%b*u{jWiC65RQc^$*h_)_yFk(MC0nEJRe^I7RDp}F~Gb9KLj@4D#'
    'Nolt^EAL7r8dRhS4Lvm~s2$-HU^|L}4BMMd0m?+vXLy8b_ppu&O(Bf+3DJU+$;}D_4aH;QMb#ZN83-meAIItkL3CJ5ea@ZA@~}fd'
    'eF)Hfl20<3Fk%aV*%Z^vNKkg;Wzn|!fUFt#9@P<oa41V7f&)}A;AEp#1Ic*Q;9uMO)#>kf2b@ub(5l(f^lQ<G!49WW2+f0Nj)@in'
    'H4v=HZ7fl>p+sn}+sN~73F+Ky+xV?u{s4dhyH#JQ)N8x}3RIA8$W;_g8vQ<ti{h@^$U+yWc`*%1CH4!MOdKO4jbIB%1Dw80QDZWw'
    'yM`aGjTTQ@U)Z9E6R`NPB`!3j_&S(q41EFeAa@rVpr4Hm2vZ}B<g;Sih1Eyp+}>Q*S4IQ{PlIALg08BQD#knHXZAH{LMX&TG9oiv'
    'x0kgYX8a0)oQ*ht4Q>D^-)MuN7Rz#`;7kv)*KWsf-EK~lma2_F&4L@mr3NJ%Ov5f9@G{<Pl$|xbDI;3?>Q}UAKhODjr3MsqfkIJ3'
    'LN(<W!e<zIQ4%3=dv0E=uy{H{SeptyZ{zN5C*`mz%SO^L))CJYO&Kz09*`0Jwv%E2OI60J`D=D@dN22Rhm%c-qscsB=qLD$F#iJk'
    'A_!FybisQO&71r~g0}LkhYz=L4kwssXrjXQsf4*O-iEuCh7_q#lxTtbh7XqsJg9+SX`rc~jc2ZUB(G<A1xJNm1=bnJ8Rkaw!ic97'
    'Pu9q4$jrHg3f_R7ug=?-?Y!f%Rzsvv&nPA-s>y+9n$gCK+=t9~;POQR$^N3;f3DijtFbsG_I;Ili2@hDHY5iTGx!;m6bcWhpycYn'
    'E{K>Qtjm-An$4Vvwzbd2XfTOy@UcUXKs%G`7zijymq-!JM<aLLW?p+K|8@U}xnGCV;pj&_%U<N-2NZ)AM1vZUK+CxTiW@*K1gEum'
    'BX1|<1<O{Q$8_dmF`=smKnOAlmN>ZaM9jg^AHj%*dyItx>?@|*IJ<r$2}{qnhrz45-!6jxA_<2R(`#selNKBrBX14fDl$?)33`K3'
    'La=dIyCMF|@zY$>1p{~>k%S1ZJ|x^3ZH$?$JPwGvQ9~`EwGeOCZls>StI5=!zONYYggK0Jp`oF<TO5nvJ@zEnhyvC|IdHnO*?VND'
    'y2qTqunUC|n2rL}(OaN@0Hl%Ig@s#+DpJ883HQofTwvJ#RAzG1OuA)z0s1sMM%5S-t@%!l(`fT#sxq%VD5`Hc9vTQ)8jyf=JN5M5'
    'QS`_IR0Aupo!9g=oG(d9808H?&aFj2&SclkS%E4Oo<eB@cbad}$)*Z~(uxNNXT@kfHW&b2#%dL>jiYBV{p)Uu1RZ(^2KrcUMf(#U'
    'gF6M^0x}ej$eBhVz&3b#w|*NK*-B<jet4?0E{84jWsv7I(h&x#EYe}n44Na)nT5RsKF6UQ)*j9i9r!sHLPKC0I^8~bQ#FjaB5p#-'
    '#f6E)Nao+LfYp~x_NvwE$jDBBDT7*D@(vjq;#@Hj3+S1HPSOQse~uJ>?R!|<!%j{iHBh$5IWr$320YlmFglKmebT0=^;!+zgat0z'
    'Mrjx8B2thOF9QuSZ`f<RG2&drj26xe)d3_nN?Z6UrB&Z7EZ#1u^O&E)<RLH8JKB2On><}5dRerj4g3@-v(Ugt-QA&j^$N2#4mXS-'
    'h@2zyj)C^{;!(2j^x<X?xLNd+__@f=`OCATKKe1<a)9d4;Al^hG;+Mi{CgVR5KFOzX+?`3bJ1=09A-YdcYm^QV9*}0O@e>J_?4C$'
    '79Cd9pmv(d$Vm~1(|sOX-HO$L4L3pzscDMQhrx1)%LX<OA}pDBaM?#Wi4k^-KXf_6bva-MtC~qE&RRy%PVkM9<t)Q6_<kXuF{4dh'
    'YE#vUidl7pest#W%D6=WSUTAzNgupiY$%sWO|ThS+An=k6Z~%3nn=MMmMq)FLGyH|Pq6A`R;fN~5FnK2Fls<OijI%(R)v$SKJ;bS'
    '36TnOV>y*Z&W_AZ<8wlOM2u)Oo&|>^M(7l4)_1E`-VjJbjK$i=%dU$02X=lB9E`vnw{s>9fMzi1q=*auZQ+VhN^o^?dBM;%It@G>'
    'U=Kmb@E`>}g|g!fP=Em-e75wd7QcI+u-_d^W8cY($$~T~6Tb+MqgJD_!Lg#Q0qn4e(>-0~Pj5tO%6YecRL>A~hJX0+9|ai@FahJ-'
    'DdZX=Kix{rmuKKKR0pG=u^6xopF7IFU+>JC6arH6(#O10Vh`-}9bh)rcSHqpU(yhgWGsGFZ_k*ctyuPq_m|gJN0RY~Sw{ysAMF>p'
    '=l6_A#wcvgV9o4;4{Pn(ui$pY7Qi{+i9^Gq3Zm~Nr&0!5%CrDobe29MYhd)JUo}<FQG2+fJe-*h`;XrbyQd4k82l4HE=(iM2tik;'
    'VfC1=WYNw5zL4|H@I*h&aaiSdNEvran-i4n<Inj0-P6nxHNmc8t`v}xUG4-1U@$ihiWQ=>P7vwmoP3SrJP)}(+-U~pKaPJMFOB+X'
    'ClE7Qyoo1>7=e<Tbb64dAU0jddx#wE=ZZ2y;N9zw{8*6j{>RaEVE^<XXx%bFlIn@78cc@z8m2j3O;Mtv&u3L>HSwwScXtccUg%08'
    '*@onS>ofHNok~U#LffNqpiS7rbq8a>to_rv=|Em}2cJW|g>&J`pKQ*5vU&3kxSYQ9nj;LQ1s6&zJ(!XP$AM9Z<Sybm0Kve=;h%lB'
    'iMQXoS6_Bt4ul|ER0Iy-+(>6bvI3<T{k&zi1U0*tClqt;KKg>xa{UtgH@?%i|5ymRGInQ%D-{6MkVgxNa(;x-gc(I7@*C-4CtI=B'
    'X~yO8fA9WRepuqc|MbVN1q_yN1%5sWH-(U}*q~FH{4$qL06A}a{J0=Jtxl69e!V-hGtdO?p35pooB-j8AZ%4oXdxs-4WYuenRw4o'
    '4D^5qP(LJpezfNKuZ8lTd3M+y66a>I9=w`(RNnB_p}nSoa*uSiv4tg1S^k%WL01@p&G1q<b6jw(?1s=7dXg5XVrZ3QGa^>H`;c()'
    '!Fq`#_*jr>>2y#jVwna#jrKj(d`PL0TQbEI`}{`Kj}IwnAFOx(!Z^bML$RB@x}xBXT$emNTqa?i(fvbWf!74F0q*Qnw;n!a$I|T2'
    'K@*Gc-Qx!_VI0mf&sWnj^g2V3gRJJV#!ruA+}@r11`c1oZf88k!R=1t)1G&QXn-Lb%24bLac@N|OjlaAY=k5*c`!wo$^<3Qii)MR'
    'R+$sQgn34@;h!y=P8>5ZIs}wKAxrbB^HMP3S=xW7pZeQ^`vpiY`BP)(gCEKOuM_(aJdF{>Lc>LqibpGj8?4v{X-ktUR(yFbGV>`7'
    'I|%52o|C99wB?BFR;_(DL6-q{Fe)kMKU*zj`CLP9{y~Dv=|9Lct9T}@Ot_Fikourl1XvjmsBo`9_3owkMu^LsHLF%-dcn3(GX<HW'
    '(~&^A$&%a}l;EA*EHoksUIzo+deh`p%N8%NC^bEOD@fH@+!cHbyfiQ<`Xz=DGfu-Z%$h|{wfN=R1htW1f0^nsqk#hphlPp}Bn|y9'
    'sS3PR`kc*Y%fcJFTaL%wKVN`3=Iv=ta>dIfori{rX*NKwEJ<Wg3SR@Y3l*abB&BnRpFic#R<5CmAY8y)hKN9%#rY0y2>vUifwC)+'
    ';sy6(Or+Y?zxrz_Fwu`3#NUVcN+6Qnj6?-cpE|BlY9tdL3O2WP;hOQW0QipC)cD*`k;37FH;1fSf**#0c2I;k-$VTTHy;i!`3?dM'
    '*~{Xh_<Zywxk3-&nJ<Vtm5d3JRx2StpEeJi#H`1RtdRxrRJCULj-y=wo!a^le*}J&*8m)$9Mr5_tw1_07ZAB{)p9jg9FQwXJ%dyj'
    'dOqW7OT6MNp?{!n0um6&^GD2mT;+ntQsxP@kJpIRK5879>oby+XNmEdPBBlDKBB<b;j{J57{e*YuE>elJGTlK40re}H*h>g068f0'
    'iT`wQ;fGLZ*sA58xxOg|3o{PjIwU~IMsvoPm@A`+hQDWg6MozZzefJGu4=`PMEXC)dB&|cegQOWrt|^gL&P_N0j;={ctpc)1XB)G'
    'i=8I&6i84=r6$cx#(SB>7N{|R;ZxhfoIq2C5EqWx@abtd$Mx60){NH^X&Q}%u+&MMSuSxp6gVJ&vQm@@?`1FEeZD05&sOpDZuwje'
    'uO1!+#}?z%+UCvCmf$ntA@aldANUc;Hu7)b(;Zi@TAoTlJIHG?G^2i)v?E5nm8~Y^dW3wP&IW#}2)EWRO;bPZ=F1#*6r-B^EQ2dL'
    'gqpvGl|2OuX1Q35F#-v!S*q&#)sYGQaS-M3`K7=CC72UwA@*VKV6mM_RE4}=SRf>5G=va=Fgd(_<%;xdz${fbJ=Gwc5n2VaYELN&'
    'aJp6uW()E28|8yFS?8Y*1<5vb1#}h=6)#I`fFev-NKrrnt(;>iQc-<PYZpDs#tZY4U_pQ;Bi2y0M8Xi%4?>YA@)J&`+%Y6G(~8BF'
    'F;q_T!cG%nh?FYQ>mb2|?2J|)^xk8B<pj&l*jLQ;i-SGV89Mrtu<Or4>O!&t><QKwnA6K_2rvllfh>|OkP?<qgA6QIEdTWUsFe?l'
    'FfELf!*|CwnxG~k9y7DVLJM*$<X(UVN1FlgfiqUW_W3qCN$Uy#Fe(uIk36$>$SD|iX<9hu5WPl?x^W!<jFXtEesTTz<}G30mbkOM'
    'umGMsG#HMzNSHnL3>ZYVD)_KLLtbb4T))0-BIgGJ%WH7ETUeT3&LQsgPrsbRxnIud!uBjy-PX0)n6pQBK11$;=F}>^2W4f{6i*TE'
    '0&GS^6I^)XfB&}sYB*PJeE@An;|iJw#{&LQ5R^!cPR9ejGHxA|Ok84J#nw+|l%E9CpWNKZ80qI45O2L+tdJNyg0=(6x%9o7JH-X!'
    'YCdtPjL>N=9fyiKEX(kk^FxIRX2FO|PpieFMk9=J&hXQ1Ic7C6tr~2jU%_3}FwK_4OP<q|6Pk)fCMMfH9H6tDW<Nbr8ikpegK#-u'
    'Vvmd3&q}h*#0>xg35Fo3j&M{Uv_(;QX&rr9VV>NC?t+LReqZyuuneWs2z$*tfLMwga!d8bMh#k~;1e024$7zb`C)$_Hl?36XjZvc'
    'A54hBoSrB^f({~zSp)4kzEB3mAOZUHU`cRwcLLWl9<^W6c3x%}9=C-KCy6UvCd|mt_{iuH*`)lra5WW#z>HNAJYeXycHwd|*CP;?'
    'jU{bAD<5g@SIng|ECe>9N#nqn;d6}iUl;tTX1-j9L`{FD98VLT;c!2Yb7W0Gijw7xnnlE?8i(4I%kYn-e@X3w!vkJG<mxmS@HL2|'
    'q}xG%3frR(pFZ1VtyjyLFMesB6wE^TZ>6?kPMWy%tt1)jAPXHP>L6D~v4Q{6=O63OOA=dOyNj1$c0}<Ir7&>DbIYO8(hx?hHn5-('
    '^@F-dO}Mdc(KiM1<x`2Iv(Yed@NS3BlZLsxBf<Is!|@=KrV^hgU$<rj)FS+sbB`goSm>%e^rb=|!p(|QSt<`JB5B=%LZBZN?Fur1'
    'c^Z~s0(`QXa5`$hQ!CR%k$GuQlcRskh5u;Hg-2Y|c%wH+nZw6}i5pskNuqk%P<%ZAJ=|G%&%$H+kfwTJ-2#$D`l~TYIu|I|De7<}'
    'abRj_L{QU^nord6!@4EmC~q&9JJMO=fk`c`r#Xq^0&GgsOI9W|Y^zz3Hm_XvHLEFDm0?f~&4Qn;YyciG#1iJwF)&qfH*yCKv$vH`'
    'xd@CP`=++S{;E?iLuyJeyjixkJtc_7l0iW;p?b9<VMv}Od_$9%tqg9am}0KYEbRg^eGGx1SW>yq!>ScO8ldwt<c`a?=H)Qmk4M|V'
    '>1)K@WXLBIi=o;@J>}0K_n#L%kbZ{U<x!D9cFgW`qL=9dUfKw7t3_>w5~h2Gl*mu>suedy)ERRJO*>W>fl|%MFNJbZuh3}%8hHaJ'
    'XPWH#Wvke#VmdH&17R|*L6GakU1XY$blkK#A=`mm5;xqs<rmFGfrUoB0mKK8h}WZf)WW+l{G?(dSjkjOo$F!Ux+g_L!QY|9N`j;X'
    'E||rnm-lL!A;gUiWt(7OsAOsA)P7h?8VZN=tVg<>%{TpGIqsDk0`?Ickxf9Vp-jYglo4P?C#&*R7o)!hU?BKSii3Pk%=th#z~CCN'
    '3Sf6q-f__q{_TVQumACX0Ls_@y#'
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
            '90da341e226f56b8dfb8b925af7c0273ecc41772ca424e3426b04c80acdb9a7b')

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
