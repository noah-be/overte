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
# f6530eddc3d9105923716541b47dc939746c54d9 / tree 2cd5fd42f3899fec562ca1a7b9a36e766c2f0c23.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = '3df5477dda1bbdc23b616ccd986df34aa6310b666e04abbf7a9b1e0e66cd9367'
_MAIN_PROJECTION_B85 = (
    'c-qaK-Ig0klAQ1L7=67p%*c%V+o#ac(LGN57SXH%Y5)|wxqJ5A^;rVNCa0?qkpNfHN~@k`w<ZFaksj{mX6FC-+dm$+r_ZncliS6^'
    'ej6Y5f9%rX;dF4jV@`*E{C?c;e*5?T{Ox%k({KO&n`xTC+TZ@|x8rBW-?n3Hl4*t<<J>j<Y+`b59@?CnG1}l$vST|L{eL)pd(nS^'
    'f7<)s{_EeqFY8$-e13S@KW)Re!fM`k(U>6(^Vmd}!ZeH{Yc$Q+<Zke>$>U&MGkv_;iwj@eV|w^wfB2H0_J2G)CVs6uZTGulVeuT|'
    '&<<{H+pf(%4nv%yZDZfrdA75gyD)|1eEad@hxD>PZcqEew}<dKg)gNQCufGP8RFC#+omDL6k|6xW8eE2jkj}1ezqxnyy7VxPY=h}'
    '?I}IP^pbWl?ZP&d)*a`j^R_iz8k&9_jO$v{`pM<i%{*>zI-AFFXlvFjt<@NQ&1}cXj2s(p$6?M>Kebbs+S&Bkji#I3=ssTS?NuIm'
    'xreknJ^b_4J#F(gEN}H6-=3d7UVVsd?0B};4_%!3xkJ<1-k5%jrki@}W8d=F$Ewv2``=SIJ?OU|uP-~zZR2K>#yL!>?L%in<1(+;'
    '4W@~saYNg)>|C?#-w)N*rN=z--E^79KAGgh%&DHcwlU5H6Q>ZzG0xWJzc1|%EJtJrPg|byr?CC>d)j^3?v9@xo!;}yw~tpf#s%v`'
    ';00Sd`qoZy2(20W6#Iz>p8I6Rv1!+=`ob^gg<oHngW4tQ(l~X#31b_lCQsh;pnYyfg4EQc6vDc7_x}2-+2yg}rH&@^``Tu9P1}up'
    'QejS$4P$n}^?cN8Rz1A#uC5u39SBL;&E8HUKaYSkH1lM9mwak%^v#%ZUbUu9@+N#f?4Q%-81^sMe>I;=)9_@S>4t%G9n$Rj&W%mq'
    'PJCN^AYM*p-LqbHuyfDpNZ?MJLvk<M-Q(45#EH`zhSU$%OgR~wIy1M{y5RY|O>gaBtO@HM#O~#J6ZX5jy}thFOd6)HABM>|LmVT9'
    'w@vQ{H}Ork4VxR;W4C&J-OF+F=hy77uJ1W#jkU4w$9Ww3h9}Xxxd|;dBqy@tDKx3`ZuR<{K(5NGYp0OA$q_PpKD=)9VGM@bg4ovE'
    ';94^gY=@@ew=1Ij;l6#^rIRAv=CFS~rA^$r$KC#T+J@`VrsI}!Q?jNHeX_j%c}mI6xo`S`s28Gdo$1ZIdK<6t<?6!i#BG^O%Z<SY'
    'A7?#%b}|H$W6Ot-Jtr}ZWA(!4gLhedNz8NvPwCIo^#IiKv5(2MUEfU|*EpN%=QR30@-@yWn8qthEAHdTkr$r!&)e`o*!#LYa-;GA'
    'esZsId)i!XJl(QazsSB%&c@b}4R)Dm7^6}qJ1Hibq1Vgc$&5GeX89`haXh(Ka>?saY8<-2tv}3`_c280iJLRIM$U2UnruvJrW~8w'
    'H}gt5c|B6b;LH@-VaiR<Z+CrYN3I4wld;YHlzSI#*CuoG9=@c*E<J6Qw{&$UGilv8#Bt!>_uZInqtvz?dSzpINb@*ye%pNWPM+P4'
    'bUSXy@j1$eZ=28CqjHt2yJ~cC4cSh<Nr5mjrk=};Ta;YEDEV$i%Tv02S9{OD^tBMohS23`Lhp%|*0<xx>2+Nb$@9C!2_lXS`lq+='
    ';^k6#xToc-KDcnY9@wU6r*^dMM1eI?iZp%SjUi6tiyZ6LHginv<ma2WL{62TwvV4r)v<OMyG%yaINN)!mc(~%$mJ*Ej~-C$8fvyY'
    '`a8B%O1F3beG{f;qyp^*s?Ane7g-jMWajNPQ#Var8*knMX-6d3ZNKtiZ@xdG>sbJ2#rbB=EoCFyn#PH^?+1c!_Qnur0`aH0{jnTR'
    'd{@^G%goUjwX~nRDFiN|JacXX4{D@dAIH9%`#Zj(lRG@7>RTX_@HQ?)vX4A)MiL*kv18968TEt)@`Jfax4)%xw)%Dz`2FiHx<a7g'
    'm{5T=r02Yr#!v(ek^j>Vf$G-}wxIy`*`{B#r;6*TOWDl*?5W9Ym*&`q#^)G};UrIyW2}f1a&za7mOE-w6$V33{@xlcOfJT$1>T9t'
    'Pn>M39M^Rn<$EU0y7RrI-Pi45zkB9iJiof@WnC+rXU?hXy!U+=xFWn8z?z2SCg1YRxY1*G-=3;((aG7-fzg<8@M%hOj+W|{1dQ_1'
    'llu;Q@a)L`y6tSXB!Q3T+oO;PdOvZX;@F0UK<s&0ejdU+aanZSX+Gta?cTSwn{IhO&I$aAVj<*t1l}5h>O`;+6Uaquww;S}_(fX_'
    '`{xBGDLt?uyVT7j@^&@^O1;mCq?z!|ZU<1e%so4G@z?C?n7*c6p{k~2okOn|ND)Z@Xn0;zW4J!rE={1J9f924x1Xv=KzeBBP7p&('
    'c@Fd7xN%)G@bL!#Su^lL4Q1|~Tlpa?dfwKY@i{l06Tr|VKs=zkFajwW52BUWUDvu~qO<wFeXUQ8cyErJ5gerVonWpExM<DLT8{Y8'
    'O)WdLP4@Thi~ML44hd}cv~^F%0y;p+Wo^qvJI$W7EoUB<asuN?c1;&NsZ*Tq-cwCV&~f>5aQGk4B4-TWJXtl6KFCcs4HT%xjj?U-'
    '+sqBw8#$!UW-!CR7e?9adQj6e_Su@`3|CIeJ!sl+-^Pyn*8`wd*ndvo*5P_K$9l1$C~`a*p=^mxzyJ_Gs|3hljy$vg#B}GDlvQpj'
    'N>~sk@-@J|cI>Ilvge*@L0w|k_6gjR@H92=_I=iGC%f&_YXRt;teP*Wca7~`2%{OvZ5=sFXn9Pb>!z6wmAUg=pPpax_9=a@)~<j4'
    'BbWZrIjS?@AR^`fEW=~*<hzX^*&IyU4|ksK)8X}a;wJf$z8y-?DBnE!CEvI8$#AA;-cgtVN*ixDRB6gKPU)VCV8v#XWjCD}!9?46'
    '%DlbY62q<a4PRLBw(DoL*{U{k0jV$l<oaz9JJ3Lm1?cG5b6-%<H)OKC@jZzw7;R7QX{yVxA77Vnmk!U{<8kRBUQNdQJkyU*qa#nr'
    'M=*_%G}<@by3wYICQu~i)cxeod%gYrz7+6vK~qmmZXRv0G4w5=jrx4z29J%2z;S#gb!(o}mg}L@%%SDO>u7&OWl;d%$pCNxn`G`B'
    '`fBVU*5yw-F8{A-<Kpx7`b|P-gXDwwXM8&hbU#2PVh;4!I{t45z-1{IDhq<ksx@F@({PDXmZ?A*Lka_hz2%Ds1rdA{DAx!Bb!X|v'
    'FR41m2%Sl-r^u&1RMkocC|X*3<QjbJO&k3T2wzz*{@CxS`IN>;ZDBi_(xCkPXjR~+ne4gaQ|4GxOH-T0amC{2!Zhp;Y4bbR<1SsV'
    'Arx8(X7oAi5UKu#5tMmuRJqSIqXz0!7jh*=_u~$p_g~XejB*7Pu0jJYIks(X{M0$YxTG~Cow^&r#b&DZk;cR9>i4iNs)WE3Z#q8f'
    'hSpa{qpSBOcQkbQ(h?U?8Ym!UU%!53XfZKUJ3<TK@PVU@6JMMVH?_|B5bZ>GC-3g+7e2?Aif2v@#CxZi+j4!irV%^ASx+CG#tR4l'
    'l^ev2p;^21UnT7IJA_7dL)zm=U4?~=Et&nqg9p%Wc-;n^goG^LzWk-z7hYbkKL@@$15<)O<*i#dIP{f!Gk_9v&(TkqMj9>i4I8Oj'
    'zso&MPD9p5vy<eDEH(2zbWmib$$>6F>4?qxBS6Bwa5?xC+~GPF<RPTQR$W$Zl|abrd-fEdRd5Is!Eqwfh|%A?g}Ns(^88t^q3P`)'
    '8$jN0unl<lj`}!pvy)u)<QX??<J;-;epd%*>hMz}0P0K&4Qrmri6MMYC!~oU6V)-#%ii!X4(Sn0he9Q8{y4aomr|A$d_(!0ITVBf'
    'VPIU2zIXJ5smNiBabCc8Za5eKOV^vQ!$6%juo&rFv}!E^4Q9G+tyhQy<t6P)mBrhIfKZzd%%huKCvr)q8IfYcjbuT$EXhIaJzYjo'
    'VDgIl=%%cI{z6aFd*J!=lRd0Bx}CuZ3UurQ?pz2%S5Xa}fBD09_wsuB#9M#5u&N%&@E`t2B;LSkR76*IL$6L%DsO!`e}T-NQW0oP'
    'fCzAR=CQPWMV9o_Zdm;xMG>EV+?Yy_jXUYlm4PEil}MUK4I<K)<5UE`UdocuQhU%RPCB&};OIviE0K0GUx4x_9!o2%fh#n|DN}un'
    'v_5+uG68I=pv)|n^&7eI`jVt-oK0n?G<%5%>VSJ{u`x{^xVm@nL`Ih@mwbc96e~Bp2X}bhA2zT2dxfl}Z}||oBk8z+hlL@i`~zy8'
    'r_q=UP0Ub?62@!yajrZcE?kLE$3yskO&%$4?Ee~_<m0WJIVCEvmQ1sNXOiAdQ>6Q1%*4qh<#Gdf20%IAFVDseaO|c#w(|xcEZe%C'
    '^;$o+PzggIrV>*5eyKSu{E19D%sxmyGlZiXH?xp9&!-zQsXJC5pE&Tnk_M(0D5_1|#sQWIZ;jg9#hyPROB^cbSH*q#*X>h0<3F{4'
    'E0Jx22qYS>Y3NZkksvURqYw}<GTJSj_?hPZ&0R3NA0AtQhr(y4=S4^e@HIi|8g+wdGQh|gS}`6>n(h4?+tLO)yuH*5>HIpfK%c6G'
    'JvY%UH}G<zQMaR`Vcf!}gI@^Y+)VQ?*x8Od>xrg^JJ9O8e##ON+Ji;YwI<aAJ12V5<_A*pP-CchX&X<y@9*E$Iq4xr{LrDjeyMr~'
    '$!i2$<lQv{s>lZ!XO0>t4z?|*0I2`u@88;**cHh$IQty@-e%%=JJIxq;G|GW16f@U>NWQZKFdqGzI|RQ*;oJa*&Pe)Xh@R-VV>;;'
    '>R6!(WJnIc7y<w#E*FkS+x{1vvGY|}1z(T!If)WrJD~+Y9H#{`%}~ahp$#IbwLG{c-M^{h_HkiHY>|Rc`Br?CJ-{NDAw?g6wgtqU'
    'vY#eC23l8vM3)B!zMB3U_O@g?6>aw^MKi0t2Kja7>`@I<5hbwDo)Qr@Qi`C@zu+Ty69Qb{PNshh3lvC})COp10v1BdLR~QTMu0T^'
    'Qf`DBxAV4#PwTEq`u!|Q@2`tqaMi@k1V<U71k^3mEfVvX@#eSqeOJpxSzz4=x`Ld|edvf&mQRty8ypK<*SDR73J{y`em<8Fe;v~4'
    '+LmI8D~AgiDg+2Cd=_Fn5CTyhTKNpxY5RNkQt_F!Flt2VgOV|VGQ!)X)9%TKQ8$2Y21hnZKYP4;E0_A==Z~!r0UDJ{d8BjVJP>=='
    'AvlBdpZT{sUYI&60O0p-ZN-)V1p$1Bitx42^UxBd%p(6Yt%Ea#)@Bqu-dw3B<Mto{(Pd|;O>eD;1(0>&RK|ic-JIM6x}lV|Q<#-c'
    '%?${|(1D4AlT+5Xv0Jl;QV~m)MiJ6Z{YZI0L4YE!6PKB`QbdYDK{=X!sQ=xSjVAiN4Qd9P>BU1A>JXjG)bNlkNZBAz8@do?e(!K{'
    '{kdH(p%w|vn@C(vMKQg9&_sS1qNM=o#dG>4dJOL|IO9H0i<4!#r%xNG`aejtHu`6UejUqlfIFDJy3djazv@wxaJuZ!c`?Pi(WUFl'
    'igI`zlbK_Nc1~YlN+d$4Dq+x4aeHZ3I5Qmqk6u=HeVKE@v;5~muXpZzFPOz=1cfb>L9|dKMO#OgO3^<dnu+iHD8XN8Csh2CJDj#C'
    'r%03+rpu|oAtyVJFz-Nvxk`}ZG$zn1>XjCYR@r9SMYPMVF1ef(5_A5(NM|#u1!(9)_ziHR8u+ZS0dgA>h5Hoxc~A^^?~eW3f@fmL'
    '^>gBc?Dbs(OAWvmNhsfT(1}Ma$!Bn`i$me}9sT}!^OajWmQxyFOk|;^=hFrp0po}I1y+MV6C!Bu$qb{9^Lx$fbG8!G*R9?n_1()!'
    'tJfrYjl>DiNCa5&!6z*?q3WW{=aTgB-y1ZzgDWi>-OEYZnI*#fZAG5mU(c1N*6<qPMopl&-qB^Ee+`yE7#&ARB%yANscyyNcUAQZ'
    'MZxz!z8=_GbyPz$adhcvAliYv0)%eZ!3YDmp|R5W;BMT(%ggrlc~i5IAhtH$q%<yV+%BO5Mx5F!Ia92M77T^K^(!}0^$_6847Arg'
    '@z#nciX=I;kR!-HTs!zMIn)kF4cD$6_D|d|`*R9^p*@z*J`!P}OsLsr&!^1|)6%>EUKf)OK?*(Qi7Y>^-OU0RZypm3_fpFdq8Ain'
    '$)tk_#a8(kj0QWUAtRp#Nd|+XDy!bYat^BA1(X7$$z3L(iE7qc$W~cOX|?~sjCc=VT5a{a`2XV_(7AXnED6bWBCUXt*dVXvcSZ%k'
    'kx)xJovL_*T|n!#t6egt;}^PDn|*kF+WuMf?15FaG<_?elYx{68V{v7ofCxrWW0n1+7@Gf;}#xYUN@iNM?R%v0oJ6a7%3imgK8UA'
    '_GoNJVgjVoskhd`vEyx|<`?V(QZ&~)RQCeUh!zb|0pb`O(jjNH{h~@HaS<$Xa?~|lXMW9w7J#Xu87(lpmu{mAxebxdFKUS%6*5wV'
    'q*s{4yXuA;cg4khfEjVze&KK5{_bkxMHK`!Wwzu%GpPw6(?~}aMP{7nc16jeX(6;X?&pj^xNlDcG}TCH`_UEqGo;!;{3SbT^3eC{'
    '&i7DA5;h)I`TI!A9_xwz*3WA7e(<&+a0Ij??KD$Mz@kAV!8420;Dppb^4-1bD)Rn*p7-HP)yM57^>8Sv$Ic9Jb>Q!CrAf#yO;i?Z'
    'fy_UL+J!IGqTlXfiG4|>DrFeKEEsg@oKZ-i5SFkw0Xs7US45~`sQ#W`wqb8S<?Wv*q5cc_c|ER4vqM5h9zpL>WwGc2q?1BDK#r+F'
    '$U4Sp-THq~rmC+M%5*2XDa|8TW9m~=FWU|(5nLjAqode;0A=eoa*)-^p?(v{m?(v4D~cTeM2C$GjB5S_Nem(xGa*0)c&Xh4|E(fw'
    'thnQ?QmQBwG9cLOp%8JYl74bNkyYdbmmoMw(i?Yh&UdPxhZG%Dxq`V60aL`&2ZuO9PK?hFVz|yiYME^HUH^5@-)<I5BUP(~=tNr8'
    '(7o%30A3WfMkzmw5|*HoqQDWWu)MafTyW;&=g>jd8qoGZAOTwg4(%<nEFThBC>I8bo6>>^X1@JLs*+yOa|dP62hVlIi_Wt&PA!<j'
    'zzt8PXF#v%Ka`eSq-bw-c|j*UOF=QyBQ}YCzikqXDLesW<}}g3<u3t-QYqln>7?mAfjb!hceoX;I@VO*h=9mi0{DA>)@}z|yV&we'
    '_m_6C{^RESZ;%;0RkU3NnsRg_6+1Q<Bg7X-9UbL54<Bw4hpmP15u01Kv)!rj3+KYWX6(8)FR%WM3v+!>gnTYvKwQuX;JX0W6Y1Pd'
    '(}?N@eI+m+E>rDYdy={hy;OSQS}HNuFfEZ5VE|qLx&xL9(7EvmLVXWR)AeGnx%VuQR_y18_6_MlPN(hj^=pbd5C%K?5z1cF!Md%G'
    '0P=Ov@#O=O#*F+ox?6Vj#M7bMn@XXXx6r6b9}M*!Mm{_!151b^gjSpccK{aPA?B7nJTL7)S`wu_wBT5vFCaVsOr($Cd0g0>nSR!O'
    'h{e!;eY|B4viD&Rhgk6}5;s#P#Z$tzgL(|Ci##&O5&<bg9FQ{rNQCj0eb5?JHU9ES55DSfP;<{z!YB>+w4oTnY$WB!*@GR?E}F7#'
    'tzo|Da4cZW=6r9RzwGPpr{QiMs0YbjVQ+bXWI(xamY@W{01P@c>9(&2Y<_<L0J!YtpU+PPQXR<*@)8J$+$R_UQSVs%zo^n6EfMm$'
    'O)1*rFW8Fy>^f$E#mX?!uTBf63_l_s3o!;_EX?sS&BD2-INZJ$u`-X2!%{$Rgkpkz8);Gyg@A4GrhsqBXUJ$Kd`+O2q;$(hj_&yd'
    'P1;fX;B#xgMBL|Zz!Ryk@Hmi%U`w{2sd#9i`5sarjA{-|x+(Ubq)d+$6@XRE0c<qV6UTE7zPO<efdL-n7L33VD;x_3=x^D?`FMmU'
    '3bE^ZfIlXgNCZ3Lm>__YfPVz}1@fU;4!92QZmj=o!e@7SlhL?S@mpzl+&Eb#Q2Yt=AubpG#;f>MA`W{703kx{sb2rP$>YU33JCXe'
    '0U>~p0Kk>#_l)qZ)Ha}933~xa3pPzW4nZnYeGog7V9&S9-b*b>GgU-2_fklbpngKzCjF%4-iL`!4W1XIMrxoEQ>n>26!6s>Q49~?'
    '!c)5BZ6WZ5D1SSBUfcklQn@aZ4jD?q&=9(~?C2)~f<hM1?E{H}ULeSTaldF!6~<nWM)1)?gfC}9!YtDN0PJP;r*a_$@PT1C{gMsE'
    'Ev|c~0^_|!!XD_Q(dhNE`5HvD3fR9U*h3sGSXWtP+%MVDA^r2U6!Rf7>*x^S@bkjtQAs6^K(M>5+P4#uTZA!oymv!S`^W9B3Tqi?'
    'lW_$mUC>xva<W0IE!n@=ve;8{Lt1fO?%fgS$59%MT}V}j33NjU?$Sr3Tgn@o%|M|-579@G2nm?EmF|90G#tOHrb~O`{qT0ENoYBZ'
    'Q%g8%>G+6v*(k$<-<wG(QoMIh$8_SRdIa0uxtHVTePLIKb}d{%kX`zngB(@#79+W)6~iKmAPz<Qm+k8H<!SG(L(N$zJOw;fqOf`K'
    '0ihIun3Ews(}@;R5248p?Y(<C?Z2emg*JOV*#g5AD>hKCxSnhr;UUooIu7!uxkK>YYJ2|X4aIm68h=Ph|HiJ!5#-vUY()J6<pnek'
    '-svPeJIq4hG)@+aT`1%?hf4l|8Wo$*r_)PSU?L>aH*FVQ1zrsV0}JaDLIU>-97|lN2E1F%aPNkW;jn$Fx%%m9`2o97kcgi85{)X!'
    'A0RAVp_JdagGfa><@SyZm1(B*NQ@i^s3>DgW=thZb&Wj&5-ofqxm*xY_5S7$KJK3#aeBEv{_^_19<L4O)S--lg{z!s!N?I-!o7k1'
    'O2UNAgp8f;+|tulQril&jxuGk2~{(m+!=)oC>HkLB(7;{0U;)-d5B2%SL}zXCT&YbKyt8)c)bTM2r?0*ZLqKOp<yBe!K_t7kk)B)'
    '=Y}L_!e6c`LL=^jDFMN!;hP4trQ8DEgzp1UUhZiTkt|q6ck7nUjHB=0*bj=c>#wetOPM8&$ArL<MxzNG)wid}!F$6a^P)O!e$}@0'
    'SE!5?maL>Cyf!&m;o$@`8P;MLK?3mwn|Qk*lPI~n=@;!Qm+fuj6rDgEiH_0|S-8qvw$QdPuAYdMpphe5nmae7TeZT<8e<lPqYUd6'
    'G?W89(T<qai=#}1o&zaK?ICmLZq6*n10UT924qoL0m~J_A*qH%$%;+@>6H<$8*woXbFxmt;R2@Vox8f+AFsR0hegL0T$cQnyWPP%'
    '>rppN@I-|30Kvo12Ts7I^ww=X?oWGh%1O8{dn;ty5ZNVoO)ctcE0!aKN(dC50)W;cg9~~Xqc=xyAq(Q;3bwrdjd{E`$oL7(G+ITi'
    'q_N87#-~Qn1ei>Flg4+xbt6yvxY${p&7-a(K2}cTX!W3w%!>wqO9NURH4$xZuwCqL6uIx%i;AJkOS**bs;dOp!3fi)c!jD77}5!m'
    'YiUIAs^m{LQY2BG+_$ksL>-qeE$oY}2qkEwhY%+4vz?&;2NBC*+#xEYh*K+c0f%ng(*+j!>oJwLG?<wR){IV)I8YJ{7qY0k^kq59'
    '#7G@#b9({8s@Uya-d`m+Vo70TIwIJP<^<06I5m%=+9JP)nFiHYWb>QTlHFd7BcXZd-+5vs#;@T%gZCfARZNReL7ajl!@>YuV<cz7'
    '3+LwgW548(=W+<n>}w$^qNu@$0V1i9F`0&LK#>B0P~$OaN<#pAOgG=KK#Mxo)cl0(I-~~3%E>BO`fnlu?l?64^#>^S0v=G7LpG*-'
    '&yFtE5S!Cyx$a%x4raiO`V=fnvM86dnf2-V!8BFR3w8{O#+y^4OG!o@M0A93SSB4vo6ENj`yR|{CgDcGz|leO-O@d1$tFjd8aLl#'
    '%S{^V?v9q5owfjGZ8+wWzmh8gQqz*Bn~k*=oiEHzkiFc#m*tK}+EM$pBTBU7_`DmcLL0z7Gzw|zsjSg@(!n7AVBW`Y=Z?NUR~UTA'
    'I|S5)!B1^!!Ko*5XqeiA$5vY7Rw9YD3peLMUneE5UxlWX(tAc;0iw-<tUHapVChNrklb0SuJM<qOq$&tJ4t_vFRzAmwe2X2&rBA='
    ';K9QiijYfG9Wr!>o0WeRp+dmy?w(C;m#33z9~0dThz4>+hFAl&MILxCuCR!+GKc{Kks(Vr-?yWEMLov2A7y1??lOra!k;x1(j6)S'
    '85O}dS413dhdi~DlQ4$;p+GsbO4d8MI*gFF@y<l{NPK2qT54NWhFKE8JN9uQ1BQ~`5Sks#VtmTL@UaZS!Z*<T!9K2wGDYE&M@j3`'
    'JzM#HPZ0qNc}}2W#+VX>1C$pT%g|t&gKs5)kW)fc&uz{p{wp?9?hXQgNiBq4ov(Tn0z<nJ)hh50AOrfogeOSycWg%T!h&{+P$v0{'
    '-1V^a>pPk4L7Zean40o#GA8v9R>M8JILWPZBNA5;i=rG>OO$3c=@bbm`=M)0xC5~hQ4+|Eiszo#`#pz9a6-`d7tEgU*T8Czv08A^'
    'XBvh)6W$t46>G_K2+;gdzB$eMEBD+ijm?6P9~W%&h(Pa<%fL=~QJVWi+k%pllMLu1clui{Ngj+e6JRN4j%`8wM(YjtL93yNUS4c4'
    'jlrL|A~n8`N*Jb0Tmd`1JYmK2W^l0l=VEW0Ow!4mB9b=&UD6ut<&Ea4sAdwoMh!76jO!^6@JY`S*q{3oZy-vwK?@vj8c8tkKvV1p'
    '>k>E<787(hELza$wlo_06>!A|`&vqb>Rlm&4|-Wx1LGcvl$g#gRvuWxwlcD#;XLyIM|<<GF3pqL{g4U+QF>$xbO!XD(|kjM2S*=a'
    'C6^S<3<iA}bMt<FWKq^`ilh%VfKl}XMVYRFJO(9A*GEq`4AdSwn-%HSyPMKKtKZYo`i295yc_yBi7CJ#m{+6Fh(w)8-H2M=+`6Z5'
    'aL3QsLhkk_SJr<6E5V(arJ=yG1N;;cx$Ivf>@eyD2)Gn{?FxR}zwG9MS=0{);*H@x%Jq#mWmFg-3vCgJ<Gq5HIf$mE*t$6e{0uu)'
    'Zc4U75%vUvI(Yw@l!hgK!z?9e-B^i|DI-aCG2XW+Rm0VGefX?&`D_|Uax7zT#`MAaX(*CM;o#B@b;GSY`i`VjZwO=8)(3>AebT+E'
    'F-{Ew(#QpoAi^Z%pOYou{ND6%+>vhgiug#q+manp3-|IfU_dMB7yVN5)E<L=YIW|F`PLm>%1`pC*GCNtC_wR`OmNwmeI@r2ENCDn'
    'L(K)}R^w}++CpN5P;$6?JLh)JzW#cn_a@g(4imUj)-}hhNogmkc7O`O>=IlQpYGh*(i^DVlV%O}Qh3puL+C(8Mr#Gi0@bJ$AWkMZ'
    'jqi@@S+%F*=hu@G#`^mN=#+qDWY-F{tHWi9W)C+n#358r6dPzhC|;}gb=k;rw2yBQGrTTF(kFNeq;T8o$qBbt0%oBOVvreY;~EOx'
    '1mP`xXTTSm<sCQA_v~oze<x|8N+oQ<E#Ad~5rzzv(7B>V!<--PoBYNI<=|ma8d$`~+%0Porg!%A(;pR6OD2l)rY4!#<79+E21pA|'
    'OL$#lRI|AK@)V)4*6%1``<))tiYJ%+*ZlH28bt*Jg|Y!ukdB9ZBr7C<j7@;wUe_Pi9q(GMe6*QMzx(oJE`N8a=L@+=i>H%ZPlO;~'
    'Q-DVVdAFFhaMQtE;Jv}_yn8F9_rsBuZwf6qnt;BOIkj}s?11kIFQZ9QVAF~ibaEbu@<K3P{<Fxv#{#oe<0J4|Byk?(j0X)5L@bLC'
    'fI%1>Alk~BrgYCPN>74_!W;s*&2cp0^d^l<Yc;3@gGkI?p(f&!)6}QY=cBpX>H|hk2m1EpzAdEdg2s#{w$}h|4CQ)Jda0NPa3{zK'
    'l+Xb0J+=D^GSqn=Ncr61Vs&>`k(BCV<X#Xk6-59vvK(Q+v>`yz+=o90-Me9mR9?3YthqM_rz~*usK1u_=rX-UQ4^IaW7dRF0^(Y3'
    'gx4}Ofc^|)s>yz)^}FD|KNhUm<SjC4E&!ZefD4!*UNFV1s|NlovR^t4ZWz`retrcy2379?Rs}dCCUlS%u{Ob*ly(#>aCnS3s7ss6'
    '5JI~`A9s;iNk4O`>B?FjNU;cwF~f%a>Y0{Fh@dSVNL;9M`BSEMLLlt@x=mbQ&$ok6aG;~mPC|ZV^vvjxELt7~H@-5WTLDVL9Wc|%'
    '^GM$br>8n;pwV=cNGlG?9iCa#u@I;`HF@!#;T?^r(HR()*6jd7iCZR4*7E}p8$$-<df<zcp(4F^?sh~f#7Pa9z}Wv?)48kLSR^TB'
    'DTp`HAK+qvP=~4z@dJSgCQC10p^gzBcwffcuY3)c5dFg=sIpMQ%c7Asbkby9g-1rTEy6M|4=9`BN5e((E8hq`El;S_7g|^z4LDSO'
    'tiM!Y0n!0<F!PHJZ4jjf0UV|mxOJ^t{&h>HcRCdgBU(0o9iH*JFM+}67a8=RI9EVn5vex_u<PRLwU2*nOWkQr$Q22cvOvmM>><S1'
    ')l?=bJ<LXczKyid)oaV0{!D9nmUW5d79?NeIb|_fYGJ+#T?Ziq;I?#UoH&mFLs)Jb%~0suJ9kn_9SDCEZ<I|iaOFXclddMhLK$Lg'
    ')Z)E`k}O-lej8f-!u6`8RxspeMj?f|Q4^klY;eBgzK~IZEWkS9%OFoHUXCO|58`ou`ze*cCod7b7KpjXhr{oW?_<)Y^uJ^@QIo`='
    '>Jmu#YT!Ac)E(^YyZU{<U33+T#$%J8++)F(S*>SU<YEs+DFx(~q>J955+?VO9SlRT+S_+@)`i0Mpv-+NP07JhFKe(eE`Nk9kR?3D'
    'vJ@~PebZIbOa{ij&$n*}*5V!o@#XC?dm$g7HWZ*7I(l-+>pJO7@DZcC$7RPHwn^hMq+;#yCMi`ZNdWsYs>#v5`m-=53h#<e0klIN'
    'G~%(s8-dKhnSq`In$&2<YFmOu)1TCdOE134f>6qA;fzbi8OuXFrU|gk=$34oWeKpLA6@mTd=`alg0C?8U^D?KO2OF40^f)i#a+r*'
    'O393Gf2mZzw3z<Is0+8wFC{~pENZM$37ii>37}%O_)0{EXd*0toxu!iXiuhc{WIEJFbLFiRT^7>a5KP&-0i7n@P>-&RPfl5SfwUc'
    'u6R)hys2qxdTmTYAS2+CLT7?mAX>9-Q1*!KOkJDMF8!urF8#KH{Q=nqs9$mF*r>q*!F8IKtl68WC*i*Li%<a<A;wWL0=Jm4eP8yE'
    'bGo=EO)A-y<3UG9lhG4Q3ZV0f6P*{^Ud#bHi;0Adk+(2kE0@NRfiLN=M=z%4{`yPD`Ct+eO5?tRq!67<@KB0?b;2|Ooua6Y>o%|m'
    'c?!d>pgO^gz^BD&Ac%leE7!Rwk3s`GfT8GZQ~Su5iOU5dDmq5WF%7l?Qz1y<yQ!gL;45sQM-;-;*P^IlyBA`rK>g=S*qmN>C2uvU'
    'Zn(2RYax~+<4PLRiAI|3U|X&cQ>cSNQTD2J7i3LOw>(ac48LC_5>iHFjiewSwNaB{&_mNahtcWE4l&EB-*y4fK_qll+S7<n2LUj^'
    'j-n!)G*O%NXkF=JrYst<-EK*aD;B@_sh;f#Hf8g1ZXj+1`aDh(s~OHJ^*aDCWCn68Xn?e0B-E%`8c;WXTldRZr5AeIF!6}X19&Qv'
    '<l%eH+%D9g%j+L((O%^DwEKd+`6pO4;4oYp1)n@-W-!7+bD*FfB@Lnt%JA_afZ!6Dp~;6_lr+69dY%)mk&#}Uw7h*Rl>NP?>Hr5q'
    'EeG>K<UtNV`k_=?p%Xa+mK&jR^*8(Sw;9u<LXWBN)WK;NS4Y&Y%Oge?3>t=Sb}x5FP&(o#YQed33k#8Rd)3$$${W7+5bPlxI}y5w'
    'WT-Q!D&XHGPF|zpq$odpTk+EBta{lvGt%fmq^8l(V0=99Bv=D#47Nj9?qO~EuKV-HE3bUx2JHhGCjb}1g1n4Hh1JVV;d*5%LxvZK'
    'bIY`53l+~CWd*JV9OSg*n6h)|;fhXTuVPVUnc*Ge_g7f<nQ>yS+B}U)kyp#LXz?fDKj388qNgGwqSGa-PI{=BrfF%>eSDRz$m`3y'
    '%HJP<=1j~W#Us<gI*#5MGk~+WSV{&VOvAC%tm$IKd|vUmSVSMI>Qam~X-2ie%aE@#7Qw*d8F|leX&@IdQd&LP(bq2gA|)>)8VX8h'
    'ng(JD@Y6iLjih{#B*_Fg$eO5uxCo(-Gewrg_hpw(cv0|;e+{TTJp;%~L`xKELhDFIs9;7XXaf0nDssZVuey+3s{CTGhl8U(CTW;Z'
    '#N<&<%&=D>NMi3m8vz?uyu<p+l~q=3%iQWg{s{ch45tvvN=v4vbO@7Q`C{@3<N9mNT)XJPqj?kCpl*{KsQApuzNpp6?63fXb4l+C'
    '_8f|B)SML6Bd!h9kfunad)vf?K11zTQrKDnf83H_uLxKWYtlKVeLtv|&!A)de2U3_-MR}NOR@Y?Q1?!>WZ-zwN}LqCWevmu!z^}`'
    '7)mZNBxtd6?Kf2+DcSX9xd<6Kq{*ci5y}~d&Xlw&NE{i*hc3e)42x6cvia#-!7+=uhhW-Z>;z=cJ#w4@OJ&;sB)uLLD&kzQg39H#'
    'aj{@>U#<qq44_UMUqiDS;Suy$CY7iYz%EbQ$!?Yuu=Y5e8!o%_O1XGFqX$n14FkqRYe&V5-=F-FQExLQ8}1Axg)E0$?ZUsmK3_jW'
    'y=)CN`x=$Hkrn~JNd&!v@>&@%;zg$UEkosc=OJX9<1+}v)dx%$$4UAry<>-=)4)97S>h&AVgnSXxIqe#YuA0F-<Dskfn+Bj03%C+'
    'C5H%Q3|I>l3=vYab*$Q%aS>LpTp6kOWa*s1I!OFzONt?*(vJ2wBaL9%BIiccn2Ubc-`C&ozZCkIOS6^>9xM7;`WugE8ea`;YGH<n'
    '^UG)tTN@=bZ@r+1;-is6GJ<R_KE!JH>~RAChZ8ACVX4mHUEA9AUY}0eWlrh!vXIeB@}LzhPXb<GwOK8E&EEu!$GDkxO<R4Q-UfeW'
    '$MSW`PXKK~Q<5*VAZ3k$f=R$E6<qf4<^qGDY6kYH+`$hH$yLiU&WQ8|FCGZLxT(sIRtO$o9=Bf-3PVqfNeq?CUwn~qR)0EuE}#Jt'
    'd*Dfnqar#Px{_EWQJ)f@>BEUl0+Ai5O69`G0K8NHmB8$|Ya=AgATLxrFRfq)$^#f!RHzD@W4C5Oo^kQRg?FG17wkn0_4#&awK2TO'
    '$=jc>g`^Igjq7l(URO*iu)GR@8rV>3UCLpg=urrSoQ8>DI8-2mLXFMReyEMo-`$ITFrvEt(@{f&Vbm-SK4nfaLVeJ2pi|B`M;#iI'
    'oM3D3;4@|mNd66;<Cj7PPcX!<Ox!G>2hFP@r(|AvCdjZI@h0(qsLiD>{g@@cN(I@gm7yTH$G|)}!Uzs~PIj&fK@$-nQIvu))s`&h'
    'CinH<$}`0tG~+tNL?miX;na-bBn9B%D&GJA>W8>$#SNU9tM?%YEWV03m}@#OBP+NpSRSTqtI8je+CbwDdD*&E&l%75xUbOjVxWln'
    'o1fT9IyH*XqrSjQ1;u5e%!I4ib=AKc>$3Cu*E1j7?<fIrDMR|n2eo`vi+}@tAB|g%IMXvjZ5VldS)jz%7ZF+t9RY~hJXY+9<-|vl'
    ')AMChE71Q?j|3z&E4I|$6lV|3x{`sfl(}9VG_obTjF6!*+K8gF$gQYj@Lh{dS#7y;HjI>!=)qOEYcm~5EMm^FW(h1raqi|pvq>bv'
    'Fbgd+mNElWfxABs=QsRm!(XvB-xNqQv$%V-o6#!{BWMF=uGn~u8p)z^i5dp=pjor<+oY<?$dT(ut(R3dBuj28_~-mwkN|ldSPinU'
    '8V^n!Z`)PtU!3~utm|cx#gmu#4kj5L&XE~CqP`kU7bPzX=(A1Ht?#EDTo8#Td6^%uegQ2gcy!`>Ga)XcA%gWCJZXqjIub^sdteHK'
    'xcQ;TP55aKRSWZ&Y43Z1ZD?!gIYHIp!&Zxx9ubZ~vN`U8UA?gW?E*CfV-4_3G8R~jl*pKn0_oD8LK=YukO+p%#VOq(=lL;JM@`l_'
    'O#96MrF=@9ID|yVP^ov)EYIx$_Oqz#g%w}6F9=aei5R7mFc+_>kyZl=mhzwB7~~}$s-oJ+Wt*e-##a7#L5VklDuJe{bzLWRMwH1T'
    '9doK-GHd`$py^^0;B29=9NDEme{TB}<TWrLNNonlhe58k6sg!c@ux&=Wg?nnjD1LH=_8%uXZL+B;=>y$;k)}@_3T0<)=o|Zny_Ux'
    'T~;h|cF15xO#<j6suEu&rPgeyX0{<hVvJJJu~Aeb>KQdVf%1#&6j&FV5KReyw$k3Uow_NKo|#RIMn)3`l|wytfG;F;M(U7`O)1oO'
    'MY;3!oh(xrU);7Z7SP}m4Gg!`gRMSDQgo=)iP4#isSzU#3Rcm+<+2rEZk3=l_O;CaWBdSS%vi-TYmu0auBcI=?<H}9Jxn<0UFB&#'
    'sQ^Xu&TI%hg<^$3_tnd;*GYR%XLyqK9;F-uQaGBVah9`Dz4oGnJ>RhDa9Acn(6cK!iQ+~LZ^y%H!R1683yGKUIHMTlfrI~&`yfhP'
    'v5A#Tq8Y3g7XXcYT;|l{Uhgyq5~{9{U}$G}XO_nv{J4YPUzOn0{QNdCyVOcZDg!DA2+-^}_X6OfWQl5AW9q+V@fD|!UhFJ#&qBpi'
    'CDBNY%qJ+zJ0MG%cEVAo6|1j1f~Y|WLgepgdhl-Sut@|A;-OGiXzFwT+hbx+>9U0mo;N?tZLgmX1UVkmw38kib{B74gK}v7G)To~'
    '=_%;fgT{rm8@Ob8HPfNwzya4pSuLuWZu#`RaCx$Os1Yb?lFS?Jja#T63&jU8$}NUkmOcdcG}JOcR+1pEVFq@Y24dE3qkbf6miV1`'
    '!~ctDP~Jb2=F|gp5{Xpqb<{zwI2`JO9lVicu2&t5zJi?q@r~RM1rus2!Bw!#5G&v+)2R{bilE8gwouoEgs6|>Nb3`1N~Vx<0fN7R'
    '1hX(eFdahigiTS={jaP4%rsnlND3J+;DwBG82AYu3txjy6)Cv-IFi!<qj4wNaMv~}2#-*b4BrLA$be<p5{9K{yLbVEh*JX^MWLpX'
    'xoaQQ6H=LSLJ>3zLc)mvqor0p<+CzbdTF?IQJ&_asq5c2qd}>gy2)F*9I#7cbTJaD351%cO{~Q6k`Ah+NRc%bclPQ%z^~b*$Fc?z'
    '*p%llQCTbh7X*(CHNzPgPAWbPNXEMfe5S}ncy|LwS<02}3!33dkr*pOKVp_Gu~;TaUadGtGGGPsJ!XEa4H0icE~|$5vCOn+6&iWw'
    'riBHvj7|dhLRP{oHZ<3(PvzSds)xoxD9do(tt2g!Z)3k)<A4ToX4W)Y+OHaWbK^d~&u6VN8i$h0M55eknsqBv9IteeoB}Qm&0eTy'
    'n#I|=wVOG&)=4h{)S!)qMiuT-$bA@`<4;G+41aoz52I>8vTRLNb`B;hiPf$9(2RxMl3{UC6{mpG@*Xu}Fq%ewV;10SSPVv$;^uK_'
    'f`?+8_Jh5gGi-LWs}RCLjmlIt6c#d~=haYoL480N2>%c^1Sg5od^ERhrH06jkzmj)LTu-;q~n^S3JvlRhk?S_+^8YfpnGdW7eF}%'
    'Tcw5s{3$5hG$SB0lh9MoDOAz{;i9974daK}s}F0V#?RV;O%?v)(XT@k1Ga<gi*AG_1y<9j@Opi(FuV!ifKUC(t<?EeaXT=q1z9M>'
    'P+BDjxM$_Ia^FQn&$knYzFV7X=cn!CXU@Xw<wAXipjprrFp8E_*sHtA1OlKu1ZW0{<|tw`gB$28h_|~o%X$>%wv!{NlHW}}@VRb_'
    'q6&f}4PW}bpxYzfUSKgqv6eKDDAuYTiTri#R*2&83*7GYg=4bRg8O|gj8g;7r>R4l1qTQYC!A?M3{0XRT{Lh!XjgV2u6-zsiru|;'
    'mHgCBf^pZ&0TpnNM^E8FYYA^RtjB?y>DG!S-iEam$PYb+<%O*AWNtLnO-g!A7Qqjdh8lt!ShPJ#dRkk=bu1VB+D{f9_c{VM<Vq5r'
    '#!&cZc1H(qPE*Xd^N|nsno}RdO6hOkN0Gb5m<;}hY3q0?0S33?o@UvpFi4DAMASssTdVI8ZDEygp_AP*060F&M)L%)hUMvqnTdeb'
    'C)y$qyQq$C*vASX1B-yjVEQFo%t9%Lcg(1uhR8W7me|FFrwKRgqEb>o3y8KZc`#x>0A^<1^8Zk#&MH~a{xc-Vxp8%sc2?SLF3P)7'
    'i3SyEMng}H3Tj6<jm*3f1sS$CodT4Jrcdw)*Y05*7n(vCZ&RX$#_RFRY16@accSVJnhXRJo5QjCK@c4lQ=dzxvOMe%V>$@XeUwi!'
    'nJ{7tf!P$(%t%mn<7Cmc`U6=r@I9y_1mRGYMg#|_V8F=;1|d*WC~NSq?cM71_p$@NQH9W|+0*oE(TKqgr&9>cgJ_P476Ua9tjTRG'
    'QnjH(Xm8ud%YF&z+-%$MrC|O5fC0Nzr&Q`S-T(zENH^pviYASI&*Gv?w{2vh3)H-rhNKevg+wNfk&#BQd87f8PNt|a3DjM~57$PE'
    'oz@q&DB=Vxer$=41@wRhU!&oDkO#TD*Z}=(Y(SVAVI-dw+s?24R4(n!b$w+-Q1CP;Rs-m&I;mp3Lw;sogC>MRJR~DB!)<$6+hNA9'
    '5Xjkx^Vi@8fbxwt2x_q;X9~XQLH641=x^K2nbK0V5vW;kgSgb7WP@qg1q5Ekn~k!wrZ;6oOJDtp7VYOHKd;n)f-X=fYDlQ297Fi@'
    'LoZ4q1a8O8ixn162Unk!TY1@r{r8=e!>TMBNyAu2JXbVj$eejVM)ccGiUBND8L#GU*~R(2Jf=NPHYJWG^Ms+F;4{Mf3+#&^R7ubU'
    '??p6k@(&5x%CjEc-Nq%HV4|Uk3fo-?b78y<cPkAkQlTKx0{0CEmkB(mfnaH%si2K#Zh9nd-|`BM3cU)fGmtanM)SgmrxZ`t$ZE*s'
    'MB5wA1|n&D%XWU?vQ|T+P|qkPDXPhVXqwT+3*3jyc;NCy0?Gb@+<$J`&YQ6~CH7;LdWixzLo#Gbn89aMQYbv2f|9EPyC7nMur5#b'
    'TQ+kc+SWc7qroJu!N(3k0_{w$V<4a?T_Qy=heqzYO<sE`|8@U}xnGCV;pj&_%U<N-2NZ)AM1vZUK+CxTiW@*K1gEumBX7s21<O{Q'
    '$8_dmF`=smKnOAlmN>Za1kAzEAHj%*dyItx>?@|*Om_W7B9@-t9|o`Lak~iqizFPrm|jBzCTYQ;G4j@6iy$Kfl%O{lBm^6WwHxBU'
    '96!x9T`+(L5=n^g>O;bv(Z-m`%Hx2z8#L4sUmD`g+KtrncQu*X(f1Vto-l`TE;KYWcZ*{YESjDK8&Sa8C<jh=F?$aTRd<;47j~gA'
    '0@G1|I(iHA4}dgsyRdLeQAH~FBjH}Tiz^J<pUO;bnpwAOFF>DW$EX@(rZwNmaT;x&OjYvQ4@LDYpN9rQmIfps-HtuIcN9JH0M)<>'
    'Z09w74d+Wz5=MDLkek*bAQ!Uh=AuBA2~VN4fjiAvoMcl4LTSYVgtKBa9~%q+FJrZe*T&I{nEq`yMS>1J1Ot7nx1#-tkHMXSZvh#K'
    'L*z`O5MUcTy<5KxjBF*dCO<saS=YlB`ZCCK8tDiFRTk+mXz<Z%_07Uw0-xif9oBxFXFBjpDuf2lG<3Rs@}_DSb4A>Ql8XxyiIL2|'
    'VF9Zz8|_W2*O8GY0j3OUZOJ=iXoz#gNGzad4mwE}l>JSl@N3`0;vRN(3aNpzMb60_L=1Sae_?bS8T+hFQR}rDz6lFlw2jg()<q;Q'
    'Ctd~`B;K&ocw@x5h#4)M8L9(FY?QX}RZ6RVx3KtrNnOVL6ebTjk>1hP<KE=xD$&cLC2ioRNSTEOKIrcD)vH&SwefMo2!hBtGVd5@'
    'PcI%N3r`<z_JEs3Pl=z3?3}+mJL;n!<1GiM4h@d>BuOKm7ny%gqZ?u=wlJ+|(IYLC($eQJ^U=NglZ69=_JD07{2RuvwA`@hu!07)'
    '(^N)Iia?z1^Dxz|SRL4KBgBxJrWkz~EQh#k7KUmg6Av!?ASW@xZt;gM-*8<H*uko1Qp#j4qiAPXvdD6lVHliW$Y;!Glb70DwW4BH'
    '9ibncIlMA%5f7G5wn@@Auo6D4n$!fFp{4!O7d62@EL#&Pn8T7}yEtf`4)qCEz04}ru?7J`c@Con)T8M5_`|AjlGTU44m%-IVQws6'
    'rIE8Ev(q?E$d8B-jmER!aKs3mV$J%)s+Bhc(hy^@_HnYSqW*!M-vb9DaL4VONdur6Ogbsz!hc)1Vw4hGU0hx;bPbaRo(`~wpkz3Z'
    'f}TQo;tf!M0U&&|^tl#)_%UIBIF-h}lNXZ(X;LPB5g<pcMq`6x1ziISY9mhfbd^865veKj{_w1xA?ghG^zA<iG9X|A#<^3-HAH^8'
    'm6|Wlz-g!sMnPjSU>iPml>KqN3u{scNXbhd^G=C9u+yIav$4J-Dv<k<hL9v<@vC|}V~)0B*$duZURxbW#v>+uI>`BGzsNnmXGAha'
    'VL5>{vkMN^+O^-n?TRgcbHEdahDQ}d-%C!V478MK0lMfUeMHj0=nqddRnJL#c%VGYOo#o)@5lY_$}a~0gpUi;NHapv)oEBg<||3G'
    'Gk`DTd>NkThdB<b{0=GOVQF)Mvb}$df4qB|EKw8eD&|T7DcR*tU;qYl<Dgg}I_m_He$2_&IL^zE>*IrFVE*Iu=jqz0pLPZ@qs1F}'
    'f`}0)xk;x7c?x3Fg}jHz(SEEbBLqIY{mAzP89)9wx(@80J_M~>CP-2}QB{M<P+!9|$EztwRP^zzDy=3ywf^p5!P*O5DJ0vFJaB!c'
    'UZ7LSC_-p^R1UNWd${gk44AclST`NXs~+HUsJCz_T=|pD<xe)>y#ubNFTLgnLutW<5=#$U`QbP)3X$AJTn8W+_&EHtk2dlB_a4-j'
    'J(L3>$QBjB1aNMovmsf5QjC7yGFyV0-N_S*Id|`!AhldSdH02L`u#r^g076+nc+$WKsDshLZX}>VKiYz!Ds~9UcA`ZR;+cNae4aR'
    '`~Q`mmU!?#-RW}ygXOHi&nMxg5E2&a^;Jf<%%u}R&f6Z}FG$a;(<BL>A1>?+G=ck<vI-I>KzJeuTNM;q2nj($sIYA&-ZK;fJs<+q'
    'cgdgct$F!tq5Nl_9kz$Wxh&R$QxlKM8@@WU*Emq_k*+qju;e+*|FkgZ3T6!4VDhxILct`{(r1(9lMM2~-404g!Z_Bg7fFJzAJ}gB'
    'I;a$}OoN_A`yOjPq}0eQwUbU0jN|YwCGDN{9$y(}SYRl2vr|_TypijYhlk4~tTVcQNG$N0AU43Ao$J=ar|eXk{W)l25x#r;ASR5%'
    'Sw=mqX&HK*-pfH&b6LZOpJdoRoc#ulpFVFh9^>G4=kaMT`$9CpkPT%h_J+8(A{M4AEn7B15|})gB1~n15@<!m(psy`iD1G!quKD!'
    'mQ5#)85kV`%Ak;?dDS^7nD8v^-_=k3ZNb9=B$xcDvGc(XWq{X-eF&b$h+?7PqDjT0mBI~HY=g9=Nfj%;z7(1Hl!hGybU@EpR2SNE'
    '#C5CIKAWJ+fIAqK)Z{)|EhhO~LvQ{@g3H%`lxbG+o3t|FLIy$V!)Q`~l>vbY_X<?+UW#voxV%}jYE`BeYzsA$*GErB0_7%4a%)h6'
    'cXG4Ph$MI&40P*FlU6NTyugCg^z^MDRVQ&*@G)@Gz@X@t7)H!E4bL!Z7CqPE*KZTlMhbW`)n!HlA1oXeDn^hr^uMGk@K)(_HXkhu'
    'Z|Gt9JRbh}3e1tW=Q+tW0hj(E8~_Rl@m9FXS_h;Diwe6E8RWM~Q|msyQ$AX`h9-h=0dpB50&y1SJGdeEuaE}Hu0)C#+>bGlYFGd2'
    '&!xaLXmTRoD6C`X;v{MW2k0PFtP+1xKho&{U$ko%t{ET8H8wGu8lM{~QaF6@=8$zu@WY+gK@sBn9>T}J`FMOy4-jC;UKSU{my;{W'
    '6?zEIoFIxuGA2k`t%Up>Z5}v@S&tc6BMaiWYR&Q;N4o$zwRI!@2>dFi0XRZAs9CvMfpl6fAadcV<!Y`t>;Yf|Ak(EmrW}EGk&_Pw'
    'B_hsAd1)EJ5SS_#Je4v}sC~RftoBjk$XuV1q&!QE&-4}ZH0dJ>j2%8&?}9O$bL{dbibW1&C3?3|_1i2ra6CqINTYHVy14K|s5ETV'
    'axYxp6oZ8s2XGxCAS8s-8MBEfqlt#UXM7WW+zP)&{<TxpitmZ^e~R;rTOsn0{AfxaAU;HVBN)(%ONmD`>_#wUU$xkIB2R$?g;Z+R'
    '%w)WmNo;`{Js5tc*oS<C<4MmE1oWfzE^+<suQlWKM4CopAuM$kXO>Hx4h0SfpsX5|#-n8~A0JT6hxf;=;_1V3T#j!Z9tFo1GpV)B'
    'o1-nkG2tQd!}(wM5z#jCZ{g^Ut5+>grC`EKtHGI=i4l9y_j73?uV(r(lzLc95Zh<M{tZjh)Q|g|3o(`?iDygig?|8!jcEpQq(M17'
    'ZnDH#Xc?^w^{XQj{NpIf;md1*14=L_(n9RR;@M(56{!k&y|6$?&}axD0%3A^{mSL=z=tCrUMfLyBZgkg8gzlB0rDCNMW-m9UvK9X'
    'YqHKip9-RVk&qVRk+f%?@)M7K@ogKF%1pFnd=dXMu3hvZ8!s4ZXOT7Z$ru@X0LO8j5$VQ;4h;~F(`Z6un)Qn-W2l_wCBHhk0VIq|'
    'm`O2e;5vLowdgSuWfCD)(ERfi-!j-EouQLE3%mX-K+Pm*vZY0Q0PachglPh<0K94%M9Rt|MZ%O;{Px|;vsOMb!n80_4&NO{J2F8{'
    'L_B6@iG}9nR>-{o4URSg-~-Ti{o0q?=q#<fzPKzY&|S-%SHv8yCocV-K__U{p|A!gYs$%|`o;C<o9_wxw#1$7g$0mGL4)D*774S*'
    'o&kf%Rs|n6XvphKzhZsaMCK;~%Uf`JSXi2$E+OviPd}Z-xt}iS!uBFo-PX0)n6pQBJ^`CRbK(~;MmcHJR0q)(i#9$KYO36i|NYzk'
    'tKnR^^#QaQjVov#91HkIUQi+!4IK}HI@bv$6PH+5vGubV<p;s^CpY(j76)$MAl`btSRpZZ1Z@YBbLo3EcMAKdspg1FWrR+1={S_5'
    'c$;K+&G$ov31-2FOo}j$JCG0#Md+`{i}=iHqIfmfM!$l)s9~BdiI+U5DJL`)jZ93oeK<fTIn90u4QUi+Vh+OffQdaWYCkK<HWN1h'
    '3?vwWpgO`)fzTF2<)wA>VI6;V6MFC>hPXq`@4_;aP9y9!Hvz;_<Zwl*H#Ta}GRTw2_;gS{jFHE~qu-Q%)}UGCVtp_n26K9%00}yX'
    'C}s_`=QyDZia`SO;fE!`)x#NFPk7XRirc)*Fg$Gw9ZnKgx=fgnq4AN?BgKyVxo|ZVguskd5<Fn&wszrSGKbA0W8h$Y%S(}HFNHUh'
    'G}Fo{gi9BKBoI)XYZv^fX1;#e1x<gR_-Qkq;c!2Yb0keb3X<iGnnlD>4MXk9MfeA>6vGR74|OtlfP`t)Pz8gscxy9|8b2ENsvlP8'
    '%UW-iGoRejJSmuk!rP*@VosX4^sOWrz_dx|Fi{7&I*JYamp(qMKQBpaed{h>{hfS|z`}$XoD}&=V3%qX5H}b`&lDxpMQXy0b&Gyi'
    'AQ!Zh)K-J0p+U1CfCDH36lBeDLfD{QJuc7FyGDZVtXToI2><1~#}HgBbVwaE7P#^_Q-NwaOXXojB&}Oe2=ud}UBQ+C+f_N3X>K{='
    '6S2mC3Be<!q=vMnDa_F2K2FB}WzB_0T+?`?H^`W24i6@7Xc1<K>S;r9dH{O3v+$mU$Mh~u^~$=1DoY;+E^eIQgo2%d07nvrfm2vR'
    '5kz-~X<FllbxXog-WGl-2!v*jAp4-f7i3EamIY^fQoEY$5FnhSaOJXZSxupzO0o?!C=wPuI1Hn34I`z3XM+P}(2v$I1z)#z5g0-C'
    '&A1@!uR8TIq^1PJ%d)lYNr5$%3<{d5U#&<Ol4l8LXcn`T!OaL4NU^iD3&`{_1cG9Tu|*zMt@z#mou46hg0AM}Fx?MvS_h}E5qFaz'
    'pG+)<YKKk_p@gYh^ho;Y_t!^70@*RUZxX#s2Y6{Cz^xXw8A_P$8B!uQ=T$3i%BVB{?NrFnzNAU95~x}ZuhAGmKneg0v~LiJ)-PMd'
    'Ru$8sRlU^ESA|?J?jqB4q~oT|3E2+hlDILgTYk}86j*4~8$f)7L%bf<qZZzc;U_I~f|X3g)VUtkt$S896#N}ptR&zn!3DFJ^zvRU'
    'GlXajLfNK-GgPvIEh-mY(oi^@7d=wJ6$e%lr<t*Cv|rH(;B3Hlrg@PfNwGzwoVv<Sw;26300Y4<Pz+|@94;CwbWo7dI8BTo<sBC-'
    ';olDQfBldD19SQKjs'
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
