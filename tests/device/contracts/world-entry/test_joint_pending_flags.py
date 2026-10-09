"""Compile production joint mutators and check their parallel-vector invariant."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


def definition(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class JointPendingFlagsTest(unittest.TestCase):
    def test_public_mutations_preserve_pending_flags_and_align_storage(self):
        text = (ROOT / 'libraries/avatars/src/AvatarData.cpp').read_text()
        signatures = [
            'void AvatarData::setRawJointData(QVector<JointData> data)',
            'void AvatarData::setJointData(int index, const glm::quat& rotation, const glm::vec3& translation)',
            'void AvatarData::clearJointData(int index)',
            'void AvatarData::setJointRotation(int index, const glm::quat& rotation)',
            'void AvatarData::setJointTranslation(int index, const glm::vec3& translation)',
            'void AvatarData::setJointRotations(const QVector<glm::quat>& jointRotations)',
            'void AvatarData::setJointTranslations(const QVector<glm::vec3>& jointTranslations)',
        ]
        # Stand-ins cover storage, locking and scalar types. They do not claim
        # Qt event dispatch or renderer integration; the actual APK covers those.
        source = r'''
#include <cassert>
#include <mutex>
#include <vector>
namespace glm { struct quat {}; struct vec3 {}; }
struct JointData { glm::quat rotation; glm::vec3 translation;
 bool rotationIsDefaultPose=true, translationIsDefaultPose=true; };
template<class T> struct QVector : std::vector<T> {
 using std::vector<T>::vector;
 int size() const { return int(std::vector<T>::size()); }
};
struct QThread { static void* currentThread() { return nullptr; } };
struct QMetaObject { template<class... T> static void invokeMethod(T...) {} };
#define Q_ARG(type, value) value
struct QWriteLocker { std::mutex* mutex; QWriteLocker(std::mutex* m):mutex(m){m->lock();}
 ~QWriteLocker(){mutex->unlock();} };
constexpr int LOWEST_PSEUDO_JOINT_INDEX=1000;
class AvatarData { public:
 QVector<JointData> _jointData; std::vector<bool> _hasNewJointDataVec;
 std::mutex _jointDataLock; void* thread() { return nullptr; }
''' + '\n'.join(s.replace('AvatarData::', '') + ';' for s in signatures) + r'''
};
''' + '\n'.join(definition(text, s) for s in signatures) + r'''
int main() {
 AvatarData avatar;
 avatar.setRawJointData(QVector<JointData>(2));
 assert(avatar._hasNewJointDataVec.size()==2);
 avatar._hasNewJointDataVec[1]=true;
 auto aligned=[&](size_t count){
  assert(size_t(avatar._jointData.size())==count);
  assert(avatar._hasNewJointDataVec.size()==count);
  assert(avatar._hasNewJointDataVec[1]);
 };
 avatar.setJointTranslation(6, {}); aligned(7);
 assert(!avatar._hasNewJointDataVec[6]);
 avatar.setJointRotations(QVector<glm::quat>(10)); aligned(10);
 avatar.setJointTranslations(QVector<glm::vec3>(12)); aligned(12);
 avatar.clearJointData(14); aligned(15);
 avatar.setJointRotation(16, {}); aligned(17);
 avatar.setJointData(18, {}, {}); aligned(19);
 avatar.setRawJointData(QVector<JointData>(2)); aligned(2);
 avatar.setJointData(-1, {}, {}); aligned(2);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp, binary = Path(directory)/'joints.cpp', Path(directory)/'joints'
            cpp.write_text(source)
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-D_GLIBCXX_ASSERTIONS', str(cpp), '-o', str(binary)],
                           check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, timeout=10)
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == '__main__':
    unittest.main()
