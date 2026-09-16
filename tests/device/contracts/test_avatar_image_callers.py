#!/usr/bin/env python3
"""Original four image caller subtrees with real RoundImage and original import bases."""
import os,pathlib,re,shlex,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[3]
class Callers(unittest.TestCase):
 def test_actual_image_callers(self):
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Test'],text=True))
  cases=[('NameCard.qml','userImage'),('simplifiedUI/avatarApp/components/DisplayNameHeader.qml','itemPreviewImage'),('simplifiedUI/avatarApp/components/AvatarAppListDelegate.qml','itemPreviewImage'),('simplifiedUI/topBar/SimplifiedTopBar.qml','avatarButtonImage')]
  with tempfile.TemporaryDirectory(prefix='avatar-callers-') as d:
   d=pathlib.Path(d);binary=d/'test';subprocess.run(['c++','-std=c++17','-fPIC',str(pathlib.Path(__file__).with_name('avatar-image-callers-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
   for name,ident in cases:
    path=ROOT/'interface/resources/qml/hifi'/name;s=path.read_text();imp=next(l for l in s.splitlines() if l.endswith(' as AvatarImages'));a=s.rfind('AvatarImages.RoundImage {',0,s.index('id: '+ident));i=s.index('{',a)+1;depth=1
    while depth:depth+=(s[i]=='{')-(s[i]=='}');i+=1
    body=s[a:i].replace('AvatarImages.RoundImage {','AvatarImages.RoundImage { objectName: "actualImage"',1)
    extra=''
    if ident=='avatarButtonImage':
     extra='property var topBarInventoryModel: ({count: 0})\n'
     for method in ['updatePreviewUrl','fromScript']:
      a=s.index('function '+method+'(');i=s.index('{',a)+1;depth=1
      while depth:depth+=(s[i]=='{')-(s[i]=='}');i+=1
      extra+=s[a:i]+'\n'
    qml=d/'caller.qml';qml.write_text('import QtQuick 2.5\n'+imp+'\nItem { id: root; width:128; height:128\nproperty bool loading: false\nproperty string profileUrl: "image://fixture/profile"\nproperty string previewUrl: profileUrl\nproperty string itemPreviewImageUrl: profileUrl\n'+body+'\n'+extra+'\n}')
    with self.subTest(name=name):subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),str(qml),str(path)],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'),check=True,timeout=10)
if __name__=='__main__':unittest.main()
