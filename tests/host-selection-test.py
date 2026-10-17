#!/usr/bin/env python3
"""Negative selection coverage against the real trusted host program closure."""
from copy import deepcopy
import importlib.util
import json
import base64
import zlib
import contextlib
import io
import signal
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('host_impact_tests', ROOT / 'tools/repository-checks/host_selection.py')
HOST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HOST)


def historical_workflows():
    # Exact reviewed source20/21 bytes; independent of active22 and shallow Git.
    result = {}
    for oid, encoded in (('d9fefd275d9e3c6977cf9350a1945a6bbe5051b4', 'c-q}s>u=jO5dWUPg6WDn0Ve0Yb{;Y;ON=J#>I8|?p(qMLmd-XCSyD;LiP!dj-|?k~CClz3S<!xq$-Cq6cW<gck&~EByhsqiQZ67MiRa&VBOoJ)fO&$((Qm}_1)ZwD34`}3Wx(-|DTP~P5FQ(WAW0ljf7V`$ya{y3B_uJYB4#t<kHNp;YjM<BBP2<~(3LWP3;CN6F-w5!KOGV$cxqsNFev@xv&bK_IHLc8S%H9xY&-M@5N5y9DF1yMvzuWU-?{<ii6{KAK8;36D$L1*urxxwMtCz$wW|7G0NiIZk$1;ir4bQhAbvbaLJ)wvQ|f~=WB?@RCV~RXB*+VP$RLhG@S=j;p_hiDBXNgp)u0=6$j}QptR=uERLN9|`f(&6LZy+=3)b+bpE3rKKa;y77N?2avd}vkdgt+n4`f8eI32WMiu~=O71~ic82}?6KUx|FL-OfUl}ma7UheRav^4T9^5h9wFVXm8FB$=F4?GTXccXS!P!U4m#5vwLm~BdCs}Gun29mt>KJ`L6q`vaS7HTO$@gg5Whel4qVr2pY>brQLP@9180#A4jk5lG@wyk#4qZG{<2`LcB#U&ANCzM-h4;gk!8oH86-M<K6tDvg9wkz?IL=%rj#m)Z#MRkpoV}OzNR$J3;*?8bv33D=VlyBXM_G}WaAshOVuuuU6C}0l83?VPP^=5oSS!_emw&zIEqd5Ayx-(CGA5GMfdM_uwp-F-W>3hrtgZwua5PDG~Twap~bBw`?JK7DdFjM#<i@rh#+3aOf1b1W_NC#;oQfGI+y}hq<7@Yv(<xFUVsG<A=wTw%}6k{*y#!)!y5E);XaT9I~XQ<mHGVS7uI}V`8l!RWC^WbJq$^p{?6|;rpmLO+|Frua<`Fdr+2?Dd3i{bVTVdD#rDN*Ijroy-wxB<nRF1}WUvMNN<FXfkuRn~FLh1&>gg|aGSH6&`OtHL;lr6Q0fXGC0BOanKs8w<GS39BNOTcbi*71C&pB2kr<MluR8<d*VhlvaqMwJn5>=wlhSG61u_MkX{GjZB|n4%eyCB#bQ;>qz#;Ua;ry@4|uS`3D2<+4jM+-Gjh;`pf>#w!iaiXZPve!25N3uw$g$VqWbOYWPrJp_G>Ml+re(-yJZlT;m)G=?5stYMieE<CF`>N4v>lg`I)z4=f4xHH?E}FVG<$vn@hQ-Y=|3H{@HDMxjE1xlB0N;^479RCaZSa3oQcmB!o|q%;hiQq3+I=@R^SB>Op{QeD<n>B1H>B5Rl`$3%f>Poe1NYQg-5Xqv<S{M7BAzv%W#HW2X*L`9@~NBy%`UH4_Te{^!xKXT7{{cf+XdFsnjB|TGBdUByy9y;WACpX(njN@p}nsaLb=-TVr$t*9h#k(O|`Zsy>`1x7?^!iV?`wCTcFOK@BkL;$SI+Hny-qFjhq|ln@yXV*ai|hWQIa7FnZf&#R7P6_8t}UYo?yzL2_@P!aS^JmQuXQZrvKwpNW5nsO$u!T_hk(t#6F?%jcfTs0iZSGry9RAWGGy^YAqaPPJ2WOvMHQXC3^VEPG7}aZ?X$g0W!)vdlpDVarsMFjmor|S9<AzI1}B{^9tbXd*mA&%Iqa*k(imlkt%w!wNV74EkfVy;JFb$Y>B|beYM!A~i(cDXV<%oDsfX>*!Y0XE#yT681}A7eNd%j!S2qMLo9|X_#!cH&>bdnip>)fph~@gO7xk?pH&<9UgF|b{@KZFsntJ9FOWqnboTlI~9bM<%#uQ@0rZTzQlQ)<PHMoPJ$o%137<HqLzS@IJRfh;vVTN3VMFzYq1`x@1h5}#8FI#P?;G4It<&(66qrsc9lV@||LY)Q+<^;G)Z~-dKdebFpy7f#<b%<(`l=tnX6MulTWKL>uL__gS9kGtQGC>`d%FbffFpQ36to4riL2e~ImQ8X^LRK2(ngpyg%QXp@8|H%8PbavbhJ^?4uhMx9URI);_q8|byq|3ucw754wu15|{~0mOuV!^b_O)y^AZk3`3bhQSTf0+WILD#Kt*_|$C3e%08t=D6PWD!H|F*82*<kMq?Y-xhOsQ4#N=3y5WoHP?%|3z1PK0@?_LvV3nV5X*hxF}bXfKX}DtL=R;j>?en_sT7=_pUrb{;Rxt`GQ>B`3hbBg&V}*Y={XB!)9QLw+ZbFAElDlHpvO-!5MFPtSWN=e_<vmuLO%pRfDf<MWg5;Z8o;sUfc7&#EWGsZM^>m>-XSoQ}P6wT9$Yq0N%pg6}ycP1kE<cBN?CEMyk@kvGeuj?FRVSE+iKwMx#LUoX3kQ+x+-Y<qGap=uwQHAE&ou<!JhdA0cbo)Xc$zwk-N0Y^{#U-z`Gk`T7VVu=5-LVl7S(h%%(PVvE2weJ{hA%3q5)jVe3#zah1fMwqRN)Oz}r`_Wh?q&Dt`tSag_5l(9b#>m;!Ma&A^(v3y<=3%g&xli<wU<1ODNP)CX{0DA`~^>EYySb4lWnp'), ('d04a6dc70213d8b549bac30c11cc15eaf0182dea', 'c-oazO>f&U488kT5J7>Q<b1E0feuTDVC`XD&?UPDvdlDEZON0Uq-oLrKFN-gG>5J8!GKBnk?-+IiWiu`#L*fRNx=zWb`OM41ei&RBCV1LV5`mJD%abk;CUVb0NPRM$krbK1rpCV@ugJcp_(wjhUd<=xOjPiUplq1L7^X%e8zZ>5TE@Dudh*5qA8@cQmd+i&{fJNV321~6p%vv09N-?6`T7e2(l;~@ifOHqZ;aos(Ry;Wu76p)G2bTKa9J>DnqhBKOZZka)iF`=slz>mX@%z@xIO9NCt$exPfDP0$<iB9z(Aa0;SP}f-r-EOVto3FA!MmjKG87&W3rp2szsk0n0;u9%KVC?Bj@YF-rNkI~w;#8Nd86>~%$N-0NQsQvR`<_6|5(N$cYpgVw8>;Db-NG{%kR5tlB{mj-`3v=pb@Vr<vEVOKvT_dr0#d9vAQ9F3Khm@t?H_wn4%z4C87DY7Lu7Fk1sd0mkeI>UdK`j%Sfwqvl=R+2WmI%PYDT{KH7cV`<oT1cyW2mW+;-xOtz{(LA-a&zLS!vr!*-neV;umnD_Q`S3LYc&9N3+xB5>qeN)|4&;@%&I*=>*DL}{AO{zoc^5N&6l&u{HE0;Ss-;@aX0xk4HdOPkJ;~w`D`(7oe6S!Lu3$ku;sgh|3PWRyhAf5&>Z#fetF+vxVnP2mjT;vb!#W>=nof(d71'), ('55d08b65a987224ce576459cede693cfd49375f6', 'c-rk5YjfMU@w<Kns`Ffun}T{+q#lhs&gIm^J;!!rJ8dU*H6RE|uql!TKsmZ3{q0=<ltk)bD{01;59coyfZfGn-@E()ohve80g_23C__mc&HjP{mPX0UED#A56No00G-8S&B{Hc1{w@(WVU*nA5sR51iYGB5!Guc*znn@;Caj0fXE8-n67j$QR74izjVEaD<445fG*i-{i4ZKZ+n+yIDoNa{pv8T|fXkF9I@X&g$FaW=DxmhzN5O70E?CghOtU{DHA~@UsRWNlpL2{!60ohHbewPst0dJFWe>d<ER(Pik|^>Cy}6o`NktO!i0yc3nnlr212U<0L}4FNMnUdFpGY>8WAdeVV@86n!J9BK+U>$h%0#YzqYy%KsR_8cqLmXX7OUlk76Z=3FyE~J6wN@3F`a25Bavh&+yUl-m*#>C=28@<wimdF#FRyt#~9Qy5==_VaHVpc_=dHd60>$=E%IHy2Tupi&5dJ`#QZmFx*8D7S7L2inV-cf!_AgcZ<!OtCoIVnp71zR4DM^XW}n5=xow`l>klsa!?$mahZp_xi{aq%<fK37p;{(IE#iLdR(Um_$F<u@1SEjr7#zzWgTti@8^<}nFUO4DAh>kllKHC=kwYQ`#tOXTil|YI0SJft!9Hy@nM(+DebTABou(U*w%2OZX`|C<w)cI~t@{o11Ddv-y3<$?yyI%zTdY7LEbO5P;c;OPymQ=}GgaJYLUO4v1q%W@;3NXxz>_3fdD(y&PEo|C44n-SH{fcvpjD8n{`>jGd4G8R`bDo8Mb;d~+Q$6v)$8HK>9740i!*{}Wxk`58y1)0UiV-8vYqzasmeHS`h!>ZFtqTfGS=DU@$qobe|rhWQ9@id@Lcv8SmLJw1<4e`EK5+zQx*~)70%wjN7cQ#psMKLzvw^j>$ppBc=fSW|GbB;u2!MvPu~rC@#x*ai?7Ww8n}C<(XM`4K>+*BNOZ9GbTmdJ<)|uHn#kJTtD}q8mp=oQv(xjVi_^isYFboqP$K?p_3EeBw+IX5Xv1){8lFFY4%_yY>NDWxpd_nx=I0c&`nOY9%5OUbYYUKECtMA;QYy%HL25%77&F8tlS~mmVmb&0HlCR~jOS{og7-agnD_!;upwmegu+S4AoXLYPc%UDYog0h4A?BzKv3OC76B(v<b;Ny)vynVotdmBImG0}bsSQl#oQK?c8xD@PJii_M57CmmB27K{oB!T87i+g%79-J2fz3D_E%ig@eFJ@-k;}|no1IIcbzOTo9Zk<S#6%$vDT!M&I;%lTb*H3*J2Dd4h(>Q<$>h%^5X3BqFTaOy3z6%#wGx9$h5O1_A(4r0isyjtcJVN1xDZC;$Q~`FIOy}Shed-tvaj)S`14VYwhIQ%UA;xwfyt_W#lMbdY#2wAwT0$V8sVTQWhy$Gj*1g5(}IUlgK=lGM;V+UzTOgwM^m_cRPoql%)mfof#!AT`BC@`o^)>I#w&viAc=QpAOKIh>ZxHVL!>hX@e)|)2CH0&`?1_vkCaLVdTk{&;}VYOR+VhLwHu3`gM;INS1CGhV53P+X*^etJ{Iyme=l3uR%<B^PGLBzBRmAf_SP!kS-6a`%a@-eMk@|pm~tk?<t8GSU7C9y4`lY-Ry!eSh(+Yx?Zcrn()tSxy%i8@bA+7j+KLZj~q0)f)tt$%i!;1N*)$Ks3XKU0Z)Q-_(YfT_dn|zs2=(r3q!x|vX<NOn{K`CdZ68I!}IE%A5bq0sULPdqh8l(-}5Z!IHASyGuu`wHpxV(;MLa^p516y*HVsD&@mR?Z632Fw|tEh)@#8mNT66!(4Iq4n4lNbv~IoLfWcdsJZOO;R&whOI6Qv|2Gha$LI(&aU?8PRglFjA1&RnkGowRX7BPIQbnHO4Dqu7sdSozVE~N4)HgOydJR9j?tF*|^)0+{7?l9yd=nVW(G%<iH*R2sRa{v#bH_Z)unz9mb&Bnus%s>lr)6pG|gXFHc#)pRsoGhNSvR8Qd9rNj!K+6{yV0huJa+jO#rpFe!0Umvc!z2orh`?ZVUWqh__Ylk)(E<jn)^|+KisXg^J){9YphD-1d+BP~ZQ5JtVdLRk4-b;Y;H4=Hg4kv{R%!Q=v9f}AqF}hOnMwdfX0mpsjl7r}mR75?JCC7O5h4-bE0}!%B}nvExo?d;;Kx6h|I%t)uTGfKB88vc9KtI>csayMz&V2gg$QT|WTJ%tW$hT20fP9WM^!-vC9loH%b~&lk%%5Hf~&>)BQKcNkJh4?velCvl??kQ?~VqiCvW;Ex@F9ZYOEt-Y0hB6n4C$fAWq#OFi4P<LsF2)BoR<)>S#{YFpEJQQ^=Yy{v1LY5wSd|7wEvSM@tR#qz`prMN%x1M9tSRQ+BSjUZLU%nu0L$nn|;W^;;x{%>wwQV>1J?bTk?0<qJ_4QjzZNFzn7V4z|M*=q49su_jf^hjqFVkVZ(3`k+?q<Q)?{oS|HgYt7HRXPldi$*wz^$-(Ys(*NgK|K&v=3fTTJ{5U$zyQYoA?J}PYe|f+4M>F-!nyJTWjm*UT(Hf(<-0{-Ps(b79`MY&fxx?BK^-}CI(<P({?~4yLpm9BwUZ0+Rv+(|ye*4Fq<O^K;p|tXyyZmEML%w&Xzl4vmBq)9@HFc2|yHMq_jYM~3CZ9e-KmLfGe*0m<vn_3RW;nz|C?3Mzq2H#i=aF{1$voflL*MPNpdL_Y!`=NRX|=mSyWQ!AcBD|hZ=_%(u=@Ege>yJ24Df;>55O;0H;K}{fZ8-*{#2^}Hz=oczA*XP2FRbZrgsO2W)8kAYcmP0ix%~6m8m;ytp?q&fr@(Qj)=H4Q`cWpwKM`yc@MQK{{ur>)>r')):
        raw = zlib.decompress(base64.b85decode(encoded))
        actual = HOST.hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        if actual != oid:
            raise ValueError('historical controller workflow hash differs')
        result[oid] = raw
    return result


def copy_git_tree(tree):
    # full_tree validates flat entries with immutable mode/type/SHA strings.
    # Copy both mapping levels so each negative mutation remains independent,
    # without recursively traversing every scalar in the real source tree.
    return {path: entry.copy() for path, entry in tree.items()}


class HostSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = HOST.inputs.full_tree(ROOT, 'HEAD')
        cls.registry = HOST.inputs.load_registry(ROOT / '.github/test-suites.json')
        cls.quick = {name for name, suite in cls.registry['suites'].items() if suite['layer'] == 'quick'}
        cls.ci_quick = cls.quick - HOST.PRODUCT_QUICK_SUITES
        cls.all_names = set(cls.registry['suites'])

    def setUp(self):
        # Fixtures model a reviewed generation even on future product commits.
        # A changed production generation must fall back, not fail its PR.
        self.review = patch.object(HOST, 'REVIEWED_PROGRAMS', HOST.program_digest(self.tree))
        self.review.start()
        self.addCleanup(self.review.stop)

    def selected(self, paths, *, tree=None, regular=True, unknown=False, trusted_tree=None,
                 target='main', base_tree=None, package_paths=()):
        return HOST.select(self.tree if tree is None else tree, paths, regular,
                           unknown=unknown, trusted_tree=self.tree if trusted_tree is None else trusted_tree,
                           target=target, base_tree=base_tree, package_paths=package_paths)

    def producer_transition(self):
        policy = HOST.package_policy()
        generations = {generation['name']: generation['workflows'] for generation in policy.workflow_generations()}
        previous, candidate = copy_git_tree(self.tree), copy_git_tree(self.tree)
        previous.update(deepcopy(generations['android-owned-npm5-sync-ci-v1']))
        candidate.update(deepcopy(generations['protected-shared-producer-v1']))
        paths = sorted(path for path in previous.keys() | candidate.keys() if previous.get(path) != candidate.get(path))
        return previous, candidate, paths

    def test_exact_protected_producer_transition_selects_every_trusted_suite_once(self):
        previous, candidate, paths = self.producer_transition()
        result = self.selected(paths, tree=candidate, trusted_tree=previous, base_tree=previous)
        self.assertEqual(paths, ['.github/workflows/project-tests.yml', '.github/workflows/repository-checks.yml'])
        self.assertEqual(result, {'suites': list(self.registry['suites']),
            'reason': 'reviewed-protected-producer-transition', 'full_host': True, 'include_platform': True})
        self.assertEqual(len(result['suites']), len(set(result['suites'])))

    def test_consumer_parent_is_preserved_by_each_exact_later_producer_pair(self):
        policy=HOST.package_policy()
        generations={g['name']:g['workflows'] for g in policy.workflow_generations()}
        for producer_name in ('protected-producer-postmerge-original-e-v1', 'protected-producer-ci37-v1'):
            previous,candidate=copy_git_tree(self.tree),copy_git_tree(self.tree)
            previous.update(deepcopy(generations['postmerge-original-e-v1']))
            candidate.update(deepcopy(generations[producer_name]))
            paths=sorted(path for path in previous.keys() | candidate.keys() if previous.get(path)!=candidate.get(path))
            selected=self.selected(paths,tree=candidate,trusted_tree=previous,base_tree=previous)
            self.assertEqual(set(selected['suites']),self.all_names)
            self.assertEqual(selected['reason'],'reviewed-protected-producer-transition')
            self.assertTrue(selected['include_platform'])
            # Neither individually approved endpoint nor the old parent tuple can
            # be mixed into either complete later installation generation.
            for side in ('base','candidate'):
                for path in generations['postmerge-original-e-v1']:
                    snapshots={'base':copy_git_tree(previous),'candidate':copy_git_tree(candidate)}
                    snapshots[side][path]={'mode':'100755','type':'blob','sha':'a'*40}
                    with self.subTest(side=side,path=path):
                        self.assertFalse(HOST._protected_producer_transition(snapshots['candidate'],paths,
                            snapshots['base'],snapshots['base'],'main'))
            candidate['.github/workflows/parent-qualification.yml']=deepcopy(generations['protected-shared-producer-v1'][
                '.github/workflows/parent-qualification.yml'])
            self.assertFalse(HOST._protected_producer_transition(candidate,paths,previous,previous,'main'))

    def metadata_transition(self):
        generations={row['name']:row['workflows'] for row in HOST.package_policy().workflow_generations()}
        previous,candidate=copy_git_tree(self.tree),copy_git_tree(self.tree)
        previous.pop('.github/workflows/pr-metadata-context.yml',None)
        previous.update(deepcopy(generations['postmerge-original-e-v1']))
        candidate.update(deepcopy(generations['protected-producer-metadata-ci-v1']))
        paths=sorted(path for path in previous.keys() | candidate.keys() if previous.get(path)!=candidate.get(path))
        return previous,candidate,paths

    def test_exact_metadata_installation_qualifies_all_suites_once_then_returns_to_normal_ci(self):
        previous,candidate,paths=self.metadata_transition()
        self.assertEqual(paths, ['.github/workflows/parent-qualification.yml',
            '.github/workflows/pr-metadata-context.yml', '.github/workflows/project-tests.yml',
            '.github/workflows/repository-checks.yml'])
        result=self.selected(paths,tree=candidate,trusted_tree=previous,base_tree=previous)
        self.assertEqual(result, {'suites':list(self.registry['suites']),
            'reason':'reviewed-protected-producer-transition','full_host':True,'include_platform':True})
        self.assertEqual(len(result['suites']),len(set(result['suites'])))
        changed=copy_git_tree(candidate)
        changed['tests/repository-checks-test.py']={'mode':'100644','type':'blob','sha':'a'*40}
        with patch.object(HOST,'_qt_free_dependency_namespace',return_value=False):
            normal=self.selected(['tests/repository-checks-test.py'],tree=changed,trusted_tree=candidate,base_tree=candidate)
        self.assertEqual(normal['reason'],'reviewed-ci-only-inputs')
        self.assertEqual(set(normal['suites']),self.ci_quick)

    def test_metadata_installation_rejects_missing_mixed_foreign_mode_or_hidden_source_change(self):
        previous,candidate,paths=self.metadata_transition()
        for side in ('base','candidate'):
            for path in paths:
                for mutation in (None,{'mode':'100755','type':'blob','sha':'a'*40},
                                 {'mode':'120000','type':'blob','sha':'a'*40},
                                 {'mode':'100644','type':'blob','sha':'a'*40}):
                    old,new=copy_git_tree(previous),copy_git_tree(candidate)
                    target=old if side=='base' else new
                    if mutation is None: target.pop(path,None)
                    else: target[path]=mutation
                    # The only reviewed missing entry is the newly installed endpoint.
                    if old==previous and new==candidate: continue
                    with self.subTest(side=side,path=path,mutation=mutation):
                        self.assertFalse(HOST._protected_producer_transition(new,paths,old,old,'main'))
        self.assertFalse(HOST._protected_producer_transition(candidate,paths,previous,previous,'apple-ios'))
        self.assertFalse(HOST._protected_producer_transition(candidate,paths+paths[:1],previous,previous,'main'))
        drift=copy_git_tree(candidate)
        drift['tools/test-evidence/producer_workflow.py']={'mode':'100644','type':'blob','sha':'a'*40}
        self.assertFalse(HOST._protected_producer_transition(drift,paths,previous,previous,'main'))
        self.assertFalse(HOST._protected_producer_transition(candidate,paths,previous,candidate,'main'))

    def metadata_joint_transition(self, producer_name="protected-producer-metadata-ci-v1"):
        generations={row['name']:row['workflows'] for row in HOST.package_policy().workflow_generations()}
        previous,candidate=copy_git_tree(self.tree),copy_git_tree(self.tree)
        previous.pop('.github/workflows/pr-metadata-context.yml',None)
        previous.update(deepcopy(generations['android-owned-npm5-sync-ci-v1']))
        candidate.update(deepcopy(generations[producer_name]))
        previous['.github/workflows/codeql.yml']={'mode':'100644','type':'blob',
            'sha':'6d55d0fe4e9edc86204c66e1fa3967681793a2cd'}
        candidate['.github/workflows/codeql.yml']={'mode':'100644','type':'blob',
            'sha':'3a273057a38255ca368d3028594fb94227ba7c3b'}
        paths=sorted(path for path in previous.keys() | candidate.keys() if previous.get(path)!=candidate.get(path))
        return previous,candidate,paths

    def test_actual_legacy_generation_and_pinned_codeql_joint_installation_selects_one_full_owner(self):
        for producer_name in ("protected-producer-metadata-ci-v1", "protected-producer-seven-target-ci-v1"):
            with self.subTest(producer_name=producer_name):
                previous,candidate,paths=self.metadata_joint_transition(producer_name)
                expected=['.github/workflows/codeql.yml','.github/workflows/parent-qualification.yml',
                    '.github/workflows/pr-metadata-context.yml','.github/workflows/project-tests.yml',
                    '.github/workflows/repository-checks.yml']
                self.assertEqual(paths,expected)
                # These literal active identities were independently read from protected
                # 5a9f18be and reviewed967d. Keep this fixture useful after deployment too.
                manifest={g['name']:g['workflows'] for g in HOST.package_policy().workflow_generations()}
                old=manifest['android-owned-npm5-sync-ci-v1']
                self.assertEqual(old['.github/workflows/repository-checks.yml']['sha'],
                                 '55de6bec71c06a6ac4c942098da0b121ef33da2e')
                self.assertEqual(old['.github/workflows/project-tests.yml']['sha'],
                                 'c2e0c310996fa860f9b1418667d05b03b7154e89')
                self.assertEqual(old['.github/workflows/parent-qualification.yml']['sha'],
                                 '6d2d342e4b63d9e60602451157d13854bd52dde7')
                self.assertTrue(all(previous.get(p)==entry for p,entry in old.items()))
                self.assertTrue(all(previous.get(p)==candidate.get(p) for p in previous.keys() | candidate.keys() if p not in expected))
                result=self.selected(paths,tree=candidate,trusted_tree=previous,base_tree=previous)
                self.assertEqual(result,{'suites':list(self.registry['suites']),
                    'reason':'reviewed-protected-producer-transition','full_host':True,'include_platform':True})

    def retained_default_transition(self, source):
        rows={row['name']:row['workflows'] for row in HOST.package_policy().workflow_generations()}
        previous,candidate=copy_git_tree(self.tree),copy_git_tree(self.tree)
        previous.pop('.github/workflows/pr-metadata-context.yml',None)
        previous.update(deepcopy(rows[source]))
        candidate.update(deepcopy(rows['protected-producer-original-default-v1']))
        previous['.github/workflows/codeql.yml']={'mode':'100644','type':'blob',
            'sha':'6d55d0fe4e9edc86204c66e1fa3967681793a2cd'}
        candidate['.github/workflows/codeql.yml']={'mode':'100644','type':'blob',
            'sha':'e9aaaed9693efc5ffb4701697ac2a4d51f5f5ba1'}
        paths=sorted(path for path in previous.keys() | candidate.keys() if previous.get(path)!=candidate.get(path))
        return previous,candidate,paths

    def test_retained_original_default_installation_requires_one_full_owner_from_each_finite_source(self):
        for source in ('npm-consumers-sync-ci-v1','android-owned-npm5-sync-ci-v1'):
            old,new,paths=self.retained_default_transition(source)
            with self.subTest(source=source):
                self.assertEqual(set(paths),{'.github/workflows/'+name+'.yml' for name in (
                    'repository-checks','project-tests','parent-qualification','sync-validation',
                    'pr-metadata-context','codeql')})
                self.assertTrue(HOST._protected_producer_transition(new,paths,old,old,'main'))
                self.assertEqual(self.selected(paths,tree=new,trusted_tree=old,base_tree=old),{
                    'suites':list(self.registry['suites']),'reason':'reviewed-protected-producer-transition',
                    'full_host':True,'include_platform':True})

    def test_retained_original_default_installation_rejects_mixed_or_unbound_sources(self):
        for source in ('npm-consumers-sync-ci-v1','android-owned-npm5-sync-ci-v1'):
            old,new,paths=self.retained_default_transition(source)
            for side in ('base','candidate'):
                for path in paths:
                    for mutation in ('missing','mode','alias','gitlink','unknown'):
                        previous,current=copy_git_tree(old),copy_git_tree(new)
                        tree=previous if side=='base' else current
                        if mutation=='missing':tree.pop(path,None)
                        elif path not in tree:continue
                        elif mutation=='mode':tree[path]['mode']='100755'
                        elif mutation=='alias':tree[path]['mode']='120000'
                        elif mutation=='gitlink':tree[path].update(mode='160000',type='commit')
                        else:tree[path]['sha']='a'*40
                        with self.subTest(source=source,side=side,path=path,mutation=mutation):
                            # Missing helper is the expected legacy state.
                            if side=='base' and path.endswith('/pr-metadata-context.yml') and mutation=='missing':
                                continue
                            self.assertFalse(HOST._protected_producer_transition(current,paths,previous,previous,'main'))
            for target in ('apple-ios','android-main','unknown'):
                self.assertFalse(HOST._protected_producer_transition(new,paths,old,old,target))
            self.assertFalse(HOST._protected_producer_transition(new,paths+paths[:1],old,old,'main'))
            drift=copy_git_tree(new);drift['native.cpp']={'mode':'100644','type':'blob','sha':'a'*40}
            self.assertFalse(HOST._protected_producer_transition(drift,paths,old,old,'main'))
            self.assertFalse(HOST._protected_producer_transition(new,paths,old,new,'main'))
        old,new,paths=self.retained_default_transition('npm-consumers-v1')
        self.assertFalse(HOST._protected_producer_transition(new,paths,old,old,'main'))

    def test_joint_installation_rejects_every_endpoint_mutation_and_unreviewed_combination(self):
        for producer_name in ("protected-producer-metadata-ci-v1", "protected-producer-seven-target-ci-v1"):
            with self.subTest(producer_name=producer_name):
                previous,candidate,paths=self.metadata_joint_transition(producer_name)
                for side in ('base','candidate'):
                    for path in paths:
                        for mutation in (None,{'mode':'100755','type':'blob','sha':'a'*40},
                                {'mode':'120000','type':'blob','sha':'a'*40},
                                {'mode':'160000','type':'commit','sha':'a'*40},
                                {'mode':'100644','type':'blob','sha':'a'*40}):
                            old,new=copy_git_tree(previous),copy_git_tree(candidate)
                            target=old if side=='base' else new
                            if mutation is None:target.pop(path,None)
                            else:target[path]=mutation
                            if old==previous and new==candidate:continue
                            with self.subTest(side=side,path=path,mutation=mutation):
                                self.assertFalse(HOST._protected_producer_transition(new,paths,old,old,'main'))
                for target in ('apple-main','apple-ios','android-main','android-phone','android-vr','android-vr-pico'):
                    self.assertFalse(HOST._protected_producer_transition(candidate,paths,previous,previous,target))
                for changed in (paths[:-1],paths+paths[:1],paths+['.github/branch-cleanup.json']):
                    self.assertFalse(HOST._protected_producer_transition(candidate,changed,previous,previous,'main'))
                hidden=copy_git_tree(candidate)
                hidden['tools/test-evidence/producer_workflow.py']={'mode':'100644','type':'blob','sha':'a'*40}
                self.assertFalse(HOST._protected_producer_transition(hidden,paths,previous,previous,'main'))
                self.assertFalse(HOST._protected_producer_transition(candidate,paths,previous,candidate,'main'))
                # Neither a preexisting metadata source nor an old approved producer
                # tuple may be used to broaden the actual14 joint deployment.
                old=copy_git_tree(previous)
                old['.github/workflows/pr-metadata-context.yml']=candidate['.github/workflows/pr-metadata-context.yml'].copy()
                self.assertFalse(HOST._protected_producer_transition(candidate,paths,old,old,'main'))
                old=copy_git_tree(previous)
                old.update(next(g['workflows'] for g in HOST.package_policy().workflow_generations()
                                if g['name']=='postmerge-original-e-v1'))
                self.assertFalse(HOST._protected_producer_transition(candidate,paths,old,old,'main'))

    def test_producer_transition_requires_main_complete_inventory_and_current_trusted_base(self):
        previous, candidate, paths = self.producer_transition()
        for mutation in ('child', 'unknown', 'nonregular', 'missing-base', 'missing-trusted',
                         'missing-path', 'extra-path', 'duplicate-path', 'trusted-drift'):
            kwargs = {'tree': candidate, 'trusted_tree': previous, 'base_tree': previous}
            changed_paths = paths
            if mutation == 'child': kwargs['target'] = 'apple-ios'
            elif mutation == 'unknown': kwargs['unknown'] = True
            elif mutation == 'nonregular': kwargs['regular'] = False
            elif mutation == 'missing-base': kwargs['base_tree'] = None
            elif mutation == 'missing-trusted': kwargs['trusted_tree'] = {}
            elif mutation == 'missing-path': changed_paths = paths[:1]
            elif mutation == 'extra-path': changed_paths = [*paths, 'docs/producer-transition.md']
            elif mutation == 'duplicate-path': changed_paths = [*paths, paths[0]]
            elif mutation == 'trusted-drift':
                kwargs['trusted_tree'] = copy_git_tree(previous)
                kwargs['trusted_tree']['docs/producer-transition.md'] = {'mode': '100644', 'type': 'blob', 'sha': 'a'*40}
            with self.subTest(mutation=mutation):
                self.assertNotEqual(self.selected(changed_paths, **kwargs)['reason'],
                                    'reviewed-protected-producer-transition')

    def test_producer_transition_rejects_each_modified_missing_nonregular_or_mixed_endpoint(self):
        previous, candidate, paths = self.producer_transition()
        workflows = HOST.package_policy().CONSUMER_WORKFLOW_PATHS
        for side in ('base', 'candidate', 'trusted'):
            for path in workflows:
                for mutation in ('missing', 'modified', 'executable', 'symlink', 'gitlink', 'mixed'):
                    snapshots = {'base': copy_git_tree(previous), 'candidate': copy_git_tree(candidate), 'trusted': copy_git_tree(previous)}
                    snapshot = snapshots[side]
                    if mutation == 'missing': del snapshot[path]
                    elif mutation == 'modified': snapshot[path]['sha'] = 'a'*40
                    elif mutation == 'executable': snapshot[path]['mode'] = '100755'
                    elif mutation == 'symlink': snapshot[path]['mode'] = '120000'
                    elif mutation == 'gitlink': snapshot[path].update(mode='160000', type='commit')
                    else:
                        other = previous if side == 'candidate' else candidate
                        if snapshot[path] == other[path]: continue  # Three sibling endpoints are identical.
                        snapshot[path] = deepcopy(other[path])
                    with self.subTest(side=side, path=path, mutation=mutation):
                        self.assertFalse(HOST._protected_producer_transition(snapshots['candidate'], paths,
                            snapshots['base'], snapshots['trusted'], 'main'))

    def test_producer_transition_cannot_conceal_any_other_tree_change(self):
        previous, candidate, paths = self.producer_transition()
        for path in ('tools/test-evidence/producer_workflow.py', 'tools/repository-checks/host_selection.py',
                     '.github/shared-sandbox.json', '.github/test-suites.json',
                     '.github/package-workflow-generations.json', 'tests/platform-profile.json',
                     'interface/src/Application.cpp', 'docs/producer-transition.md'):
            changed = copy_git_tree(candidate)
            changed[path] = {'mode': '100644', 'type': 'blob', 'sha': 'a'*40}
            with self.subTest(path=path):
                self.assertFalse(HOST._protected_producer_transition(changed, paths, previous, previous, 'main'))

    def test_producer_transition_does_not_accept_another_approved_legacy_tuple(self):
        previous, candidate, paths = self.producer_transition()
        generation = next(g for g in HOST.package_policy().workflow_generations()
                          if g['name'] == 'npm-consumers-metadata-edits-v1')
        previous.update(deepcopy(generation['workflows']))
        self.assertFalse(HOST._protected_producer_transition(candidate, paths, previous, previous, 'main'))

    def test_producer_transition_preserves_the_independent_trusted_reader_review(self):
        previous, candidate, paths = self.producer_transition()
        for snapshot in (previous, candidate):
            snapshot['libraries/shared/src/unreviewed-transition-reader.cpp'] = {
                'mode': '100644', 'type': 'blob', 'sha': 'a'*40}
        result = self.selected(paths, tree=candidate, trusted_tree=previous, base_tree=previous)
        self.assertEqual(result['reason'], 'host-reader-generation-not-reviewed')
        self.assertTrue(result['full_host'])
        self.assertEqual(set(result['suites']), self.all_names)

    def test_ci_changes_after_producer_installation_return_to_the_existing_quick_selection(self):
        _, previous, _ = self.producer_transition()
        candidate = copy_git_tree(previous)
        path = 'tools/branch-cleanup/cleanup.py'
        candidate[path]['sha'] = 'a'*40
        with patch.object(HOST,'_qt_free_dependency_namespace',return_value=False):
            result = self.selected([path], tree=candidate, trusted_tree=previous, base_tree=previous)
        self.assertEqual(set(result['suites']), self.ci_quick)
        self.assertEqual(result['reason'], 'reviewed-ci-only-inputs')
        self.assertFalse(result['full_host'])
        self.assertFalse(result['include_platform'])

    def test_actual_producer_prepare_accepts_the_transition_but_rejects_later_quick_only_selection(self):
        # Immutable Git/API facts are fixtures; this does not qualify execution,
        # runtime admission, source flags, or the native final publisher.
        import producer_workflow as producer
        packages = HOST.package_policy()
        generations={g['name']:g['workflows'] for g in packages.workflow_generations()}
        previous,candidate_tree,paths=self.metadata_joint_transition('protected-producer-seven-target-ci-v1')
        # The event below deliberately models main. Its immutable fixture must
        # retain the shared profile on every branch that executes this test.
        shared=(json.dumps({'schema':1,'platform':'shared','suites':[]},indent=2)+'\n').encode()
        shared_sha=HOST.hashlib.sha1(b'blob '+str(len(shared)).encode()+b'\0'+shared).hexdigest()
        self.assertEqual(shared_sha,'d63537504c20204de9d35d9be61da72a56df59c3')
        for tree in (previous,candidate_tree):
            tree['tests/platform-profile.json']={'mode':'100644','type':'blob','sha':shared_sha}
        self.assertEqual(set(generations['protected-producer-seven-target-ci-v1']),
                         set(packages.METADATA_WORKFLOW_PATHS))
        plan = {'candidate': 'a'*40, 'base': 'd'*40, 'plan': 'c'*64, 'host_mode': 'full',
                'paths': paths, 'regular': True, 'unknown': False}
        repository = {'full_name': 'noah-l-frank/overte', 'id': 1319052603}
        binding = {'pull_request': 17, 'merge_sha': 'a'*40, 'merge_tree': 'b'*40,
                   'merge_parents': ['d'*40, 'e'*40], 'base_ref': 'main', 'base_sha': 'd'*40,
                   'head_ref': 'fix/main/activate-protected-producer', 'head_sha': 'e'*40}
        event = {'repository': repository, 'number': 17, 'pull_request': {'number': 17,
            'base': {'repo': repository, 'ref': 'main', 'sha': 'd'*40},
            'head': {'repo': repository, 'ref': binding['head_ref'], 'sha': 'e'*40}}}
        environment = {'GITHUB_REPOSITORY': repository['full_name'], 'GITHUB_REPOSITORY_ID': '1319052603',
            'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_BASE_REF': 'main',
            'GITHUB_HEAD_REF': binding['head_ref'], 'RUNNER_ENVIRONMENT': 'github-hosted', 'ImageOS': 'ubuntu24',
            'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_REF': 'refs/pull/17/merge', 'GITHUB_RUN_ID': '123',
            'GITHUB_SHA': 'a'*40, 'GITHUB_WORKFLOW_SHA': 'a'*40,
            'GITHUB_WORKFLOW_REF': repository['full_name'] + '/.github/workflows/repository-checks.yml@refs/pull/17/merge'}
        refs = {'default': 'd'*40, 'default_ref': 'main'}
        commits = {'a'*40: ('b'*40, ['d'*40, 'e'*40]), 'd'*40: ('f'*40, ['7'*40]),
                   'e'*40: ('8'*40, ['d'*40])}
        adapter = SimpleNamespace(current=Mock(return_value=(binding, refs)),
            _object=Mock(return_value={'id': 456, 'path': '.github/workflows/repository-checks.yml'}),
            _commit=lambda revision: commits[revision])
        snapshots = {'base': previous, 'candidate': candidate_tree, 'trusted': previous}
        contents = {HOST.hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(): raw
                    for path in (ROOT/'tools/repository-checks/workflows').rglob('*.yml')
                    for raw in (path.read_bytes(),)}
        contents.update(historical_workflows())
        contents[shared_sha]=shared
        policy = SimpleNamespace(validate_wiring=packages.validate_wiring, candidate_plan=Mock(return_value=plan),
            validate_tree_wiring=packages.validate_tree_wiring,
            workflow_generations=packages.workflow_generations, CONSUMER_WORKFLOW_PATHS=packages.CONSUMER_WORKFLOW_PATHS,
            METADATA_WORKFLOW_PATHS=packages.METADATA_WORKFLOW_PATHS)
        with tempfile.TemporaryDirectory(prefix='overte-producer-selection-') as folder:
            candidate, trusted = Path(folder)/'candidate', Path(folder)/'trusted'
            candidate.mkdir()
            trusted.mkdir()
            for path in packages.METADATA_WORKFLOW_PATHS:
                endpoint = candidate/path
                endpoint.parent.mkdir(parents=True, exist_ok=True)
                endpoint.write_bytes(contents[candidate_tree[path]['sha']])
            for path in ('.github/test-suites.json', 'tests/platform-profile.json'):
                endpoint = candidate/path
                endpoint.parent.mkdir(parents=True, exist_ok=True)
                endpoint.write_bytes(contents[candidate_tree[path]['sha']] if path=='tests/platform-profile.json'
                    else HOST.subprocess.check_output([
                        'git', 'cat-file', 'blob', candidate_tree[path]['sha']], cwd=ROOT))
            # program_digest reads the registry by immutable blob identity.
            HOST.subprocess.check_call(['git', 'init', '-q', '--initial-branch=main', str(candidate)])
            HOST.subprocess.check_output(['git', 'hash-object', '-w', '--', '.github/test-suites.json'], cwd=candidate)
            # Exercise the real private immutable Git reader in an ordinary
            # repository. It has no ambient HEAD ref: only the independently
            # validated exact default commit can identify the trusted template.
            for path in (producer.TEMPLATE, '.github/test-suites.json'):
                endpoint = trusted/path
                endpoint.parent.mkdir(parents=True, exist_ok=True)
                endpoint.write_bytes((ROOT/path).read_bytes())
            def trusted_git(*arguments):
                return HOST.subprocess.check_output(['git', '-c', 'commit.gpgsign=false',
                    '-c', 'user.name=Producer selection fixture', '-c', 'user.email=fixture@example.invalid',
                    *arguments], cwd=trusted).decode().strip()
            trusted_git('init', '-q', '--initial-branch=main')
            trusted_git('add', '--', producer.TEMPLATE, '.github/test-suites.json')
            trusted_git('commit', '-qm', 'Create immutable trusted producer template fixture')
            refs['default'] = trusted_git('rev-parse', 'HEAD')
            trusted_git('symbolic-ref', 'HEAD', 'refs/heads/absent')
            def full_tree(root, revision):
                return snapshots['candidate' if revision == 'a'*40 else 'base' if revision == 'd'*40 else 'trusted']
            with patch.object(producer, 'ROOT', trusted), \
                 patch.object(HOST, 'REVIEWED_PROGRAMS', HOST.program_digest(previous)), \
                 patch.object(producer, '_host_policy', return_value=HOST), \
                 patch.object(HOST, 'package_policy', return_value=policy), \
                 patch.object(HOST.inputs, 'full_tree', side_effect=full_tree), \
                 patch.object(HOST.execution, 'checkout_identity', side_effect=lambda root:
                     ('a'*40, 'b'*40) if Path(root) == candidate else (refs['default'], 'f'*40)), \
                 patch.object(producer.sandbox, 'contract', return_value={'digest': 'sha256:'+'5'*64}), \
                 patch.object(producer, 'protected_source_context', return_value={
                     'controller_digest': 'sha256:'+'9'*64, 'fixture': 'independently authenticated source only'}), \
                 patch.object(producer, '_controller_identity', return_value='sha256:'+'9'*64):
                prepared = producer.prepare(candidate, event, environment, adapter)
                self.assertEqual(prepared['selected']['reason'], 'reviewed-protected-producer-transition')
                owner = prepared['plan']['owners']['shared-host']
                self.assertEqual(owner['suites'], list(self.registry['suites']))
                self.assertTrue(owner['include_platform'])
                self.assertEqual(owner['platform'], {})
                self.assertEqual(prepared['run_id'], 123)
                self.assertEqual(prepared['policy'].producer.required_execution_schema, 3)
                self.assertEqual(prepared['policy'].producer.workflow_blob,
                                 candidate_tree['.github/workflows/project-tests.yml']['sha'])
                adapter._object.assert_called_once_with('actions/workflows/repository-checks.yml')
                self.assertEqual(adapter.current.call_count, 2)  # Independent source bookend.
                # Once installed, the same controllers retain the normal CI37
                # route and prepare cannot relabel it as full-host execution.
                snapshots['base'] = snapshots['trusted'] = copy_git_tree(candidate_tree)
                snapshots['candidate'] = copy_git_tree(candidate_tree)
                path = 'tools/branch-cleanup/cleanup.py'
                snapshots['candidate'][path]['sha'] = '9'*40
                plan['paths'] = [path]
                with self.assertRaises(producer.PreExecutionUnavailable):
                    producer.prepare(candidate, event, environment, adapter)
                adapter._object.assert_called_once()

    def package_plan(self, path='browser-client/package-lock.json', *, formatting=False):
        project, profile = HOST.PACKAGE_LOCKS[path]
        return {'base': 'a'*40, 'candidate': 'b'*40, 'tree': 'c'*40,
                'consumer_generation': True, 'paths': [path],
                'package_set': [] if formatting else [project],
                'dependency_profiles': {'unknown': False, 'base': {'revision': 'a'*40},
                    'candidate': {'revision': 'b'*40, 'tree': 'c'*40}, 'projects': {
                        project: {'profile': 'none' if formatting else profile,
                                  'required': not formatting, 'changed_paths': [path],
                                  'reason': 'reviewed-lockfile-format-only' if formatting else
                                      'reviewed-single-dependency-security-update'}}}}

    def test_package_paths_require_complete_matching_independent_owner(self):
        for path in HOST.PACKAGE_LOCKS:
            for formatting in (False, True):
                plan = self.package_plan(path, formatting=formatting)
                self.assertEqual(HOST.package_owned_paths(plan), (path,))
                for mutation in ('generation', 'candidate', 'tree', 'base', 'unknown', 'profile', 'paths', 'owner'):
                    changed = deepcopy(plan)
                    project = HOST.PACKAGE_LOCKS[path][0]
                    profile = changed['dependency_profiles']['projects'][project]
                    if mutation == 'generation': changed['consumer_generation'] = False
                    elif mutation in {'candidate', 'tree', 'base'}: changed[mutation] = 'd'*40
                    elif mutation == 'unknown': changed['dependency_profiles']['unknown'] = True
                    elif mutation == 'profile': profile['profile'] = 'unknown-profile'
                    elif mutation == 'paths': profile['changed_paths'].append(project + '/consumer.js')
                    elif formatting: profile['reason'] = 'unchanged-package-inputs'
                    else: changed['package_set'] = []
                    with self.subTest(path=path, formatting=formatting, mutation=mutation):
                        self.assertEqual(HOST.package_owned_paths(changed), ())

    def test_full_required_javascript_owner_covers_only_its_exact_foreign_lock(self):
        for path,(project,_) in HOST.PACKAGE_LOCKS.items():
            plan=self.package_plan(path)
            profile=plan['dependency_profiles']['projects'][project]
            profile.update(profile='full',reason='unsupported-lockfile-node-change')
            with self.subTest(path=path):
                self.assertEqual(HOST.package_owned_paths(plan),(path,))
                profile['required']=False
                self.assertEqual(HOST.package_owned_paths(plan),())
                profile['required']=True;plan['package_set']=[]
                self.assertEqual(HOST.package_owned_paths(plan),())

    def test_mixed_ci_and_owned_locks_keep_reviewed_production_graph_without_full_host(self):
        paths = tuple(HOST.PACKAGE_LOCKS)
        candidate = copy_git_tree(self.tree)
        for path in paths:
            candidate[path]['sha'] = 'b'*40
        selected = self.selected(['tools/branch-cleanup/cleanup.py', *paths],
                                 tree=candidate, base_tree=self.tree, package_paths=paths)
        self.assertEqual(set(selected['suites']), self.ci_quick)
        self.assertFalse(selected['full_host'])
        self.assertFalse(selected['include_platform'])
        self.assertEqual(selected['package_owned_paths'], sorted(paths))
        self.assertNotIn('results', selected)
        self.assertEqual(HOST.program_digest(candidate), HOST.REVIEWED_PROGRAMS)

    def test_ci_only_after_integrated_npm_update_keeps_the_same_reader_boundary(self):
        reviewed = copy_git_tree(self.tree)
        for path in HOST.PACKAGE_LOCKS:
            reviewed[path]['sha'] = 'a' * 40
        previous = copy_git_tree(self.tree)
        candidate = copy_git_tree(previous)
        changed = 'tools/branch-cleanup/cleanup.py'
        candidate[changed]['sha'] = 'b' * 40
        with patch.object(HOST, 'REVIEWED_PROGRAMS', HOST.program_digest(reviewed)):
            result = self.selected([changed], tree=candidate, base_tree=previous, trusted_tree=reviewed)
        self.assertFalse(result['full_host'])
        self.assertFalse(result['include_platform'])
        self.assertNotIn('package_owned_paths', result)
        # A reader identity is not permission to omit changed package checks.
        for path in HOST.PACKAGE_LOCKS:
            self.assertTrue(self.selected([changed, path], tree=candidate, base_tree=reviewed)['full_host'])
        appium = 'tests/device/ios/package-lock.json'
        drift = copy_git_tree(candidate)
        drift[appium] = {'mode': '100644', 'type': 'blob', 'sha': 'c' * 40}
        self.assertNotEqual(HOST.program_digest(drift), HOST.program_digest(candidate))

    def test_owned_locks_do_not_hide_historical_or_new_product_differences(self):
        path = 'browser-client/package-lock.json'
        for reader in ('tests/platform-profile.json', 'scripts/system/chat.js',
                       'libraries/shared/src/new-package-reader.h'):
            candidate = copy_git_tree(self.tree)
            candidate[path]['sha'] = 'b'*40
            candidate[reader] = {'mode': '100644', 'type': 'blob', 'sha': 'c'*40}
            with self.subTest(reader=reader):
                selected = self.selected(['tools/branch-cleanup/cleanup.py', path], tree=candidate,
                                         base_tree=self.tree, package_paths=(path,))
                self.assertTrue(selected['full_host'])
                self.assertTrue(selected['include_platform'])

    def test_owned_locks_keep_required_changed_control_plane_owner(self):
        path = 'browser-client/package-lock.json'
        candidate = copy_git_tree(self.tree); candidate[path]['sha'] = 'b'*40
        previous = copy_git_tree(self.tree); previous[HOST.CONTROL_PLANE]['sha'] = 'c'*40
        selected = self.selected([HOST.CONTROL_PLANE, path], tree=candidate,
                                 base_tree=previous, package_paths=(path,))
        self.assertEqual(set(selected['suites']), self.ci_quick | {'device-control-plane-full'})
        self.assertTrue(selected['full_host'])
        self.assertFalse(selected['include_platform'])

    def test_owned_locks_require_ordinary_complete_base_inputs_and_regular_inventory(self):
        path = 'browser-client/package-lock.json'
        for mode in ('missing', '100755', '120000', '160000'):
            for side in ('base', 'candidate'):
                candidate, previous = copy_git_tree(self.tree), copy_git_tree(self.tree)
                changed = candidate if side == 'candidate' else previous
                if mode == 'missing': del changed[path]
                else: changed[path] = {'mode': mode, 'type': 'commit' if mode == '160000' else 'blob', 'sha': 'b'*40}
                with self.subTest(mode=mode, side=side):
                    self.assertTrue(self.selected([path], tree=candidate, base_tree=previous,
                                                  package_paths=(path,))['full_host'])
        self.assertTrue(self.selected([path], package_paths=(path,))['full_host'])
        self.assertTrue(self.selected([path], base_tree=self.tree, package_paths=(path,), regular=False)['full_host'])
        with self.assertRaises(ValueError):
            self.selected(['interface/src/Application.cpp'], package_paths=('interface/src/Application.cpp',))

    def test_reviewed_generation_binds_actual_reader_inventory(self):
        tree=copy_git_tree(self.tree)
        del tree['tests/device/contracts/tablet/pages.json']
        self.assertNotEqual(HOST.program_digest(tree), HOST.REVIEWED_PROGRAMS)

    def test_actual_android_reporter_is_not_admitted_as_ci_only(self):
        path = 'android/common/tests/reporting/test_granular_reporters.py'
        self.assertFalse(HOST.ci_owned(path))
        selected = self.selected([path])
        self.assertTrue(selected['full_host'])
        self.assertTrue(selected['include_platform'])
        self.assertEqual(set(selected['suites']), self.all_names)

    def test_finite_ci_executables_have_separate_complete_ordinary_inventory(self):
        previous = copy_git_tree(self.tree)
        paths = sorted(HOST.CI_EXECUTABLE_PATHS)
        for path in paths:
            self.assertEqual(previous[path]['mode'], '100755')
            previous[path]['sha'] = 'b' * 40
        plan = {'unknown': False, 'regular': False, 'paths': paths}
        self.assertTrue(HOST.regular_ci_inventory(plan, previous, self.tree))
        selected = self.selected(paths, regular=False, base_tree=previous)
        self.assertFalse(selected['full_host'])
        self.assertFalse(selected['include_platform'])
        self.assertIn('project-runner', selected['suites'])
        for changes in ({'unknown': True}, {'paths': paths[:-1]}):
            self.assertFalse(HOST.regular_ci_inventory({**plan, **changes}, previous, self.tree))
        self.assertFalse(HOST.regular_ci_inventory(plan, None, self.tree))
        drift = copy_git_tree(previous)
        drift['unowned/input.py'] = {'mode': '100644', 'type': 'blob', 'sha': 'c' * 40}
        self.assertFalse(HOST.regular_ci_inventory(plan, drift, self.tree))
        self.assertTrue(self.selected(paths, regular=False, base_tree=drift)['full_host'])

    def test_ci_executable_waiver_rejects_modes_missing_files_and_unknown_executables(self):
        path = 'tests/project-suite-self-test.py'
        previous = copy_git_tree(self.tree)
        previous[path]['sha'] = 'b' * 40
        plan = {'unknown': False, 'regular': False, 'paths': [path]}
        for side in ('base', 'candidate'):
            for mode in ('missing', '100644', '120000', '160000'):
                base, candidate = copy_git_tree(previous), copy_git_tree(self.tree)
                changed = base if side == 'base' else candidate
                if mode == 'missing':
                    del changed[path]
                else:
                    changed[path]['mode'] = mode
                    changed[path]['type'] = 'commit' if mode == '160000' else 'blob'
                with self.subTest(side=side, mode=mode):
                    self.assertFalse(HOST.regular_ci_inventory(plan, base, candidate))
        for extra in ('tools/branch-cleanup/cleanup.py', 'docs/NEW.md'):
            candidate = copy_git_tree(self.tree)
            candidate[extra] = {'mode': '100755', 'type': 'blob', 'sha': 'c' * 40}
            self.assertFalse(HOST.regular_ci_inventory({**plan, 'paths': [path, extra]}, previous, candidate))

    def test_reviewed_doctor_cli_keeps_its_host_owners_without_product_setup(self):
        path = 'tools/repository-health/check.py'
        previous = copy_git_tree(self.tree)
        self.assertEqual(previous[path]['mode'], '100755')
        previous[path]['sha'] = 'b' * 40
        plan = {'unknown': False, 'regular': False, 'paths': [path]}
        self.assertTrue(HOST.regular_ci_inventory(plan, previous, self.tree))
        selected = self.selected([path], regular=False, base_tree=previous)
        self.assertFalse(selected['full_host'])
        self.assertFalse(selected['include_platform'])
        self.assertIn('repository-doctor', selected['suites'])
        for side in ('base', 'candidate'):
            for mode in ('missing', '100644', '120000', '160000'):
                base, candidate = copy_git_tree(previous), copy_git_tree(self.tree)
                changed = base if side == 'base' else candidate
                if mode == 'missing':
                    del changed[path]
                else:
                    changed[path]['mode'] = mode
                    changed[path]['type'] = 'commit' if mode == '160000' else 'blob'
                with self.subTest(side=side, mode=mode):
                    self.assertFalse(HOST.regular_ci_inventory(plan, base, candidate))
                    self.assertTrue(self.selected([path], regular=False,
                                                 tree=candidate, base_tree=base)['full_host'])
        candidate = copy_git_tree(self.tree)
        extra = 'tools/repository-health/new-executable.py'
        candidate[extra] = {'mode': '100755', 'type': 'blob', 'sha': 'c' * 40}
        self.assertFalse(HOST.regular_ci_inventory(
            {**plan, 'paths': [path, extra]}, previous, candidate))
        self.assertTrue(self.selected([path, extra], regular=False,
                                     tree=candidate, base_tree=previous)['full_host'])

    def test_two_separate_npm_owners_compose_with_the_finite_executable_inventory(self):
        previous, candidate = copy_git_tree(self.tree), copy_git_tree(self.tree)
        executable = 'tests/project-suite-self-test.py'
        previous[executable]['sha'] = 'b' * 40
        plan = self.package_plan()
        for path in HOST.PACKAGE_LOCKS:
            item = self.package_plan(path)
            plan['dependency_profiles']['projects'].update(item['dependency_profiles']['projects'])
            candidate[path]['sha'] = 'c' * 40
        plan.update({'unknown': False, 'regular': False,
                     'paths': [executable, *HOST.PACKAGE_LOCKS],
                     'package_set': [value[0] for value in HOST.PACKAGE_LOCKS.values()]})
        self.assertTrue(HOST.regular_ci_inventory(plan, previous, candidate))
        result = self.selected(plan['paths'], regular=False, tree=candidate, base_tree=previous,
                               package_paths=HOST.package_owned_paths(plan))
        self.assertFalse(result['full_host'])
        self.assertEqual(set(result['package_owned_paths']), set(HOST.PACKAGE_LOCKS))
        plan['package_set'] = []
        self.assertFalse(HOST.regular_ci_inventory(plan, previous, candidate))

    def test_cleanup_and_ci_tests_keep_ci_contracts_and_omit_production_contracts(self):
        for paths in (['tools/branch-cleanup/cleanup.py'], ['tests/branch-cleanup-test.py'],
                      ['tools/branch-cleanup/adoption.py', 'tests/branch-cleanup-test.py',
                       '.github/workflows/branch-cleanup.yml', 'docs/AUTOMATIC_BRANCH_CLEANUP.md'],
                      ['tools/repository-checks/check.py'], ['tests/workflow-contract-test.py'],
                      ['.github/workflows/project-tests.yml'],
                      ['.github/workflows/parent-qualification.yml'],
                      ['.github/workflows/codeql.yml', '.github/codeql/codeql-config.yml'],
                      ['tools/ios-build-qualification/check.py', 'tests/ios-build-qualification-test.py']):
            with self.subTest(paths=paths):
                plan=self.selected(paths)
                self.assertEqual(set(plan['suites']), self.ci_quick)
                self.assertFalse(plan['full_host'])
                self.assertNotIn('device-control-plane-full',plan['suites'])

    def test_eligibility_fixtures_keep_the_required_device_owner(self):
        for path in ('tests/device/self_tests/test_android_adapter.py',
                     'tests/device/self_tests/test_pico_property_eligibility.py'):
            previous = copy_git_tree(self.tree)
            previous[path]['sha'] = 'a' * 40
            with self.subTest(path=path):
                selected = self.selected([path], base_tree=previous)
                self.assertEqual(set(selected['suites']), self.ci_quick | {'device-control-plane-full'})
                self.assertTrue(selected['full_host'])
                self.assertFalse(selected['include_platform'])

    def test_hidden_device_input_changes_cannot_use_the_ci_only_route(self):
        for path in ('tests/device/run_control_plane_tests.py',
                     'tests/device/self_tests/test_android_adapter.py',
                     'tests/device/self_tests/test_pico_property_eligibility.py'):
            previous = copy_git_tree(self.tree)
            previous[path]['sha'] = 'a' * 40
            with self.subTest(path=path):
                selected = self.selected(['tests/branch-cleanup-test.py'], base_tree=previous)
                self.assertEqual(set(selected['suites']), self.ci_quick | {'device-control-plane-full'})
                self.assertTrue(selected['full_host'])
                self.assertFalse(selected['include_platform'])

    def test_device_fixture_ownership_does_not_hide_unreviewed_inputs(self):
        fixture = 'tests/device/self_tests/test_android_adapter.py'
        adjacent = next(path for path in self.tree
                        if path.startswith('tests/device/self_tests/test_')
                        and path not in {fixture, 'tests/device/self_tests/test_pico_property_eligibility.py'})
        for paths, options in (([adjacent], {}),
                               ([fixture, 'libraries/shared/src/SharedUtil.cpp'], {}),
                               ([fixture], {'unknown': True})):
            with self.subTest(paths=paths, options=options):
                self.assertEqual(set(self.selected(paths, **options)['suites']), self.all_names)
        for mode in ('100755', '120000'):
            candidate = copy_git_tree(self.tree)
            candidate[fixture]['mode'] = mode
            with self.subTest(mode=mode):
                selected = self.selected([fixture], tree=candidate, base_tree=self.tree, regular=False)
                self.assertEqual(set(selected['suites']), self.all_names)
        drift = copy_git_tree(self.tree)
        drift['libraries/shared/src/unreviewed-fixture-reader.cpp'] = {
            'mode': '100644', 'type': 'blob', 'sha': 'b' * 40}
        self.assertEqual(set(self.selected([fixture], tree=drift)['suites']), self.all_names)

    def test_exact_owned_inputs_keep_their_declared_host_and_workflow_owners(self):
        expected = {
            '.github/workflows/issue-intake.yml': {'workflow-contracts'},
            'tests/device/contracts/chat/test_chat_qml.py': {'shared-script-behavior'},
            'tests/device/contracts/snapshot/test_snapshot_qml.py': {'snapshot-qml', 'snapshot-native'},
            'tests/device/contracts/snapshot/test_snapshot_native.py': {'snapshot-qml', 'snapshot-native'},
        }
        self.assertEqual({path: set(names) for path, names in HOST.REQUIRED_INPUT_OWNERS.items()}, expected)
        for path, owners in expected.items():
            previous = copy_git_tree(self.tree);previous[path]['sha'] = 'a' * 40
            with self.subTest(path=path):
                selected = self.selected([path], base_tree=previous)
                self.assertEqual(set(selected['suites']), self.ci_quick | owners)
                self.assertEqual(selected['full_host'], any(self.registry['suites'][name]['layer'] == 'host' for name in owners))
                self.assertFalse(selected['include_platform'])
                self.assertNotIn('device-control-plane-full', selected['suites'])
                self.assertEqual(len(selected['suites']), len(set(selected['suites'])))

    def test_hidden_owned_inputs_and_device_deltas_preserve_the_complete_owner_union(self):
        expected = {
            '.github/workflows/issue-intake.yml': {'workflow-contracts'},
            'tests/device/contracts/chat/test_chat_qml.py': {'shared-script-behavior'},
            'tests/device/contracts/snapshot/test_snapshot_qml.py': {'snapshot-qml', 'snapshot-native'},
            'tests/device/contracts/snapshot/test_snapshot_native.py': {'snapshot-qml', 'snapshot-native'},
        }
        for path, owners in expected.items():
            previous = copy_git_tree(self.tree);previous[path]['sha'] = 'b' * 40
            with self.subTest(hidden=path):
                selected = self.selected(['tests/branch-cleanup-test.py'], base_tree=previous)
                self.assertEqual(set(selected['suites']), self.ci_quick | owners)
                self.assertFalse(selected['include_platform'])
        previous = copy_git_tree(self.tree)
        paths = sorted(expected) + ['tests/device/self_tests/test_android_adapter.py']
        for path in paths: previous[path]['sha'] = 'c' * 40
        selected = self.selected(paths, base_tree=previous)
        self.assertEqual(set(selected['suites']), self.ci_quick |
                         {'shared-script-behavior', 'snapshot-qml', 'snapshot-native', 'device-control-plane-full'})
        self.assertTrue(selected['full_host'])
        self.assertFalse(selected['include_platform'])

    def test_affected_subset_cannot_drop_an_independently_required_input_owner(self):
        for path, owners in HOST.REQUIRED_INPUT_OWNERS.items():
            previous = copy_git_tree(self.tree);previous[path]['sha'] = 'a' * 40
            for omitted in owners:
                mandatory = self.ci_quick | set(owners)
                smaller = {'suites': sorted(mandatory - {omitted}),
                    'full_host': False, 'include_platform': False, 'reason': 'protected-affected-dependencies'}
                with self.subTest(path=path, omitted=omitted), \
                        patch.object(HOST, 'affected_selection', return_value=smaller):
                    selected = self.selected([path], base_tree=previous)
                self.assertEqual(set(selected['suites']), mandatory)

    def test_owned_inputs_reject_unknown_missing_modes_neighbors_and_reader_drift(self):
        path = 'tests/device/contracts/chat/test_chat_qml.py'
        for paths, options in (([path], {'unknown': True}),
                ([path, 'tests/device/contracts/chat/test_chat_extra.py'], {}),
                ([path, 'interface/src/Application.cpp'], {})):
            with self.subTest(paths=paths, options=options):
                self.assertEqual(set(self.selected(paths, base_tree=self.tree, **options)['suites']), self.all_names)
        for side in ('base', 'candidate'):
            for defect in ('missing', '100755', '120000', '160000'):
                previous, candidate = copy_git_tree(self.tree), copy_git_tree(self.tree)
                snapshot = previous if side == 'base' else candidate
                if defect == 'missing': snapshot.pop(path)
                else: snapshot[path] = {'mode': defect, 'type': 'commit' if defect == '160000' else 'blob', 'sha': 'a' * 40}
                with self.subTest(side=side, defect=defect):
                    self.assertEqual(set(self.selected(['tests/branch-cleanup-test.py'], tree=candidate,
                        base_tree=previous)['suites']), self.all_names)
        drift = copy_git_tree(self.tree)
        drift['libraries/shared/src/unreviewed-contract-reader.cpp'] = {'mode': '100644', 'type': 'blob', 'sha': 'c' * 40}
        self.assertEqual(set(self.selected([path], tree=drift, base_tree=self.tree)['suites']), self.all_names)
        incomplete = deepcopy(self.registry);del incomplete['suites']['shared-script-behavior']
        with patch.object(HOST.inputs, 'load_registry', return_value=incomplete), self.assertRaisesRegex(ValueError, 'mandatory input owner'):
            self.selected([path], base_tree=self.tree)

    def test_ios_unproved_fixture_readers_keep_device_for_direct_and_hidden_deltas(self):
        paths = ('tests/device/contracts/chat/test_chat_qml.py',
                 'tests/device/contracts/snapshot/test_snapshot_qml.py',
                 'tests/device/contracts/snapshot/test_snapshot_native.py')
        with patch.dict(HOST.REVIEWED_CHILD_PROGRAMS, {'apple-ios': HOST.program_digest(self.tree)}):
            for path in paths:
                previous = copy_git_tree(self.tree);previous[path]['sha'] = 'a' * 40
                owners = set(HOST.REQUIRED_INPUT_OWNERS[path]) | {'device-control-plane-full'}
                for hint in ([path], ['tests/branch-cleanup-test.py']):
                    with self.subTest(path=path, hint=hint):
                        selected = self.selected(hint, base_tree=previous, target='apple-ios')
                        self.assertEqual(set(selected['suites']), self.ci_quick | owners)
                        self.assertTrue(selected['full_host'])
                        self.assertFalse(selected['include_platform'])
                smaller = {'suites': sorted(self.ci_quick | (owners - {'device-control-plane-full'})),
                    'full_host': True, 'include_platform': False, 'reason': 'protected-affected-dependencies'}
                with self.subTest(omission=path), patch.object(HOST, 'affected_selection', return_value=smaller):
                    selected = self.selected([path], base_tree=previous, target='apple-ios')
                self.assertEqual(set(selected['suites']), self.ci_quick | owners)
                self.assertIn('device-control-plane-full', HOST.required_input_owners(
                    self.tree, [path], previous, target='apple-ios'))
                self.assertNotIn('device-control-plane-full', HOST.required_input_owners(
                    self.tree, [path], self.tree, target='apple-ios'))

    def test_ios_fixture_fallback_does_not_broaden_workflow_or_proved_targets(self):
        reviewed = {target: HOST.program_digest(self.tree) for target in HOST.REVIEWED_CHILD_PROGRAMS}
        with patch.dict(HOST.REVIEWED_CHILD_PROGRAMS, reviewed):
            path = '.github/workflows/issue-intake.yml'
            previous = copy_git_tree(self.tree);previous[path]['sha'] = 'b' * 40
            selected = self.selected([path], base_tree=previous, target='apple-ios')
            self.assertEqual(set(selected['suites']), self.ci_quick)
            self.assertFalse(selected['full_host'])
            self.assertNotIn('device-control-plane-full', selected['suites'])
            for target in ('main', 'apple-main', 'android-main', 'android-phone', 'android-vr', 'android-vr-pico'):
                for path, owners in HOST.REQUIRED_INPUT_OWNERS.items():
                    previous = copy_git_tree(self.tree);previous[path]['sha'] = 'c' * 40
                    with self.subTest(target=target, path=path):
                        selected = self.selected([path], base_tree=previous, target=target)
                        self.assertEqual(set(selected['suites']), self.ci_quick | set(owners))
                        self.assertNotIn('device-control-plane-full', selected['suites'])
                        self.assertFalse(selected['include_platform'])
            selected = self.selected(['tests/device/contracts/chat/test_chat_qml.py'],
                                     base_tree=self.tree, target='apple-ios-unknown')
            self.assertEqual(set(selected['suites']), self.all_names)
            self.assertTrue(selected['full_host'])
            self.assertTrue(selected['include_platform'])

    def test_qt_script_contracts_are_required_for_product_changes_and_omitted_for_ci_only(self):
        self.assertEqual(self.registry['suites']['shared-script-behavior']['layer'],'host')
        ci=self.selected(['tools/branch-cleanup/cleanup.py'])
        self.assertNotIn('shared-script-behavior',ci['suites'])
        product=self.selected(['scripts/system/chat.js'])
        self.assertIn('shared-script-behavior',product['suites'])
        self.assertTrue(product['full_host'])

    def test_product_quick_groups_are_omitted_only_with_complete_unchanged_inputs(self):
        ci=self.selected(['tools/branch-cleanup/cleanup.py'])
        self.assertFalse(set(ci['suites']) & HOST.PRODUCT_QUICK_SUITES)
        product=self.selected(['scripts/system/chat.js'])
        self.assertTrue(HOST.PRODUCT_QUICK_SUITES <= set(product['suites']))
        self.assertTrue(product['full_host'])

    def test_unknown_product_setup_shadow_and_mixed_changes_keep_full_host(self):
        for path in ('interface/src/Application.cpp','libraries/audio-client/src/AudioClient.cpp',
                     'tests/device/catalog.json','tests/run-project-tests.py','tests/run-unittest-suite.py',
                     'tests/requirements-host.txt','.github/workflows/unreviewed-host.yml',
                     'tests/json.py','json.py','tests/sitecustomize.py','PhoneLoadingDiagnostics.h',
                     'unknown/data.bin','provenance/artifact_identity.py','tools/sbom/verify-artifact-identity.py',
                     'browser-client/package-lock.json','script-archive/marketplace/S3Server/package-lock.json'):
            with self.subTest(path=path):
                tree=copy_git_tree(self.tree)
                if path == 'tests/run-project-tests.py':
                    tree[path]['sha']='b'*40  # A changed implementation is not an owned-path waiver.
                result=self.selected(['tools/branch-cleanup/cleanup.py',path],tree=tree)
                self.assertTrue(result['full_host'])
                self.assertEqual(set(result['suites']),self.all_names)

    def test_new_reader_historical_child_dependency_or_optional_header_prevents_omission(self):
        for path in ('tests/device/new_reader.py','tests/device/contracts/tablet/pages.json',
                     'libraries/shared/src/new-input.h','interface/resources/qml/new.qml',
                     'scripts/system/new.js','tests/run-unittest-suite.py','tests/platform-profile.json',
                     'domain-server/src/new.h','tools/sbom/new-reader.py',
                     'tests/json.py','tests/json/__init__.py','json.py','json/__init__.py',
                     'PhoneLoadingDiagnostics.h','QCoreApplication'):
            with self.subTest(path=path):
                tree=copy_git_tree(self.tree)
                tree[path]={'mode':'100644','type':'blob','sha':'a'*40}
                result=self.selected(['tools/branch-cleanup/cleanup.py'],tree=tree)
                self.assertTrue(result['full_host'])
                self.assertEqual(result['reason'],'host-reader-generation-not-reviewed')

    def test_changed_trusted_reader_cannot_resume_old_dependency_exclusion(self):
        tree=copy_git_tree(self.tree)
        tree['tests/device/run_control_plane_tests.py']['sha']='b'*40
        result=self.selected(['tools/branch-cleanup/cleanup.py'],trusted_tree=tree)
        self.assertTrue(result['full_host'])

    def test_deleted_reader_and_nonregular_reader_fail_closed(self):
        for mode in ('deleted','100755','120000','160000'):
            for side in ('candidate','trusted'):
                with self.subTest(mode=mode,side=side):
                    tree=copy_git_tree(self.tree);path='tests/device/run_control_plane_tests.py'
                    if mode=='deleted': del tree[path]
                    else: tree[path]={'mode':mode,'type':'commit' if mode=='160000' else 'blob','sha':'a'*40}
                    result=self.selected(['tools/branch-cleanup/cleanup.py'],
                                         tree=tree if side=='candidate' else self.tree,
                                         trusted_tree=tree if side=='trusted' else self.tree)
                    self.assertTrue(result['full_host'])
                    self.assertTrue(result['include_platform'])

    def test_unknown_nonregular_and_empty_inventory_cannot_get_quick_only(self):
        for kwargs in ({'regular':False},{'unknown':True}):
            self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'],**kwargs)['full_host'])
        self.assertTrue(self.selected([])['full_host'])

    def test_staged_workflow_uses_trusted_selection_and_conditions_qt_setup(self):
        import yaml
        path=ROOT/'tools/repository-checks/workflows/host/project-tests.yml'
        d=yaml.safe_load(path.read_text());job=d['jobs']['project-tests'];steps=job['steps']
        self.assertEqual(steps[0]['with']['ref'],'${{ github.event.repository.default_branch }}')
        self.assertEqual(steps[0]['with']['path'],'trusted')
        self.assertEqual(steps[1]['with']['path'],'candidate')
        self.assertTrue(all(s['with']['persist-credentials'] is False for s in steps if 'checkout@' in s.get('uses','')))
        qt=next(s for s in steps if s['name']=='Install QML and portable C++ contract prerequisites')
        self.assertEqual(qt['if'],"steps.host.outputs.full_host == 'true'")
        select=next(s for s in steps if s.get('id')=='host')
        run=next(s for s in steps if s['name']=='Run independently selected host contracts')
        for s in (select,run):
            self.assertIn('trusted/tools/repository-checks/host_selection.py',s['run'])
            self.assertIn('--expected-plan "$EXPECTED_PLAN"',s['run'])
        self.assertEqual(d['permissions'],{'contents':'read'})
        self.assertEqual(d['jobs']['project-results']['if'],'always()')
        self.assertIn('project-tests',d['jobs']['project-results']['needs'])

    def test_new_candidate_tests_are_added_without_replacing_required_commands(self):
        candidate=deepcopy(self.registry)
        original=list(self.registry['suites']['branch-cleanup']['command'])
        candidate['suites']['branch-cleanup']['command'] += ['--new-required-variant']
        candidate['suites']['new-contract']=deepcopy(candidate['suites']['branch-cleanup'])
        candidate['suites']['new-contract']['command']=['python','tests/new-contract.py']
        extra=HOST.additional_suites(candidate,self.registry)
        self.assertEqual(len(extra),2)
        self.assertEqual(self.registry['suites']['branch-cleanup']['command'],original)
        self.assertIn('branch-cleanup',self.ci_quick)
        self.assertTrue(any(command==original+['--new-required-variant'] for _,_,command in extra))
        self.assertTrue(any(command==['python','tests/new-contract.py'] for _,_,command in extra))

    def test_duplicate_candidate_aliases_execute_the_same_command_context_at_most_once(self):
        candidate=deepcopy(self.registry)
        candidate['suites']['alias']=deepcopy(candidate['suites']['branch-cleanup'])
        self.assertEqual(HOST.additional_suites(candidate,self.registry),[])
        candidate['suites']['alias']['command']=['python','tests/new-contract.py']
        candidate['suites']['second-alias']=deepcopy(candidate['suites']['alias'])
        self.assertEqual(len(HOST.additional_suites(candidate,self.registry)),1)

    def test_new_unsupported_test_context_cannot_get_a_successful_partial_gate(self):
        for field,value in (('environment','unreviewed-sdk'),('command',['unreviewed-executable','test'])):
            candidate=deepcopy(self.registry)
            candidate['suites']['new-contract']=deepcopy(candidate['suites']['branch-cleanup'])
            candidate['suites']['new-contract'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                HOST.additional_suites(candidate,self.registry)

    def test_six_child_graphs_are_target_specific_and_initial_launcher_owner_is_required(self):
        targets=set(HOST.REVIEWED_CHILD_PROGRAMS)
        self.assertEqual(targets,{'apple-main','apple-ios','android-main','android-phone','android-vr','android-vr-pico'})
        # Genuine full parent integration brings the common reporter fix to VR;
        # its product reader graph then equals Android-main's graph. Contextual
        # execution/provenance still belongs to each independently checked target.
        self.assertEqual(HOST.REVIEWED_CHILD_PROGRAMS['android-main'], HOST.REVIEWED_CHILD_PROGRAMS['android-vr'])
        self.assertEqual(len(set(HOST.REVIEWED_CHILD_PROGRAMS.values())),5)
        # Portable graph fixtures do not require historical objects in shallow CI.
        # The six actual immutable topic trees are separately checked locally.
        for index,target in enumerate(sorted(targets)):
            with self.subTest(target=target):
                child=copy_git_tree(self.tree)
                child['tests/platform-profile.json']['sha']=str(index+1)*40
                digest=HOST.program_digest(child)
                previous=copy_git_tree(child);previous[HOST.CONTROL_PLANE]['sha']='a'*40
                with patch.dict(HOST.REVIEWED_CHILD_PROGRAMS,{target:digest}):
                    initial=self.selected([HOST.CONTROL_PLANE,'tools/branch-cleanup/cleanup.py'],
                                          tree=child,target=target,base_tree=previous)
                    self.assertEqual(set(initial['suites']),self.ci_quick|{'device-control-plane-full'})
                    self.assertTrue(initial['full_host'])
                    self.assertFalse(initial['include_platform'])
                    later=self.selected(['tools/branch-cleanup/cleanup.py'],tree=child,target=target,base_tree=child)
                    self.assertEqual(set(later['suites']),self.ci_quick)
                    self.assertFalse(later['full_host'])
                    self.assertFalse(later['include_platform'])
                    self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'],tree=child,target='main')['include_platform'])

    def test_only_explicitly_reviewed_predecessor_reader_generations_remain_compatible(self):
        previous = copy_git_tree(self.tree)
        previous['tools/test-evidence/validate-sync.py']['sha'] = 'b' * 40
        with patch.dict(HOST.REVIEWED_PREDECESSORS, {'main': HOST.program_digest(previous)}):
            selected = self.selected(['tools/branch-cleanup/cleanup.py'], tree=previous)
            self.assertFalse(selected['full_host'])
            changed = copy_git_tree(previous)
            changed['libraries/shared/src/new-reader.cpp'] = {'mode': '100644', 'type': 'blob', 'sha': 'c' * 40}
            self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'], tree=changed)['full_host'])

    def test_immutable_launcher_difference_requires_owner_even_without_caller_path_hint(self):
        previous=copy_git_tree(self.tree);previous[HOST.CONTROL_PLANE]['sha']='b'*40
        selected=self.selected(['tools/branch-cleanup/cleanup.py'],base_tree=previous)
        self.assertIn('device-control-plane-full',selected['suites'])
        self.assertTrue(selected['full_host'])

    def test_exact_ci_admissions_do_not_waive_neighboring_tests_or_runtime_readers(self):
        self.assertEqual(len(HOST.CI_ROLLOUT_PATHS),57)
        self.assertIn('tools/test-evidence/affected-test.py',HOST.CI_ROLLOUT_PATHS)
        self.assertIn('.github/workflows/pr-metadata-context.yml',HOST.CI_ROLLOUT_PATHS)
        self.assertIn('.github/workflows/documentation-push-owner.yml',HOST.CI_ROLLOUT_PATHS)
        for path in ('.github/workflows/documentation-checks.yml','.github/workflows/workflow-security.yml'):
            self.assertIn(path,HOST.CI_ROLLOUT_PATHS)
            self.assertTrue(HOST.ci_owned(path))
            self.assertFalse(HOST.ci_owned(path.replace('.yml','-extra.yml')))
        self.assertIn('tools/test-evidence/source_admission.py',HOST.CI_ROLLOUT_PATHS)
        self.assertIn('tools/test-evidence/source-admission-test.py',HOST.CI_ROLLOUT_PATHS)
        self.assertFalse(HOST.ci_owned('tools/test-evidence/source_admission_other.py'))
        for path in ('tools/test-evidence/new-reader.py','tools/test-evidence/postmerge_extra.py',
                     'tools/test-evidence/runtime_ci_extra.py', '.github/ci37-runtime-extra.json',
                     'tests/project-suite-self-test-extra.py',
                     '.github/workflows/repository-checks-extra.yml',
                     '.github/workflows/pr-metadata-context-extra.yml'):
            self.assertTrue(self.selected([path])['include_platform'],path)
        for path in ('tests/run-project-tests.py','tools/test-evidence/execution.py',
                     'tools/test-evidence/inputs.py','tools/test-evidence/validate-sync.py'):
            changed=copy_git_tree(self.tree);changed[path]['sha']='b'*40
            self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'],tree=changed)['include_platform'],path)

    def test_legacy_reviewed_ci37_route_never_loads_the_ineligible_full_setup_graph(self):
        path='tools/branch-cleanup/cleanup.py'
        candidate=copy_git_tree(self.tree);candidate[path]['sha']='b'*40
        options={'tree':candidate,'base_tree':self.tree,'trusted_tree':self.tree}
        with patch.object(HOST,'_qt_free_dependency_namespace',return_value=False), \
                patch.object(HOST.inputs,'load_dependencies',side_effect=AssertionError('no graph read')), \
                patch.object(HOST.inputs,'plan_affected',side_effect=AssertionError('no graph/tree hashing')), \
                patch.object(HOST,'affected_selection',wraps=HOST.affected_selection) as graph:
            selected=self.selected([path],**options)
        self.assertEqual(set(selected['suites']),self.ci_quick)
        self.assertFalse(selected['full_host']);self.assertFalse(selected['include_platform'])
        self.assertEqual(graph.call_count,1)
        self.assertIs(graph.call_args.kwargs['allow_full_host'],False)

    def test_fixed_boundary_controls_keep_their_owners_and_exact_controller_generation(self):
        paths = ('.github/shared-sandbox.json', '.github/workflows/shared-sandbox-host-diagnostic.yml',
                 'tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml',
                 'tools/test-evidence/sandbox-test.py', 'tools/test-evidence/sandbox-host-test.py',
                 'tools/test-evidence/sandbox.py', 'tools/test-evidence/sandbox_host.py',
                 'tools/test-evidence/sandbox_host_fixture.py', 'tools/test-evidence/sandbox_probe.py',
                 'tools/test-evidence/sandbox_shared.py',
                 'tools/test-evidence/producer_workflow.py', 'tools/test-evidence/postmerge.py',
                 '.github/ci37-runtime.json', 'tools/test-evidence/ci_profile.py',
                 'tools/test-evidence/ci-profile-test.py', 'tools/test-evidence/runtime_ci.py',
                 'tools/test-evidence/runtime-ci-test.py', 'tools/test-evidence/ci-integration-test.py',
                 'tools/repository-checks/workflows/producers/protected-project-tests.yml',
                 'tools/repository-checks/workflows/producers/repository-checks.yml',
                 'tools/repository-checks/workflows/producers/parent-qualification.yml',
                 'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml',
                 'tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml')
        selected = self.selected(paths)
        self.assertEqual(set(selected['suites']), self.ci_quick)
        self.assertFalse(selected['include_platform'])
        self.assertIn('test-evidence', selected['suites'])
        for path in ('.github/shared-sandbox.json', 'tools/test-evidence/sandbox.py',
                     'tools/test-evidence/sandbox_host.py', 'tools/test-evidence/sandbox_host_fixture.py',
                     'tools/test-evidence/sandbox_probe.py', 'tools/test-evidence/sandbox_shared.py',
                     'tools/test-evidence/producer_workflow.py', 'tools/test-evidence/postmerge.py',
                     'tools/test-evidence/ci_profile.py',
                     'tools/test-evidence/runtime_ci.py',
                     'tools/repository-checks/workflows/producers/protected-project-tests.yml',
                     'tools/repository-checks/workflows/producers/repository-checks.yml',
                     'tools/repository-checks/workflows/producers/parent-qualification.yml',
                     'tools/repository-checks/workflows/producers/protected-project-tests-android-platform.yml',
                     'tools/repository-checks/workflows/producers/parent-qualification-android-platform.yml'):
            candidate = copy_git_tree(self.tree)
            candidate[path] = {'mode': '100644', 'type': 'blob', 'sha': 'b' * 40}
            with self.subTest(controller=path):
                self.assertTrue(self.selected(paths, tree=candidate)['include_platform'])
        for path in ('tools/test-evidence/sandbox_extra.py',
                     '.github/workflows/shared-sandbox-host-diagnostic-extra.yml'):
            with self.subTest(unknown=path):
                self.assertTrue(self.selected([path])['include_platform'])

    def test_both_consumed_platform_readmes_and_optional_membership_remain_bound(self):
        reviewed=copy_git_tree(self.tree)
        docs=('android/vr/common/openxr/README.md','android/phone/device-tests/parity/fixtures/README.md')
        for path in docs:
            reviewed[path]={'mode':'100644','type':'blob','sha':'a'*40}
        with patch.object(HOST,'REVIEWED_PROGRAMS',HOST.program_digest(reviewed)):
            for path in (*docs,'tests/platform-profile.json','libraries/shared/src/PhoneLoadingDiagnostics.h',
                         'tests/json.py','tests/json/__init__.py','json.py','json/__init__.py'):
                for side in ('candidate','trusted'):
                    with self.subTest(path=path,side=side):
                        changed=copy_git_tree(reviewed)
                        changed[path]={'mode':'100644','type':'blob','sha':'b'*40}
                        result=self.selected(['tools/branch-cleanup/cleanup.py'],
                                             tree=changed if side=='candidate' else reviewed,
                                             trusted_tree=changed if side=='trusted' else reviewed)
                        self.assertEqual(set(result['suites']),self.all_names)
                        self.assertTrue(result['include_platform'])
            for path in docs:
                for mode in ('deleted','100755','120000','160000','rename'):
                    changed=copy_git_tree(reviewed)
                    if mode=='deleted':del changed[path]
                    elif mode=='rename':changed[path+'.new']=changed.pop(path)
                    else:changed[path]={'mode':mode,'type':'commit' if mode=='160000' else 'blob','sha':'a'*40}
                    self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'],tree=changed,
                                                  trusted_tree=reviewed)['include_platform'],(path,mode))

    def test_excluded_ci_symlink_or_gitlink_cannot_get_partial_verification(self):
        for mode in ('120000','160000'):
            for side in ('candidate','trusted'):
                changed=copy_git_tree(self.tree)
                changed['tools/branch-cleanup/cleanup.py']={'mode':mode,'type':'commit' if mode=='160000' else 'blob','sha':'a'*40}
                result=self.selected(['tests/branch-cleanup-test.py'],
                                     tree=changed if side=='candidate' else self.tree,
                                     trusted_tree=changed if side=='trusted' else self.tree)
                self.assertTrue(result['include_platform'])

    def test_target_comes_from_server_base_or_push_ref_not_head_branch(self):
        self.assertEqual(HOST.target_branch({'pull_request':{'base':{'ref':'apple-ios'},'head':{'ref':'main'}}}),'apple-ios')
        self.assertEqual(HOST.target_branch({'ref':'refs/heads/android-phone'}),'android-phone')
        self.assertIsNone(HOST.target_branch({'ref':'refs/tags/main'}))
        self.assertTrue(self.selected(['tools/branch-cleanup/cleanup.py'],target='unknown')['include_platform'])

    def cli(self, runner_result=0, expected='c'*64, cancel=False, new_command=False,
            select_only=False, full_host=False, control_changed=False, platform=False, transition=False):
        plan={'candidate':'a'*40,'plan':'c'*64,'host_mode':'full',
              'paths':(['interface/src/Application.cpp'] if full_host else
                       [HOST.CONTROL_PLANE] if control_changed else ['tools/branch-cleanup/cleanup.py']),
              'regular':True,'unknown':False}
        previous, candidate = self.tree, self.tree
        package_policy = HOST.package_policy()
        if transition:
            previous, candidate, plan['paths'] = (self.metadata_joint_transition('protected-producer-seven-target-ci-v1' if transition == 'seven-joint' else 'protected-producer-metadata-ci-v1') if transition in ('metadata-joint', 'seven-joint')
                else self.metadata_transition() if transition == 'metadata' else self.producer_transition())
            plan['base'] = 'd'*40
        proposed=deepcopy(self.registry)
        if new_command:
            proposed['suites']['new-host-contract']=deepcopy(proposed['suites']['branch-cleanup'])
            proposed['suites']['new-host-contract']['layer']='host'
            proposed['suites']['new-host-contract']['command']=['python','tests/new-required-host-contract.py']
        policy=SimpleNamespace(validate_wiring=Mock(),candidate_plan=Mock(return_value=plan),
            workflow_generations=package_policy.workflow_generations,
            CONSUMER_WORKFLOW_PATHS=package_policy.CONSUMER_WORKFLOW_PATHS,
            METADATA_WORKFLOW_PATHS=package_policy.METADATA_WORKFLOW_PATHS)
        def run(args,suites,cancelled):
            if new_command or full_host or transition:
                self.assertTrue(self.all_names <= {suite[0] for suite in suites})
                if platform:
                    self.assertIn('fixture-platform',{suite[0] for suite in suites})
                if new_command:
                    self.assertEqual(sum(command[-1]=='tests/new-required-host-contract.py' for _,_,command in suites),1)
            else:
                expected_names=self.ci_quick | ({'device-control-plane-full'} if control_changed else set())
                self.assertEqual({suite[0] for suite in suites},expected_names)
                self.assertEqual(args.host_timeout,900)
                if control_changed:
                    command=next(command for name,_,command in suites if name=='device-control-plane-full')
                    self.assertIn('--require-qml',command)
            if cancel:
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM,None)
                self.assertEqual(cancelled,[signal.SIGTERM])
            return runner_result
        controller=SimpleNamespace(Suite=lambda *args:args,run_suites=Mock(side_effect=run))
        with tempfile.TemporaryDirectory() as folder:
            event=Path(folder)/'event.json';event.write_text('{"ref":"refs/heads/main"}')
            argv=['host_selection.py','--candidate',str(ROOT),'--event',str(event),'--sha','a'*40,
                  '--expected-plan',expected,'--junit',str(Path(folder)/'result.xml')]
            output=Path(folder)/'selection.txt'
            report=Path(folder)/'selection.json'
            argv += ['--selection-report',str(report)]
            if select_only:
                argv += ['--select-only','--output',str(output)]
            before=signal.getsignal(signal.SIGTERM)
            with patch.object(sys,'argv',argv),patch.object(HOST,'package_policy',return_value=policy), \
                 patch.object(HOST.execution,'_runner',return_value=controller), \
                 patch.object(HOST.execution,'checkout_identity',return_value=('a'*40,'b'*40)), \
                 patch.object(HOST.inputs,'full_tree',side_effect=lambda root, revision:
                     candidate if revision == 'a'*40 else previous), \
                 patch.object(HOST.execution,'platform_suites',return_value=(
                     [('fixture-platform',['python','tests/fixture-platform.py'])] if platform else [])), \
                 patch.object(HOST,'candidate_registry',return_value=proposed), \
                 contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                result=HOST.main()
            controller.selection_output=output.read_text() if output.exists() else None
            controller.selection_report=json.loads(report.read_text()) if report.exists() else None
            self.assertIs(signal.getsignal(signal.SIGTERM),before)
        return result,controller

    def test_producer_transition_cli_requests_full_prerequisites_and_runs_one_complete_owner(self):
        result, controller = self.cli(transition=True, select_only=True)
        self.assertEqual(result, 0)
        self.assertEqual(controller.selection_output, 'full_host=true\ncomplete_receipt=true\n')
        self.assertEqual(controller.selection_report['selection']['reason'], 'reviewed-protected-producer-transition')
        self.assertEqual(controller.selection_report['omitted_suites'], [])
        controller.run_suites.assert_not_called()
        result, controller = self.cli(transition=True)
        self.assertEqual(result, 0)
        controller.run_suites.assert_called_once()
        suites = controller.run_suites.call_args.args[1]
        self.assertEqual([suite[0] for suite in suites], list(self.registry['suites']))

    def test_metadata_installation_cli_selects_full_prerequisites_and_one_complete_owner(self):
        result,controller=self.cli(transition='metadata',select_only=True)
        self.assertEqual(result,0)
        self.assertEqual(controller.selection_output,'full_host=true\ncomplete_receipt=true\n')
        self.assertEqual(controller.selection_report['selection']['reason'],'reviewed-protected-producer-transition')
        self.assertEqual(controller.selection_report['omitted_suites'],[])
        controller.run_suites.assert_not_called()
        result,controller=self.cli(transition='metadata')
        self.assertEqual(result,0)
        controller.run_suites.assert_called_once()
        self.assertEqual([suite[0] for suite in controller.run_suites.call_args.args[1]],list(self.registry['suites']))

    def test_joint_metadata_codeql_installation_cli_qualifies_one_complete_owner(self):
        for transition in ("metadata-joint", "seven-joint"):
            with self.subTest(transition=transition):
                result,controller=self.cli(transition=transition,select_only=True)
                self.assertEqual(result,0)
                self.assertEqual(controller.selection_output,'full_host=true\ncomplete_receipt=true\n')
                self.assertEqual(controller.selection_report['selection']['reason'],'reviewed-protected-producer-transition')
                self.assertEqual(controller.selection_report['omitted_suites'],[])
                controller.run_suites.assert_not_called()
                result,controller=self.cli(transition=transition)
                self.assertEqual(result,0)
                controller.run_suites.assert_called_once()
                self.assertEqual([suite[0] for suite in controller.run_suites.call_args.args[1]],list(self.registry['suites']))
    def test_new_candidate_host_command_forces_prerequisites_before_execution(self):
        result,controller=self.cli(new_command=True,select_only=True)
        self.assertEqual(result,0)
        self.assertEqual(controller.selection_output,'full_host=true\ncomplete_receipt=false\n')
        self.assertFalse(controller.selection_report['complete_receipt_required'])
        controller.run_suites.assert_not_called()

    def test_partial_host_owner_keeps_qt_without_claiming_full_receipt(self):
        result,controller=self.cli(control_changed=True,select_only=True,platform=True)
        self.assertEqual(result,0)
        self.assertEqual(controller.selection_output,'full_host=true\ncomplete_receipt=false\n')
        report=controller.selection_report
        self.assertFalse(report['complete_receipt_required'])
        self.assertFalse(report['reusable'])
        self.assertEqual(set(report['selection']['suites']),self.ci_quick|{'device-control-plane-full'})
        self.assertEqual(report['selection']['platform_suites'],[])
        self.assertEqual(report['selection']['omitted_platform_suites'],['fixture-platform'])
        controller.run_suites.assert_not_called()

    def test_partial_host_owner_failure_blocks_and_unchanged_platform_is_not_executed(self):
        result,controller=self.cli(control_changed=True,platform=True,runner_result=1)
        self.assertEqual(result,1)
        controller.run_suites.assert_called_once()

    def test_real_runner_preserves_qml_requirement_900_seconds_and_host_failure(self):
        runner=HOST.execution._runner()
        command=tuple(self.registry['suites']['device-control-plane-full']['command'])
        suite=runner.Suite('device-control-plane-full','host',command)
        args=SimpleNamespace(timeout=240,host_timeout=900,native_build_dir=None,junit=None,fail_fast=False)
        with patch.object(runner,'run_command',return_value=(1,'fake selected host failure','')) as execute, \
             contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            status=runner.run_suites(args,[suite],[])
        self.assertEqual(status,1)
        actual,timeout,cancelled=execute.call_args.args
        self.assertIn('--require-qml',actual)
        self.assertEqual(actual[-2:],['--timeout-seconds','900'])
        self.assertEqual(timeout,900)
        self.assertEqual(cancelled,[])

    def test_full_fallback_executes_declared_platform_instead_of_waiving_it(self):
        result,controller=self.cli(full_host=True,platform=True)
        self.assertEqual(result,0)
        self.assertEqual(controller.selection_report['selection']['platform_suites'],['fixture-platform'])
        self.assertEqual(controller.selection_report['selection']['omitted_platform_suites'],[])

    def test_partial_parent_plan_cannot_claim_full_or_reused_execution(self):
        result,controller=self.cli(select_only=True)
        self.assertEqual(result,0)
        self.assertEqual(controller.selection_output,'full_host=false\ncomplete_receipt=false\n')
        report=controller.selection_report
        self.assertFalse(report['reusable'])
        self.assertEqual(report['kind'],'host-impact-selection')
        self.assertEqual(report['candidate'],'a'*40)
        self.assertEqual(set(report['selection']['suites']),self.ci_quick)
        self.assertEqual(set(report['omitted_suites']),self.all_names-self.ci_quick)
        self.assertNotIn('results',report)
        controller.run_suites.assert_not_called()

    def test_product_parent_plan_keeps_legacy_complete_receipt_route(self):
        result,controller=self.cli(select_only=True,full_host=True)
        self.assertEqual(result,0)
        self.assertEqual(controller.selection_output,'full_host=true\ncomplete_receipt=true\n')
        self.assertTrue(controller.selection_report['complete_receipt_required'])
        self.assertEqual(controller.selection_report['omitted_suites'],[])
        controller.run_suites.assert_not_called()

    def test_parent_template_keeps_full_receipts_separate_from_partial_execution(self):
        import yaml
        path=ROOT/'tools/repository-checks/workflows/host/parent-qualification.yml'
        steps=yaml.safe_load(path.read_text())['jobs']['qualify-parent']['steps']
        selection=next(s for s in steps if s.get('id')=='host')
        qt=next(s for s in steps if s['name']=='Install QML and portable C++ contract prerequisites')
        full=next(s for s in steps if s['name']=='Run complete host qualification')
        partial=next(s for s in steps if s['name']=='Run independently selected parent host contracts')
        self.assertLess(steps.index(selection),steps.index(qt))
        self.assertEqual(qt['if'],"steps.host.outputs.full_host == 'true'")
        self.assertEqual(full['if'],"steps.host.outputs.complete_receipt == 'true'")
        self.assertIn("steps.host.outputs.complete_receipt == 'false'",partial['if'])
        self.assertIn('trusted/tools/test-evidence/run.py',full['run'])
        self.assertIn('trusted/tools/repository-checks/host_selection.py',partial['run'])
        for name in ('Create content-addressed qualification evidence','Upload immutable qualification evidence'):
            step=next(s for s in steps if s['name']==name)
            self.assertEqual(step['if'],"steps.host.outputs.complete_receipt == 'true'")
        upload=next(s for s in steps if s['name']=='Upload qualification test reports')
        self.assertIn('host-selection.json',upload['with']['path'])
        self.assertIn("always()",upload['if'])
        generation=next(g for g in HOST.package_policy().workflow_generations() if g['name']=='parent-host-impact-v1')
        import hashlib
        raw=path.read_bytes()
        expected=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        self.assertEqual(generation['workflows']['.github/workflows/parent-qualification.yml']['sha'],expected)

    def test_parent_impact_report_cannot_replace_full_sync_qualification(self):
        source=ROOT/'tools/test-evidence/validate-sync-test.py'
        spec=importlib.util.spec_from_file_location('parent_sync_consumer_fixture',source)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        case=module.IsolatedConsumerTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        gate=module.VALIDATION._gate()
        diagnostic={'schema':1,'kind':'host-impact-selection','reusable':False,
                    'candidate':case.parent,'tree':case.tree_sha,
                    'selection':{'suites':['alpha'],'full_host':False},'omitted_suites':['beta']}
        request=SimpleNamespace(repository='noah-l-frank/overte',repository_id=1319052603,
                                parent='main',parent_sha=case.parent)
        def verify(*arguments):
            with patch.object(gate,'artifact_evidence',return_value=({},diagnostic)):
                try:
                    return gate.verify_evidence(object(),{},request)
                except gate.EvidenceError as error:
                    self.assertIn('mismatched schema',str(error))
                    raise
        case.gate.verify_evidence=verify
        case.gate.EvidenceError=gate.EvidenceError
        result=case.validate()
        self.assertEqual(result['mode'],'fallback')
        self.assertEqual(result['reused_suites'],[])
        self.assertEqual(set(case.executed()),{'alpha','beta'})
        self.assertTrue(result['execution']['include_platform'])

    def test_parent_execution_route_rejects_missing_or_contradictory_outputs(self):
        import yaml
        import subprocess
        path=ROOT/'tools/repository-checks/workflows/host/parent-qualification.yml'
        steps=yaml.safe_load(path.read_text())['jobs']['qualify-parent']['steps']
        check=next(s for s in steps if s['name']=='Require a complete host execution route')
        select=next(s for s in steps if s.get('id')=='host')
        qt=next(s for s in steps if s['name']=='Install QML and portable C++ contract prerequisites')
        self.assertLess(steps.index(select),steps.index(check))
        self.assertLess(steps.index(check),steps.index(qt))
        for full in ('true','false','','unknown'):
            for complete in ('true','false','','unknown'):
                actual=subprocess.run(['/bin/bash','-c',check['run']],capture_output=True,
                                      env={'FULL_HOST':full,'COMPLETE_RECEIPT':complete})
                self.assertEqual(actual.returncode==0,(full,complete) in {
                    ('true','true'),('true','false'),('false','false')},(full,complete))

    def test_new_candidate_command_is_required_and_failure_blocks_merging(self):
        result,controller=self.cli(new_command=True,runner_result=1)
        self.assertEqual(result,1)
        controller.run_suites.assert_called_once()

    def test_cli_rejects_mismatched_candidate_plan_before_executing_any_command(self):
        result,controller=self.cli(expected='d'*64)
        self.assertEqual(result,1)
        self.assertIsNone(controller.selection_report)
        controller.run_suites.assert_not_called()

    def test_cli_propagates_selected_suite_failure_instead_of_publishing_success(self):
        result,controller=self.cli(runner_result=7)
        self.assertEqual(result,7)
        controller.run_suites.assert_called_once()

    def test_cli_cancellation_is_forwarded_and_signal_handler_restored(self):
        result,controller=self.cli(runner_result=143,cancel=True)
        self.assertEqual(result,143)
        controller.run_suites.assert_called_once()


if __name__=='__main__':
    unittest.main()
