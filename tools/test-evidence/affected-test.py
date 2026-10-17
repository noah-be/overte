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
# eb24e953a9969d851289ff9c1fefddbb44cf880a / tree 47bd0aea8fca5d765a16875fcee4d92c939cda9a.
# It contains complete import membership/root module identities, every affected
# authority and every fixed CI subject read from trusted_tree by plan_affected.
# It is not a complete source tree or native execution/provenance evidence.
_MAIN_PROJECTION_SHA256 = '46831bf873413307d82b5be87206f596604d130ad65c7c0eee4a17d877357f23'
_MAIN_PROJECTION_B85 = (
    'c-qaK-F72MlAQ1L7=68*%E-US+^5jd(LGN5vd~2m9008D+CBU3`YZvmS<@sU5~!6VX}71VTN8oINDp^&GxPua?H~8s<JTAe#XZIS'
    'ZX54*e>|oA-Er@p4ms`r@%v%-^xMDx=Wma@n11{B-%QhtegE6P{dV~3_}kXTCYff;G0t5x%qAx1=CRGWv9S+6rQWua(f^0zk7xZC'
    '_=lbU?Z5u*ZCTGk;p^S=?qM5#6jt-Ti^hy;oNW_b3e#vUYc!2*ayR<eWIOh*nLc0b*@bWJKHdGX+keXsyFc#k6Tj9Sx4Wl9Veyok'
    'zO{{=hADMzYLn|m7xNrbPH{FP|J(IxN}n&jPtUu<_PE>sxC>uX_*PnR2t2$TOt5Cs15PQ;dFa_kocW>i<hr&`{=&mOro-{>@UlIo'
    'yO^HSQ%p}`n@a1p&1i<H&o-OJj3#&=yMAb699(N>JLJ(>-?h1B-O^evcfrp?JKE9kdWX^FXxhg2ZQD1|&nX1&k~g2P_4+Cgyxe_y'
    'I^O;B#XW5EHY{)TA3q)+K3{!|EkCVIy&pTC@7Rn@+YiPJHkxi4dLQ+(ldW2PzxzFf<DGu{;qtQ6+%|4D$<AR)?GU;?H2iK3&}f=y'
    'jT_s6W#^h@|9+@0E^V{ryXmqShRGx!<`BoZYa8QSFmVde+Bo<92k+MJS&qmM9=1H?FJb%T_w@8_`*iqn@ARIZe|)~GF)s8zgx2?c'
    'Z++WOaSW}oLy8=<!Q>$sYnyh>s?Yp#Uijs8ImBJ+U9wZ>n_$~GHF@GZyV2*?5~QXkam3cGyYrV<%`V%9mud|$VQ8D#HEm}*--kI('
    'eX!XDH%y&bv+Dlk>EfEf^y4_j>}KCjmY?V5Zfxes_%8X>_R%*s<-BT5o#ajUy5Bvf%^~cbFaK&jm!{##I@66K=Q^a>4V|;i&`x|?'
    'Lx^*n%(`d2?BK~grUQXHZT87MZ=dcjZX-^d-Y}+N?1`Gm^r<s*+xIT`QE{#BN7I|I{y{uFKW@VADQ_>YZ=FfwL?9a{<4ijRGxB*2'
    'esmMxblb2w%O1Pc>+4>Qn?Jv2e{p@!Icxep4g;Zj92%a);N~W@+>o5ej;GM1&b!s?a{{?4FRq<J?j}db9Qg1$>w^u(n~vBv^ue`e'
    'BG`^i#cx+c`NRGA@|2E>besL|<(M{c>+YX+hvPO}jyB!QoiU}}3}Hw;uYaCWa$KFwFcS4b^sO_4nOAS)B|cwVxShDgl4-dy_~7HL'
    'r_WBtU~(jN7_#RiCTpt~J{`RC>Pup#BX~@I9xn%=fsfrL*LFiUbzRb?hB;Y3M7~DuRMU86X~lg!IP${d?r|IL2z%eR2X0h8z%TA4'
    'ZjYPuji+1o;ukp#$@Q^yWP@EM8phbq+%c14q8SIh44#a=dN<2gsgL8qy^u>@j#75)0=ND+_q>lWI#1l3r*_Uc+OEmQq=saxxqdS*'
    'q?4B;Wem<tp&h5(4E%OCgw}F3@R^YA4O1Rm?8z|A)qD7s_D|_yv%IB?JDFS01BrIz-uIo&ebZ(i+i@^<9`l%HYdODdzIrE*?um3e'
    'ZpiUD%KIOiuiJxim5aM-ba9QjpL~-7VZ^3^%Zyu;T)~ica+UQwrR#UK^ZZNS3&Cs*9jRy-JkhfEt+kw9*EO*teM+1l;@GHvdi^e*'
    '&y|OJSib7L3&+cWZHoQW+P<AAu%?lyJ`9}=aUx&jSd%bQjI@)Vuig?lRespse?3;m+R=8IjH+?{;JI27-?^ELorphrK(TA6*|POF'
    'Y^juP@c@P<OpT=i?MAB2R#_KW7LR1+?KM+3O<fzW-U4YyB-m}g^I>n^9?|72fV1L!GiT~Io<TR+iMa1af^YW55N87Mr@8*I9FBZf'
    'mk-O#(Xd+D&)pOPmk`Bj8v_r@QchYsbn|e-S9Emy`&4}kWD?%Sg-G_1N6tv%!#2GgI3!k2Xe2+Fn{@qKI%TV`SApNXJVjRsG#nEu'
    'u!i)U*V0hzx-s&9hcWc6@nhdOL!Hp4U$m!+>#0lG%){)d$@(tMaR`miF&M*1o+8Is5hvv4#vLtp)TSy7hJpOOHC&inj1#Dbi^)%%'
    'Y^ogBb=@%dOqzA$drME>xBK1GBmd&*)m<*@TH!o%PF?4{AHv8L;oS(<G$uEB;DgMK9=qH2RDFw1uD7nEs<5L60Ge~`scuQYC@(#^'
    '@5l$wj{0A>oz0dc@cwjr6f!~YCk|A!ZD<I@o|on4G0YQ}MaP}yQ*PPrZCktQmiHDwi-edno@blLLW1f<un`ca&i1+QT%5x%+FIB>'
    'E;vc)fsNUvZYGiMXG5UW`<zIc3E%8?jK*i~*{O@aW><&wJv|kwYD(5Q40?eSkpzH-=QTBk>!a<`1RB~A$lY!Gsfq-ohyC0MVgT}-'
    '!wd>Icdi-v_yd5f8F`_GGWW)<yvvFnw>4*c&Q0e8FmwqJ59lt~!OzBnXeD;nwJsT;*?il+)~80iH%HD04l)320&``+#oml<&k-NH'
    'sbz<Kll`sxB0t)MeFED(Zr#J7fDTY{^?l1lJI$W7EoUB<asuN?b`4-GsZ*S9-cwCV&~f>5aQHu<Ma~$$d9rFCeUO`O8YxhXv$1V&'
    '+sqZ&8#$!UAm8K27e?9a22j%k@ZFo_fT?}UJ!sl++r|#Nmp!0X*nLgl*5PtC$9l1$C~`a*p=>F3^Juz$Rtb>99C>H~i0Q^HDXZL6'
    'l&~O7<ZFO^tsSV$vge*@L0w|k4hh_o@H90a_I=iGC%f&#O9AMe`Y9xr2G{h13p7kDxve8-2`!H)blo)5KruI->*M2d-ae$aYVGpp'
    'Z@Kix&QYBK2N5wxU>P2ZC*N%Z$<o<rhw;YKecZnsj@%^Q(vN)!8s(cOzvTPweKMTsnRgUsfYQbr4po|RAE$InMX+Ks%CeizSTNCc'
    'o-%JQx5V(i_YGfI@O?MTU=elK{~4q{|C7tNMeINWIToO!cHq9Cpl`@z2jd44SuomR3e!}VVc)+j;V$hTw}->hL%f)b`FW-vp+-lZ'
    '5=}Mwn55C3ZkMyP4ru~KVou#p{<_oK-|b2PUl%m>#N=k%hdzd(CA3kWPu$?KF%dY9&!le6Q`&MlbecJ|e0Ux0kEkpP;5!)rE?|?)'
    'okL%ZJ;b{F>50q#d)m18xV?On(AgmQApRNOjw9U<P>GlWJ+_Yj*8y<#6bzLG!FkmhFtKU4#3{>EAlZ<@NMYae#e;$fJ_?j;gn_!V'
    '^!`h#&M`t~QtK)5sSj1P(gBJ+tvzxLKK7=ig9->=Sueit_tbn!Hd0&kU5p(l|6qF+_-Q74?)a2B*3{C}X3?%#{8X5R-9Bx8=X!if'
    'mum=xR)QIQj(&_(f1?Fuo*Px}GtH=xI@N_-iP62^!Q<|GT8dGwpu$yXz$I<l=EhH*6O2n*L(-|c5nODhYPU2VW>>$5bx|b*o_N#o'
    'SvR!4IvQPrH@Tys%a@k8fD%-JF#G!TD?^Kknc8u3s<pvU?8Fx*#7(VpKE!?^ypwl#^$VZkOT{y%2I9Tb%x$^8TEka3kxP5}=rmqH'
    '0I1yJK>u^?(tnk(m+uf7*$rurBXt!PVp}r%i3bm$-|)H(I0*?^zJB?0w=X=uTz(FGcP30Nf67~j7DAoDO*VoObI;LFm@JK!`HGFy'
    't>5K=CZ{3mquELFMV6ZR9=eu4m>lTB*!tM4KLRA|3zvgW!R;?&LEdwdw(7ESs{}&cFtDcpt%5_C2#yn(MvVUIEz~^;%kyWwhNicJ'
    'Yyf$~!8YLGJL==a%}#PPkY`-6jUUIayQexpQ-_}-0Z?aJXjo8$(g5LuIw4K;n5d3<Ui}phW1sH9bSPBf=8wI5elBHM!8eq@nL|M+'
    '5C+EO=m&U1fr=c)80Q6i=Zb>?uynZzJC4+8Ba4yF#a^vNputSHt@R3#puD7gsj_%G6A)?>g4w#+bt0E!nh_~B+(<p>R!?#e2Tzw#'
    '6qvl?KDsI^puaHC^oC32_{knt9No^~1O+;F0(UNiv8$+tPQUza`}F*B{K8v*IJ2tm$nfv}NF?6CYE(oQcSEmERVr_NIe&r7o>CEL'
    'O@Ih+cjmFQLq(SK({5P(E=3Wa-fv8$$HpD?=*qy6qe>)AqXrS_%W*0KUoT~e?WsNJ6DOV83UKtZjg?3{nJ+;36OW}8*1#1S<CLjB'
    'EUnMMhfDyQDkw9{W&KKSyu2i-8fR14Da~FYf;!-yTFj=&16L0a@<!`&<&v+^m}2FI_u%%AyZz>cf3J|W3@sl5cO)Gb@USojm4863'
    '^JI<5(8LVIC}F&IAE(Om?#z|=a@dFe*W{7%#{RF-Nj~4oiBqBiYsoYVcqZxXG(peg6~R62Nx9qzo&iwK_sg?!BOJTwhV8rp2+OuE'
    'XT80*EmXn~h^d5BzF%sN9{xlo9cCXSpBci@m77^eoTt+bnbaMsk53%=UP%K}3l!BRZsP#UgttcR?c%^6ktL25^sC~&{LA(sp75Vq'
    'z?H~0K?G{u3<HQBRTBvU)><JTU}UsgI`K2j?VCGecJCfrfrr9pr{_gT2=FyQ>Kb)}X)?gb8Cx+POq%=KH@2k>w10i6XVUp)WPv_a'
    '3wv&&TW;XxM5As;N5i;<PY1sc!nv8|U$C<$?yLuz9&S&o@A4^2L}(8dP1l-K5A2-iNt+)?$wQ5y=A~^s4Su+NSEr<h81b${d-+oJ'
    '4w9DzT;$y~1ggjf8E1|fCl0nPr~s({<Zs{Fn%EV|GdTMkeE9Rk?{=c;55Y;Hlm@c89@J~@7krlIbbb4{RI)Gr`Kvn=*wK(CN5VYY'
    '3)Hbf6UdMpfH4FBN?a}+k+%IWIAf=)unNAm^f`$VU^}4&K(x~WnPw>C&DaK!)LI@~lWyPCVSB%@BeqCEsC+9v$^l@J%aEcEK)VOT'
    'owA=MJ_cG>fkc-F2ELm98}_zjIu&jADMd4@y$1Pp=Il`oQxPSw(18*WHd2b9&%fX!cohO%-cF`}3=0%UmedAlXaW`*rMVy@Hv**T'
    'mvSRqxt-TNd|7u@((h+cdVgK?f~zKOCOFCvC7^D3Pzz97W3PUTZ@XG9$^z>~&=urt?n6hM>iHB&yuq=+b$#1Or~t9~=I3(`@s}Z;'
    'u5BrnxN^9Vp+bPL!e=4I10fLAp_R{|o&9j@UMfDb7DkOoeNZwiC?mXGI_;i(7<B{aW<ZzY=x5uTw{or@e*V}B5uj1Ilr5bT=YiO}'
    '4#63u|IEMD@xs(m0RX>sYb&+{C<x#~RD`dEo`;qwWfu9LX&sy?v^G}ocypnejN82gMCYBMFneu9EP$*F$1)b2>E`4n&<&-uox-eq'
    'YHmOv#tuvzoSd@8*>24qN<}PH8bwGu4VLnNf&fKcCoVH>rHB-Rg3_8{tpDAWjVAiN4Qhry(~E~L)FC>Vso^18kg`FbHgqA({L$g$'
    '`g2dYgj%GQ20tV&r=pnNKWHL94AD}6^x`@F5<P~G7@TnzsKv=L-NTm+RQ-1nt&RR!p<l<c9N-S7ukN$t!LJ4sC7iB)?7W!boptH*'
    'vZ5Sb#$@K0p`Ftgm=cK)s!ABNRNP+L70ygYz@wMdU0&vt@GSqi(CeK$KL}>=d9aAvAXSn?Q?zw-sTBPaqM7)?j}rWqo`i~jar@&I'
    '<rInX!gM(nIOJsK5#}9eFjon3oW=xtMT62}(JI?ayNGt##U+=MLSoL}7wK$9wEzu$2)_Z2R0E$iHb8D8;!rxu!#pYme00bDZNU>U'
    '<nlRjLiUEPfu#oEYiTo%5TH2m-Apwwoa*9G_<aYzd)$2I){f<r1{iaurXKjT0Y||2p?-nYWCzh2mLZv8^l|>Ed40-OV*0+-Tco~w'
    'K5F%vM6Z!J0UC(_OFsCd#U@l;l=)ne9{zh1X?nWSqR~AcrJY$K%->ez>AlmVQakY);YLlMxZcraqJIsRKp3@F5=p3AHr1_ocvDqB'
    'Qxv@Y@#VnQs-qg3iK9zT1JMrT6(DrO4lE4dhQ><ggS&DE&(GVJ$4$*fg4o)0lagK9xE+G$7IEsJ<V>+1S}+s_H>})9)kA<UGtyr3'
    '#M@p(Q41K*LXIH+aP8>B<WM^xHC(%P*gbH+>`p2Cnf6#d`$&X^GNERhJ)br=OiS|ucwJ0B1S#~GC$jvwb~g)Pytz*_+)FJ-h+a^P'
    '`4;Hr6V`g=V=x-}DUEsVEl4sL993EM7M62R^)8?kAWiNv0Zml1p@(dhrIc3tAIymN0H)Pezl;Ar-T|G9$HJ13Y$wtR7>Nz?T7G9#'
    '0JMZ!+UZoq7Ip!x*RFQSm=53QUTt>a<zf40)w2gy)zb8>fKEnI9%ww2;&e{t9(p-kCJ0PqCs%Ia{`qC|6@KJHIuu|{dWw<aaWJU1'
    'VP#v>cO)i2I-PoJEgU=EMrwY+J|IPNy+d^`@Qi5D5EUSf!66-UR@*PCWD*ylM^28qrt8eF+0X(oRWzdoh7ZzhbRoAP()mR#F`z<5'
    's*v;wlXzF%c;&9Rxc4w44%=`1?d#uNOuVRqpr*_{IS?ib8IZ}+kwuXiC%RoxvS?Ze?UnmEArS7z0|8AnQrdoY#r}(t2E<>oqb85T'
    'pziztg(P9)(JOzqwCqinhHF2o)%!86CvXI`BkeR(OTeN*CBZX`)Zm2FK=R#v=qmE@ejaz>Th+(yCiQSAs%>XRxH|B6xY8u#mnJHU'
    'wLs>dL+!%nYSC|>Vu^i8r7C3@!7Lbb>6}qWpb(bgDD2D-ToIv$vHE*{-iBTOC2#*c3iV&W&&zR5njI24@(6m5DvL!IAe|KI0dh<Y'
    'Le^oYb?g5{nX0~4DAS$jrZkUWjj2yfz1(+DiQp2^8?|Eh0hF!V$X-?}`}$2FW1<wIttfT?5S{aYt1`Pm5`##_ObAc`UTQbNf2)WZ'
    'EAIGSDOHpT84zstP>8rxNk2KC$SQJzOAs6->6JS;<vZ2SLy8WnT)|w3fGOhXgF_r4C&uRoF&u6*w5$8-yZ-x*zuhdBMygf|(TTLG'
    'p?lX60lX+|jZ%IVB`iTFMS&w$VR>y|x!}yl&!K~^HKOf<KmxV~96I#KvV2Hjp<Ea!Zb}OxnECM^sY-f9&mELOA3WC;FFMcCIJIC7'
    'BR4#mo&mk4|4>?Tk)plU<prJaECt0(kJu#o{e6>QOyLP2GpC6LE`JFylu7}oPA5(03Eas5xWlbz)v>1fMg&CG62RYwlXg4wwTmsk'
    'ba!qC>pyNz{|1@CLq*$FpeaW;Qn6!$VIjUi>gXufdH8UXIBYG1kJwzZo$Zqvzi=-6OUABi^ZeppxiFXaM9Amz1;hoN0KN-=J(14c'
    'G+9(P=qs&kpJIE{o}_L=FO?p+mP*VuOiQFi7=agn?trBNbZ&ftP~QX7bc5Jy?juX275jPDz9Bux>9~Eod`)o&!eB=~LfMNtShp1t'
    'K)wz-zI;H^n34ZRcg?OIcsg`@Qz<m_78*6_1D;&eJdp=wU<px#(2A4b4!{CD#9Xt7$E6)eOQN)g790!o1%wBHiS!XXj|-bKGtAl#'
    'u^8H~kJs!$_CD-kA1j_k;%4fkc*6CJlLFihI|j}PmIz20;)t99KqA;{_Cae@)%f!ZJ@~4_LCrl=38OUN(}rRQvyqe^XAgEnyJ*U~'
    'wZ{3X!?A!ho725@`m!&-pN6}6q#h)Dg}vnkk^$wyS%MM(12E{+r0c#Ou=(8{0N}ive?C4GNOdGL$V(s~a-U!bM7`7F|3#GsX^D`}'
    'ZA#G|f5BGtXO}SpELKKKzd9|PGW>{mEW{Xyu`tJNnuT*ualC#nVr3p2hoykt2*m{bHqxXZ3IW^VO#$DM&ydkf_?kd3N$Hx69NgnG'
    'nzV!X!Kc=KiMY?-fG1L6;c+mB<Xf`+OvOVB%@2?QVN`Qy(p9nlC}n!Ar~rD^9Kc4Fo;aR!@Wl;%2n_Hjw_pTXtZ;fTK!439PRAoW'
    'P>5aL1N<?`L?YM`#{>bK1pF4{7s!WZIp8|HJ6r$Rgs<-SDx-17;<qB6Fi5sI%5;}WwZT;Yy17{(qw@VCU8ZRF_2KNz<ne4B1%&&x'
    'fDk}P0N_gWdn|k_wGC)j!d^hqf=v^TLy*c;AH+^1*wgK@^HNLFOchbhJr|NBsGrcbNk3`14`HHHgXaaQks7GPRBG}L1$^~J6vM-h'
    '@Q}`VTL^q1%HNJ(7dL>1RIbaULxz$tHiRxNJNk)$ppXT0`#|EL7YH(7+%MWwg|Qc;5q$Iz;mg^OFpKm*WVv(lr!y5afDa7A>6dIM'
    'ZgJf^78vg>681nZjYhAR&DSWRRlxo=!5-ph!Me&S<9^AG_UWH5rI-(ySx1Kmho2WFk4h?W1mc70)xMpO+#-zW?X4Sn*xhfRs<4)k'
    'HW^o7(glsxB_|uSx+nV=TNZmtZpdDoms@uP`f-p(<0+)7!vwk^1b68p(k<nU;bKdnLJ!eLk_ZWyxs`5yQZyXjRMVwB@qTza)FiZ='
    'EP;?N6CEEBFB@fe@Ov{UMT)oX>5z`xRQF)JPwx5fbywIGqTL>@AjmHL&QXpkdW(@<vlqi6iXaX}`<LzN<@sUfE<?>(C_Du`R-&+Z'
    '@d2R}ftZsaKGTU7QV*f2AKP2^bliPQPiNZf<zx#CSFG4Tz2XM4afF9NBj`BDpXLt1d#mmFt2Y$mUTFM2CH)&uMUEiX7G)#q7bq{F'
    'dGJmr+1X(h0;h56vDk$|es!qiAE;5W`FcD)R|O_QB7M_#;Z@+(KrrZGeL_g!et~0&3)P5ss~K<I&>`%%&ox&+T`fOi7YY(FP+y`^'
    'CHVt{#VeHZ8+Q<?NGUmQ*ie~fN{__Ifq;rKwq(XsvQ*dDBOuYjH<HT*5!K+Y{@~;8(GjPY>*Fu4@5}Mpa84b{7+AQ<i583;VI|xf'
    '=&vM9*i6XS>BcQRY$dg=K<g+|raqx+#uPiFkO9StAj24`O)aV7BsC8ass9!Gp{hySk`a&`>>^(8feV661Zf-WD}88~$Urb_)exk0'
    '+T6Gy$(it%tBTNw`(R2y@M-v_!E7nFfH&d$K$MqzS|qCmtLU!X(ur~O_Km$$oLzo(gIvmb`hb`aIMQe|p;mo+iX6N*JTfn;)8<!g'
    'OMivRSYgRZO2TWClNBCLFq2^|1`861FWAJ}1(`(2-A%t}U%6~=Bd6#jqxnW!K<Z(%6^O3LydmNcD?uYITACX-q+7MZ${J%9g`*7X'
    '6*QCsJ<*Ps)r+G{g`NW`N$nwX<8DqY$2}k25e8&YSpmxx!Xc?fkCGLg0MaWXUN_Yu4s)_j!r=m@>5aQO-ybhel@E)KEx0WCEqA-4'
    'gdI>fP4Gm7^8mra&<9Syru5ov-S3V&amq=!&wDFm+Ys3$cug(p>s~BJ2$c{hJOu!)MGH|5#^}}2TgZa=xPmP&e`6l+4KjX0GmTbJ'
    'D`~89x$&t{Gyx{l-lXxJuiePQE-rRfC-bPwh)*vka<qC-NajTYz@-7Lj+%(JH`p%rH;UXh>_x@U`6Zphchyw_>|lgxQ@ldeWR6EC'
    'M6RU~!K;!#nWadgI=O9Qi-<ZdUs~7|TM<goNDm=Q;AcBS0S+RT!?;6KND-%2=mHL1yQecO^4DW3Z)r3$6|AvNk~mNj3>UJfyYyu_'
    '%EU+=YIA)7!m8Nqo!?(2IMS2C%5+4q9nA@x?Qv?hqS_+AhnWV|S7h_6(~_s18b?C&(7*G<N{nB_eFpD8h^v?up@KLCNrr_1xW-7%'
    'gcr`$^~Y|>Ay4HHoY|K`RP-7N1CT}c2%VmWZa|R&fl%WyX-Y!?d`ws0ut1AC*3|rj>^h_d$jZqoS^94x0q!_7{q+YZ_5vPIJ%`Mu'
    'e9Ml`))1THSGn$8-VSEKjrtTUOR^}Jw3+qk`oT0+&kJ@8ipHx`qjO0{9Yl15a9AcCNSn*I4*MR=Y9`@E!NAc$?%mQoXvromO^vJX'
    'vE?R>b$3V0%}!eYvo;*_$zRD80jX)p)6K?Oi_RBjC&*r|-^+5xBkidD+7Tu8<oLWBs=_{iec(Ti=!41{ttTA}@(<>Hj5qG+`(uT{'
    'hrB~TT^Rht7$$J)i5wcH_UN&d*0_~OV(r4!dC>PsiR*WvX{Gd@kyn6dvmonEV=q{Gl077Mma1#~r74qUcf(H7pW@4_VO?!I%HlJV'
    'g)n&V@P;Df5><x`-Qi~CUqz@8FuS{DQ`_a~q}s<c8|2$TuE-E;pti^Z55^T1alH&;z(8ck(#^N+Xjf5>G44lMnV7pwB8l*44TW@v'
    'ia<t1@XZww?e&nSc5)QPu-g|XhrN>ZPOc6X@;2U?$R3H$%u7pctI9A-0(iqd&Sbz)(i=jvgISDE85lm6L0I?(nm^dbby21$eDWx1'
    'eY#~UZ}$`tu#o2jDrSr+K{!Bpk+F;oraAal5(qgZRQ25EeB!@iGv)3e0GQN5=+*hEtq>U6m8e#Me*hWK_a!_*lD}ayk{1@VQ-m_f'
    'U*xWbt>4heY%gdM9H}zw7!ojt2Z0Z_?BXc5&W%W1MJ$SPSS?YS)udA-r0j>TG2srxPDDu{Gb)~2V((iHk>G@&@h_M?;je+!9%HrO'
    'qR%u8c_zFynks!yrbB?{kMh-N)?c~jW@&5|g#5T*qeldKhg=4B%8Sz6C)yU2oSbApAGy<Cb4l`Gq?rIqIdN<Y;x}4vxDWOkis<FV'
    '2Gbb)i7S$C8J-S^GZ|KWZuR_t70;`|!SbJry=^i{Cv%EO-UM_>YjBV^nx~?gN$eUm#IP`~r#!$XJxO4H?oYgeDAfinaJ*?G!Mp=a'
    '=`E~F;7nLd(BZIXL8IH!Xc$(&6`$;DDG{o7g$zFEWnm4Bdn8g~I=fhTU=7>K$c~2d%mcLj)w?=3Pipr=Dhx#FkuA^}(05Mr4Q2uy'
    'eT0=<QZzFd^kvM|`+3iztlbnzA8Y`l>IsT6T?2UxN}8^Zo^BYZJ$5!L(yb3SrGHkxr=|4`2LO3D^l=hXfI~2^MxhajI+3~&wY<4@'
    'Phsy4U$KRJ+8te4{|&4JcV?D`0?Q8YQ%K~pe~qxis23pMQt-7a_;LTTn=@unKOBfRra`65e`ETe!T?!li%1;r6}-$rG<%Azt7E{='
    'uv6uxWGfV5Pavp+_peE5SmHO#Qi9fvl_;4ql4KX-ZJSaxTy58f&q|k1rhz2KG6rW%AC^81MY0tRF5OT!Ub~|=B&B*o7`wJUAUqwC'
    '?p2L(Y8a44E{FsXCL#ZvEcxp9ribGWbh}r?N9x^{?2uY`ke>kqT1mg?my)Lr81z%CbFa+T?&w^8l25(dYgj-5iU(za%g*d8xtCx;'
    '135Ws6mO@-*GRR6#0sJ0c=L8n?VMfx^+xYauA3YtaHp(mj#-n^PEzdv6@u9%xF|l|xU;1<P`fA18XTnXqBn=ofsBmS3X}z^(O!T!'
    'ndD?Y9M`jIPlvBBM<tB)_X*G`0m;a&6>3+9%M#5VZeEB(sGuk|(0ow5R`2V)k>zL~UL$6BS&XEQ@D@nnwwIF=Zm$H)LLI~)GuFm6'
    '6uJq*Tl&tL!kpzDH_x~1Xy<<?X`)IcY{D&miUlJK87iT3MURF#KioI@jS<Sh!=f~>h>y8j)+9_H?CGaJDyEi96y;4#GO@?W2!jle'
    '7MzygOJY>Bxc%}Jp|IBPC}I1Z?$nAWm;BfK@-iAl1q6k%0aTEVhkPU}B!G-ffZtx%AJ!coTCRMynRCDU{AA95cdq9zZ$<h!W_FV*'
    'f@5}~kTL?a$CQNx1O^WMXQ;I+=+2*PrI`A2L4dHptd`D)IyrbXQ6c7w1>VYM4aR<7|6LuO2ckR^jF<l`a_^zQY}NP(ycT&Hqnz=e'
    ';em){5dts>g9AicS<{qm*+uC|5K)*zAh$V=CgQrJacQjvm0%Ew*(=mUd~%xlH2QQjpSJpd(bIvxJ-8nW>AIjX6OUK}xG|I)MCqks'
    '9>JX;Cs0BIybsjwE67l%eIVs?`?J;ENkvkskCA&pz*H0g(8zLx0n>&6MROni9CYu7DN=deHn8U2?47c}&At9w>Z8l_7DY`|s*G6^'
    'LJ5d#xe;E=&;a@~jHxF3nbz-u|NdC8Vw1Os)m#8Ly8st3L%d*$Syv7GS!BO-8r(RpTm1A2bPTHA1FQ;gMoj1+En;ngH!1BXSm5v&'
    'aZr~wmm!4x3VqyJW+na1xuz>?c_76iG{y`Y_N!-FCQNVI;(^44I+s6%{SJX}@ar~lhCN>oLcxKKLOTihmC-Y!L$YXj6x{gAh;9Wa'
    '4R^pyE6*c+C!C(@q=81$Q6jB4D0g^fQO81{?$qSPdxm#pQKK_3EUnuCgc7$*oUG>uAU1{!NNDDZl%XQMckXsXD#S?*n84WoL({p7'
    '+gKziWhsa^(jVYrflz1EH30#cnwsDZ2GTL&1Mkb2hn2749HQSnf+`C&yet}NLnlqvRd{4X+afFj^MJA`el%Ppzw(XH)AEE$eW8Wr'
    '(SSqc$NEbZ79br!2Q$Cu&<0UzxJ@y=z^!ZD@-JI5z2mWP7}2uv>+p=%eF+RkzsR5m#km3si%7jefL#|?uYLGqTk1}0Las=llm$}8'
    'Vh<t4uBI|k>0vek^lhYtu3lU2^e0-=qpV9bw;=f%&#4}hr55I^&~*|R0Pdddj1%V(U<k`?qZtZAd*e=u+8`#WVFEC<FmUBTj+3q?'
    '!a^BhY}Detg_11ye*HGI`kCuhNv&YW&x}F}b)zOc1KHqw$9*BA1X+M}!k0mwR=gZZg6_oQ{_#^Pflpo{dMyxhkq?L8AK%BMP3eEg'
    'Xrd;GLDeOY^3}j|La96U*YE20-FDGcEE<nZesK2%TV}PMX_1RP6r~i9Taqq%gG!j(OLi~}!D_GH(McBy+k-OqzBDBVOTDbY%DDUy'
    'vOt#b6w6Y;i1bZYO*0u7`#xX49axJy6vXGZ$Lxi?huTnpa_H#EC9mtGGr>oU?jDyNbJ!-0%aDq7z?-C0FeL%(%cv$t`|8iam?*p}'
    'It9=Ud630pg*O73gEIp?2Q;bCjMcUTi>5!R6PI3ml?9=c*}@r@jx&~rcuW&u8|#*An`H^GpdVfJs(coOY=W;a`d~BxDN4cE$pYVq'
    '7sXx5S4zo@Z-1#&Kew3v#i$Fn&Tl0{n=ERqQVE<7K?$H@w)jd!hG-%zfSth%YiLiVa{Uw9TrddKbX6K#fN(Rwh}`X|XYhuK>QwO9'
    'kyxcBSFU(g2)wFkYkF-=Lm(sIl0s*KSs+@oZdCS&?o3^q&@TO^VlMr<gWVq42B=?g>X_AF0Sao(OV;d7)RS=EhefD>ixA_e7=c^N'
    '*xr`?<CHG$NRvu-<#^E1(PZ=llLF|x;zZ}gwik1N&SD~AW8^K&*UF`FWZ+Bs>(Ps;xx4(*aXy$tgwnY0ASpyA6Fih6V4W~cK&L3G'
    '<GKwjLY~5~E2vIzBk*Z)8VDjFwU_H$lt-a~9l%iZwyAyO%f#gZ5fvRH<(LLr0Rs}G@ZHqVG5RQMVL%kZ)Yqb@VY?GzszCkcbJ!eT'
    'o=V<oQr&Q8f!0DSN5+*jq!W!a+rhS6Bc@OXg`(_L>n_Neo^E-Z92x$wNF=0;$QnsOJ_=eDBvpqlg!!$e7d17j{&)(A4kDqe(w;_q'
    'ItYLPb`%xaq>0+BN9#%-Gi8y*cDp4xu2}r+r+Ts{*p$u3xq-M5=<_&DtZs#jLGk4iqJw8LG(cK05^B^e4XB%cto!AxG6+3wn0UnH'
    '0X&sS^6))pZWrp$<@Jw!(O%^D^z;pT^DnS!z+t#H3O;$v%wU9t=0HI|N*Y8Pl;Pt;0Kp|PLz54=C~10K^fV`2BO|>yX?c5JDEkLZ'
    ')d3EKS`Oxe$b%e!^h2q(LML(tEH^^s>aX_YuQR4eh3-?~spGxBxH_VCT^=#IV9+ppvj@35g3=K`Q47wMTUdyk+l$7w0J8YnL$HT*'
    '>_q4ylA+F^s(^o&IC+hVlcN0ab;Wb5v+8Bz%t)gLk(x$BgYogalVA;~G1v}axrepshwjgxue|b&8?+B(oB&)13-U4+6;>}dg&UNq'
    'j2T`a&MniLEmS;nlohxdaFElIV{&DnbD{tcdlieSo*CXjet(5!9~md+s?F1=6nV8=i#`4X{0E#2Tl7?9M0C1j)kzOE(=;tDx{EKe'
    '6?u97Q2G1*XU@b7Qamy(tmEjNF#|Y@i=|``!ZaL9&6+M&%%>F(i$(OIsxHM?lV(&ayo^QzV-XBI9?N@%O9Q!xk<#kPT3@^Hvy{Ay'
    'XecP1X&Q(rFsrXI%5?~mB$)sQSrau77a{a<rpU5*TXyM$7X{z=*MQp7Gl0BAv_zpMw2owi3dTA?6Ue_)krV#5>Oyv@@{7S94vxM}'
    '(lDWj$yQFxuvZ~SV(&m30UK7l!-mS0RaR`v-0D&O2>j6urx40YOQxrE2$Ns=V)6;&`fJQwyXeBBc@^8BZj&6S_{_<^sMW~qumFQ|'
    '$s7*Yb11e^b5c}WTpOq%O_50Vx`{J=hT5^Du<Zr>aZ7@|B49zRN#~sQ{it3(gO2s{DJF+?>n?aK#qx7O-8<2ef#Zek;-uIuYak97'
    'X0cXcD7nOtpvB6yUsZ*qWS5uaB4p%{CYRE)<kyRLBCQG%N5=7?%P<JT;#9e8e)v&v%wp~#m^K(Y0U30U9B0H*nf5<PuSbQ7I2Wv-'
    'a=C3>ESTK4i-9r&sME&R(CkKd1U;5XCF%sQ%hPtUn<WLTJx-^F%Ts!xT)dpogQtUr0b|nsrDDeKPkza$w;7WScZQOJ6nl2H3;+J|'
    'c=-$svNhD~YgFn+S_J$i5%iAAYh}QQ7n$a_jFs!1hLCLzk01~iA23}UC+Vm3jva<hBlCb~iJM4?4N#oo1}Q+UUH6rKTYj|$lAVA6'
    'j4TP393qr4U@cTIL`c!rv1(_=MOeLZWu)ShrE>!7An~JnQVbcDcC^14X#~?2IX9}tT=c_!TYtCvR_J3c%~~#atmtRyZ#<%Dd^NDC'
    'g&8K!FQYyB+9;uU>jgy=AB`N65oB}mAy&g@j~f6uoJc_mOLY$Ky02aD<>9zp=9FG83mLs64_eXkB;W;Bo7KYC{7t}kjGJlKwAJV7'
    'b?|3)EMKSm1kfflCHX=NQr0Lam;}sH!DSC`E-(nHW?-Mn9lUc$u3DaPMx-}*@j&>+O;vuhLhu0dxc!n)7<yt%VyImH?2C-E`or;S'
    '0S%DY15a8U717DimBcEE`jq%g9}d_30U|q6mCA(=0eGnZDuLN^*G5Q~L0+hMUiN|=C=Xy@QK2eq+HTE)Jmcbr3-3T3F4&70>htZ;'
    'YGZhllea%%3rQU~8`t4ny{?#4V0je)HL#)7x|G8}(N+kAoQ8>DI8-2mLXFMReyoksZ|+6!jHoXEbkq=Gw3_9?r_4!4s1G_0bjlg$'
    'sN;+wC)nCM_=MR4lK+6`_^pt^6AbYy6E_R!LG!A}DVbNE2{LR)yh;2YYIEsxKW53VQbG3G%TSQqW0d0`4J&GI*|{zRO+<u5Q3}RX'
    'Te6&*+?RhV&lG#mjO!2+k*GO^Q!|E>6o7}Td;<Vz7~`rHH*jVy-iIKt_$uOHuIapttl+X>d6=@TDu2xMMjCg>%hs)W%6PViU4@>P'
    'Awj6W`H8KhQ&x-~^#x`sC@vFaCS1*~tNz_smz~zXocZ8>M+t~a8PZQasO76#1RUu5XxwtdnVuPH!^q3?0wumYi_lW&2tdr{v0_gw'
    'Cq9y#fiIg{f&PbjBp|6-v8DE=IC*H+l?;5P%=PM^kuBL}gba<*MiiYzZbcn~?{Ko5Ys;0BVWf;i_pZWSo9Rem5p#|;OJE_2b2pEg'
    'O(GG7S!kKDlo_B3eEM^Ldc$8f{1t2SO@TBsi@Qg=8NK3YK^ri0#m38OB#X)=Y8cdmX3fH{ld8@mM=l?=K~~-P(s5J4Kj-Iy1jy^4'
    '*C2~t<H3pJZM$myvr~Vab-hfoc=8h8!6c)@X_?U@>Z{RoQS!2YKHC)C`hMEM8IgF9m-!y+7tn%&M<>2F6XG%&B3R$SlZHs8BVjbU'
    '2c|HHn;(nZgrD|MwJ?vF_P!U`hPH;D6I3leY_(YF5#bmlo8vC@s~6V4U7&_wtO1@$#sZ6x5*ZUxAYIy1NF%TS62XwUIHfz}G(V>5'
    'sL48qX}=kuluwBhhmZ&vD)mm9<+(k=ein7Tu;TOf86iq35u<bx=HfLqve$rurTk|&26>5xs;D+{+2-h@v6b&HDDg&6CD1hOUDt`7'
    '5oPj7$DC@I3>yFwXu8-0I9VtxM|SDYpV~f`@ic}Wikd>D$O-Y{vQrp#8gd5gAJMQ;+aUBUJ<S81;z##37xC_ul<?-hS3SEBiM5kc'
    'fhKJAnl1|%fuT#wU`9;>7$T|?UnZs2Y^Y|oAwpt|Qqi$dR3qxKnw>!TMRp3Ti%p281VCG9Z`w}X6iLs_CPpKp34_X^9y`Dn5;`Mw'
    'NXMoW>bs)c`SMPdDU8o<TNn$-fq^^XmU^(&2T6(!l{#^H7*iug7!<6ceam?(z}zZ9YwT;8|Ht?N%$Tu?W!54w9bHkQLf=c`1bdip'
    'Ft|{+@KFUQns;VH=qVH{1iG(YcD+v8dpg6DwD&0G7?8rzoTV^`wtDSF346L>(|*59grH|vauUUj8s3hF*MiH5I2IBw<8ekY$^!@g'
    'CHFy;x?&S6nM5;KFD?KY`?$=h$GzTZ4kT1vA;Hkj@XjocJ$S!^-(QsA)cpK5F}t*vkW>a#5D=i*aqb1cN68Y^xW?3f&EhLgAHCRF'
    '<er6!sY;@e8ktW}mUlpwH0^|=PAgVlcLY&`5`@U#(e&Wm*kO|h7{o)NuF%x!0Jg`(p3-Ft9XxN|&26ur4+J?L)U=Zx8+I3OT!V6G'
    '{WM6$XXz>E*Mr7|wHr8RdQ~Gy!2}pT93(*tFf+)v85%a}f`)=K(+;A5Zj1A&KHEb5SSUUKE4LVGS^5y%(@@I*SxJJth8gtBG!V0P'
    '8}%bmv&8Sj8~!(<L3#g7no|$ZNhDIa*HH(#;&7->cJNA;xm<NH`U-XeSp&Hr3MMAP3a)}>hFAetnNE#ZR|HM|wuQPTBt(52M_QjC'
    'Q!<5=3lRJjB$$N(g6R;7Cv1v}?tfkVXQtueLsH0q0WV~f!@y7QSoj)rsz|}r$B~={7>zrz4>xV2g763>$;^SGmz0#AH*X*I5SnQ$'
    '`iy2-Fen(*bTT*Xqk2LrQ%)#?W<f|e5n!~`%BOr*CQC03w=T-l+)b-Dqd}>gy2)F*9I#7cbTJaD351%cO{~Q6k`8K5ks@m>?(Efj'
    'fM4^J?#miTU{jvIL}jh~Uzj1nP&1r?;iTfzfMmRzz-NkFgbz1xkfmJdzMvVd6bbPo{fJq%#A2Bwd9~so$$%Bi_iPi_hKSc8msP|3'
    'SY}$Z3XME-)4~E-MkfJ$AuAar!VIfV<?9xzhsHuE%W&R%Nm?l1?66$pfCh4A)-+q%uNr%E<v!l#vsM|6L&;?#QEoNOx|J!8S2{^f'
    '0T+j6FVr*5;%wd8&74~6q!$5d&_+X}_Ju~BC3T^g0e}YY1%jkS7sSMGG*#I-n5-mL*X~0z7M_+2i;Jo_1(cSz)ri4p8u^X&0B7T3'
    'Fsc+c+ocH}if!6Y_HxRw+0j#l5DscormCT^kP$tvhRO@-1HwS~hp-_yNtEW+T(^}PA~!~YL9+<4oyU@nYmO>3$VVIo3S)DlhFpX0'
    'tqolO<rr+08WQlQpm5WSfXqxnPd%qlNe6_BjwUvYA8M~5tc@B!YX>$}_=`us4p9u)4ze%05t<ZOO{2ma^u5CHCV&Gz4J)@&=Uc_?'
    'z_1o%p%6o9l_21rmD|dF7ZE+*P8^4BZLXakw)bB-3oqvj^$~(*L05p3o>MreyU7FspgaU<28pH>F`B^*^cBS0U7Kay3v+vtBdL<#'
    'P2TglZi}J{f+P)J`n{mr7H==G7@}B98b}mtRgXmex^^o>arg!9>E)SYvebgRT`r7M1J0+ZLz)E#2o5KlX+8{0q99!~a6D*Nb|J2P'
    'D2$4I`sgb8shtGlZjb{i;2@74iUF-9yxp)K2X3ZYE1Gy)1Y7@g>32Pb<%O*AWNtLnO-g!A7Qqjdh8lt!ShNF5dRkk=b*wJ^+D{f9'
    '_c{VM<Vq5r#!&cZc1H(qPE*Xd^N|k@no}RdN*S)-N0Gb5m<;|8)7J4)0t{}&J<YOHVUQTLh^UFMw^rXH+QKT~LMOXr0C0Skjphkp'
    '4a?IJGZO)=PqalKc2ON&v5yr(1{ML4!SqYGSP!Kf-Z7(s8Y1VUSkf;hJWaS_7nPC%T0pdQ$%7I5(FtJYE&q!$bymrW_Mag^Sa7Va'
    '(oRad%~^R@D$$@K&1mSUQ9<nprvTeQ6lB=mbP7-=njyg>T)T&LTxbemtWSs*e3{&=FwjsuHcnLCQImmSVskiFKM113V(N45RF;Pw'
    '0_sD61~UOcBojt#AuyX_ni&boZk#OIR(~LC2EGS%gdiNs(um*y6%07psMSC+9yIv3AKdEn_q+qXQH9W|+0*oE(TKqgr&9>cgJ_P4'
    '76Ua9tjTRGQnjH(Xs_GI^KJ?0+-%$MtziBDfC0Nzr&Q`S-T(zENH^pviYASI&*Gv?*KK5>3)H-rhNKevg+wNfk&#BQd87f8PNt|a'
    '3DjM~57$PEC#^4RQN#&Y{MZr~no^t&CK^LufIP_E#RlkSV*|p}2qXEd*mi#Pr*dv@uIno!f`X?(u^K>E)kziO9r82#8Z{vl;vpH4'
    '8L!*R+72^*g+R_moWBM)0F-aEK~Re&IaBaWkFwWpt-o$JCrV4zMxbWF4dPORk`1QOFCg$T-ptC*n%<NVEq(PXTC|_%{Jc^F3c5g{'
    's3D=6atz_qkAo<Q5V##TFIHGQozbsN1)sNJ_qLOASe0cXX&CE>=ZdBbnKKW_h<@8iF@U8i<JH_XyEwg<`?SN!ro_=?o-p(id`6gm'
    'fqfB#Dhayay@=*b{vknIdDg>++c<|4Of)o6Vf$3VTo`Y|-AY4>R47Qaz<tBPWdaXsAXpk`Drn=Gs~*Ygx4eR*Lazer4CD;C(Y!F?'
    'DaBK7WHn@RYN3KRVCSpz_GLToxUAI>DbzEHNs4N6Aev^h@dEcDGak5nkwCJ)AoriEw)1K%PKkYAqh2BlunU8ldTv0f&g2pT3gx~k'
    'a4;e|+_d)GRo~E=Xj}VSj0Tgq1|K^F3A8i0j)8!pbcqzf92&XnHhJx({MY>>=6)Schoc|$EPIiQA5aWh5DjWX0xjnXC~g3`5S-TL'
    'jl3P77A#wJ9@CkN#e}XN03paISmNNu6EFuue*_~M?lBe)u&<bIGxh5?60!7rdl<Z``|Tq5FOqQhVg?Njn4|@V#>iWPw~CAuP=elI'
    'kPys{Yd6GyIewaJx?lhgB$5!})rW*Tqm40>mB#^bH)yCOv=-vc+KtrncQu*X(f1Vto-l`TE;KYWcZ*{YyvKnA8&Sa8C<jh=HhT{Y'
    'Rd<;47j~gA!dEOn9lZtm2S6IRUG#8EQAH~FBjH}Tiwg|fpUO;bnpwB(AV8mHhgFR+)0*$(IE^+>rYd>uhobtH&qD(tO9K*+ZpVS%'
    'JBl88fNEd`w)2|4hVvyU38TCr$W3bzkTcnJb5@|rgr`v2z@6qSPO_;2q3p#2gtKBa9~%q+FJrZe=at(yi|Jo?QzYonLom?ChF-Kk'
    '@iDkl@GT%iafqC06as96r+4eOfsw6b*5rq$I_q-SLSF`XP9q&*pvod02F<8B@_e(fm%!)vXvei5=ZOydoC=}AGYy??pS-CW##|9M'
    'q2%JiWOd8&E`aao%f|ky)$7Q}lK@i&wYKCPGBm`w!V(MUnS)N!1!aE|Dg4^^u(*evoI+}#Y>{&^2N44v>|YoiN5(#DQ`CB`hHt_G'
    '7j2`oi**sn%ZZnP28lQ9G~O6-E@H+W&J5K7BsNN0_$sAU-z+TNE~)dFpTguJC(=9Gdfb~FT_t*1w4@FE6e+XNzz5ykzIycvvo=0%'
    '7(oy@E%T0n_VnUWvheibW{<d8kXYqZWas?l*-;<;7;ia3b!c$3CrPq=US$3Qjc$mg*uu1;McY(#+dYSw&+gryEF2iL2W%6e-Z6fq'
    '<%UIv6*Q=wrZRF;1mbj`$Ej|`>cEB@A%@g6#puIeImBfXv7=*R1qBzEeUOtFVYm20mv6W(2kc-~Gbv^2dq&aD@Qsn>EW<E3zmU(E'
    '(IzjoxoSnltU5wJI&*ks+#((<ooth&4_+=dl*^<h*bFW0m!YT$ez$B*q+kw9lI`NCc{<c5SoJciRL2?w2<1798c>g-<Kw$k;UudM'
    'eHnH_q{7@-zDgr!M`ovSoRA+8BN~lo!QqGzI>nmx-Kv#01kw=GW9{Q)S4D>zcK!eyjKCeYb0!UdW-#fbhztL1;fhg8aCLEc!O%5K'
    '8hARw9)gnLKney5<%u_d#2x_Qv!ze9_}%-2{q9&A`%Yd=7Nkj;_(gymwHl2LjumtbV24ed9_T86dLvR(=H32LJwwzP?%~IO6l6fa'
    '1dMa1kZXwibSpJqo`KU)9gKp;V!$?j?kM|yy)$c42uR6GAM;L$J+RZC0JE{aBPx*ll7^5ZWAUqcJ7bQvV%am^UtU`sNyZ~4eLBeb'
    'Xurrke_%v1MqxRDHM0v2*4njS!R?AIfOEhThlWQLMBhtJr3|!`X#u+EBz;8E!01m;HC4}1d$^-K%uI*<$M1*T(}iCQ{s|u!rjcfZ'
    'psUlcddydnXlDRl$oVon(NA+6R{0%L#@*891ZDg97{9-Jnk-Qh>?-C;0V(y%oxlJL=Egy>LUh&%BK@3`uW_8`A=igH&A|M}@z3L>'
    'Q9tbrVn&NM@&pkhP;!$_kMb16rVDuwk)!=wQAP;7d;O6g3o_pSIJyq(pFRYwTP8?SJyBINppW_*ra4|sL87A1XH{u6@u~H9cMH~D'
    '=t?2khU9_kGxY+UN=6Yv+oN)zO*p`H2V=mj{nNVXKwfnRpF_QcbK%OLY|ekOdGijqoW2a2BMhYl7fLKWn34v^fl-L$F5)@>!NAAi'
    'pMAE8x8J*0Uv^&(govD}2qu7YBb^P&3ifsA=X+*LP_sLELNVv=qZ6c->lg37aZca<V<G6u*qs@!Q~*>%4lN|gc?+WnGm1duH`2q-'
    'eZ^X*8JEZZz58G3VTlL-(;dGSFj&qC{CpB_3L#;!USDN&%Un7E<h*VBaY1@oohC{6dUs}Lpb6YPmsOBB0m2hO*s7q=LP!W2LWONJ'
    '@t&a==m8O+en|fOXwCCqOTx=2ZJpBxLn{FPItp+;6^4hwd}QoFry=7_VaZdL|7Bs&6^39lycEtH7hEg5AvA`Lqy?%NS|!<xAV`68'
    '8tc}JB*DjmOiNz}l_HjD(9>w&W6g(@8o4D?OtH^zME&@XlJ>!R_b-eyEHD(i*{LfE-pF-HCWy-<tTVcQNG$N0AU43Ao$J=ar|ejo'
    '{W)r45x#r;ASR5%S?2j_S_TCqnV=kGHJ3Gf`bmcE-N|p@@a5|^<1r3ycN(AeyemWl4B1eIVsD6hD`H_VZ`raDlECD_6k#e8lt3#g'
    'meyKjP6QL?8O?@&wro0a%)sanPzHr8&8yBy!Gve&@S%R{Zwu}hAi3mEjhzpEC?mX1>_hN0MidJT7fmW2trTvsVjH9_O{!S&<+;er'
    'r!?#!paXi&qPozQBd+&q?XwB23~&ddlA7FStHmUrYv|2CNO1Z34>HXvev`dSxR61R`k+_@SQ!zhaIZl19;En2h|8Nbt5#)t!M0E{'
    'd6}crkwCf0lH3}U;GNtoG$ILJ2Ls&()1+0)7B8?MH9dVRNYzQ)6?_aF6fn6P0km2%<1{?OtXcF_i(kG?P#X#Mm#Ho@8u(!0uuw6A'
    'q@n*MRe`rkpYzi&3vcLd`8@9a`2x(5x2HMD6)%@`9vUX5*#Nz=B#}WWd=1ntRE#o^l+Gc1{**skxrQc!Z~=1}A_8$1=R0l|{8vZ='
    'Wmh7_3+~65NVThf_198hq8~YmzYp`3KqS2xi3*@TbzGy=NG3cKY}49>E5^rCBhWsfa#Ldg9tyu2ZqB%XJP;iji$a4AGrCWgJ{(@s'
    '9RwJ%m&HZ#`RGb=1upEC6U3cL#so>Lm5`sK%>ySf8!#hlWI;Svty#X~Xcs`I?)f>88G4x*^Q1Kjl9Ga9Y>brW0wNc#TCV1b19By)'
    'XOId*&oi#J#4Elf^bhn+Kmt5@zQx>Us$B3`$~>X=p^n9BA2p85^%+UZv&8sJUolUUKBB<b@w4^L7{e*YuE>elJGTlK40m{z8#o>#'
    'fE<+h#D5MC{17UQzG}H=u5XIL!i<A<(fdKuV$K*7b7eHq@b`>w!jD_w*T}zis#@_Qk^WC{o^dM^zW^FGQ~Ch$A>tdsfW5esQX*zy'
    '%D!r`(?p&E2@0vyteMGpFOM)OK(oQ{scm6Spea*U%X$6uYdFXC*T2?`*Ar<PjfJq(S)5reaXJ(@Ab_$`lnL);FK+sLN%Ehq;_2OT'
    'Tn?`u9tFo1GpV)Bo1-nkG2tQd!}%W=2(fSE-@?(gt5+>grJx<;G#Q#vKTO&YqrR7|CgggAe4V}x{8SNctzVj^e%$5D9Cj3=n)@t+'
    'D>{UlzlN24M}z>D<Dell@QbRtesyGme;h<Pe10i#K$-PLq=ndry+e=fRHQ28^+Nn3L8Bpr2!zSu^($ATXCr2*!s)37>5R}S$f`Z1'
    'D8T7jF_<lc(5zUKb^iHKkZe;|WFthy$<i922on}k6mGR%&ao7!sJ`a4i=JiUh51RaAV8B5Yp7ZxVesk)p~w^Y2`5wT7?PQJ#p22s'
    'DyMnLAp#;T(-CkN0ZB?SKms8HLc+0vVpYaSlz8=vgFVt2I=Yjv>(4^!Lb3wv3D)SD)5~lKFbM8}B$6$V5|&V-3@lbG|MdK*l@E+C'
    'EsT`IcgHoFpe7<7Gqc1(^KvWXUVsKin*s2FZ>)ap^KEpJ))fF?R3P{tIcDvUQ!wt*w4_cDy{tyvOdSBsBr#R};`;N=Tf)9Aac2i%'
    '0m42yecmEr4%jnb5ZS8W!v+m`of%U7`m%}44+NIi;C8pLG{2lf-0PoyIf-+>oYRHvS**IPYqKe#B-e%91<k2ddOzs6f>DwB5hQRs'
    ';EfLUzkl0*HJmHAK7ux*aRtqTV*&rj3rZwMr{e)%8Mh8fCN8nAV(TX}%1?snPj2pHjP!F2h__xZR!9sULEC}kT>4(ko#FzSYL2*6'
    'M(8w`jzdKqmSlL%_d|sVX2FO|N2|r5Mk9>!o#Ch3@|o4dv}&-8T7<i(VVW(8mprE_Co~m}OiZ?YI6x;k&3^hxX%uE+4niSdGFvTy'
    'u#r?TaRb0Wf*}a17LE#pwje4mt)ovX%#)kYofk30?Q4D)mZ5YSVXwIfAeJJB+)}+Ut3k^Yd?Mr1LHRU4KkV=Qru4H$%_<k`g9$O1'
    '(-Q?q&>NaIxCU|m&|=2GA$6aASQ1>_oxt^kN9~um&C3kK<F?S@Bypw7gc%tc9~nI&o0LBnuBL(zn6XNN2MpcTE?i9Jm~BP=K+43g'
    'Q7=l3r?C_COql~e0hgl1LAQ3npK9jIbx6?kXUg$7;~5V3135?11f(EYp4BWOj%pZdS1!UofP|7qP-2Ou%O?rQPOb_W(#mSjsEo}Y'
    'JMk_HE^ED7&U|r8^Q2%F3bsyd#hf&8>03!MfN7J^VWJL;qS(NH>GQ+-^OD5Y*Y4tFm>p3(L@B7rcy3K-v^0bfs|_q@ME#&HQWMVB'
    'E&8TFzWh}p>1;Gi9K0K68IiD+I)U{AhT}mdO(i~0u5Qf=s73fM-#v!lVxg<@0Oqj}h;XwaRhG)57m>7XK_SqOigpE=K%U2Cm;gss'
    '6HcuLJhd`S6q%O>H97jnT=<XHTzJGajW>FOlsOz8Ox(~S%o5ephT`-9^l)e4JqwTNLz?P^bqn(g&=_cp5+^vJV5g|Vkz@i>LnDHk'
    'hSYqfjvv=82}gN*x!jS?5)VvjX+6zZ92a0yl3ubhsbO2qitN+MWnZ(J0!-V;N*8|%ycBSSAqgb~can|MCr2I44ycGK*DeAh$iAtq'
    'u)pfm%aEE93@^*pc7U6%v1CxtjIUm;NEni531?^)vz4|U#T0XGVBb+oV}!=6Vmx*^X5*?AKN_I(GvtoTx8~&t86^_J>1)K@WXLBI'
    'i=o<~)8pbXb&DQIKmG3Vs7N3?X7^2^m+1g6Z3MX0qBcVb(>+5<<mS9;#Z3`)#@s>Ej@3n=RGZ|NGQnx&6;7IfM&7`eGtd3{Wvke#'
    'VmdH&1MnHwAjtLNE;3C=I&RvWknK3T#Eog)@{8u8z(S+m0OA8k#OqN#YLEjNep0a!tgM0*e>$#P_oQej_&e~aj&POWg7uj6@?Lvp'
    '2+<mZvQ4lsRI)U5Y7f?uhQi@I>ya*J^UbhWjyvUsfPDl<WD}5TC=>A=WdxYfmsR<yi_u>LFcADk#X*h}b3PCbFt~=%AHeRUymrwN'
    '{_Q~j*Z=rGx_kbB'
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
            'sha256:8527f25d58c8ebf8eebab8a9e43517899b7afce2e511026d2873a69ab82f1794')
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
