# SPDX-License-Identifier: Apache-2.0
"""Run the actual pose replacement after pending remote joint updates."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class AvatarPoseReplacementTests(unittest.TestCase):
    def test_real_setter_keeps_pose_and_dirty_flags_aligned(self):
        text = (ROOT / 'libraries/avatars/src/AvatarData.cpp').read_text()
        body = text.split('void AvatarData::setRawJointData(QVector<JointData> data)', 1)[1]
        body = body.split('\nvoid AvatarData::setJointData(', 1)[0]
        source = r'''
#include <algorithm>
#include <cassert>
#include <mutex>
#include <thread>
#include <vector>
template<class T> using QVector = std::vector<T>;
struct JointData { int value = 0; };
struct QThread { static auto currentThread() { return std::this_thread::get_id(); } };
struct QWriteLocker { std::unique_lock<std::mutex> lock;
 explicit QWriteLocker(std::mutex* mutex) : lock(*mutex) {} };
struct AvatarData;
struct QMetaObject {
 static void invokeMethod(AvatarData*, const char*, QVector<JointData>);
};
#define Q_ARG(type, value) value
struct AvatarData {
 std::mutex _jointDataLock;
 QVector<JointData> _jointData, queued;
 std::vector<bool> _hasNewJointDataVec;
 bool _hasNewJointData = false;
 std::thread::id owner = std::this_thread::get_id();
 auto thread() const { return owner; }
 void setRawJointData(QVector<JointData> data);
};
void QMetaObject::invokeMethod(AvatarData* avatar, const char*, QVector<JointData> pose) {
 avatar->queued = pose;
}
void AvatarData::setRawJointData(QVector<JointData> data)
''' + body + r'''
void checkPose(AvatarData& avatar, size_t size, int value) {
 assert(avatar._jointData.size() == size);
 assert(avatar._hasNewJointDataVec.size() == size);
 assert(avatar._hasNewJointData);
 assert(std::all_of(avatar._hasNewJointDataVec.begin(),
                   avatar._hasNewJointDataVec.end(), [](bool changed) { return changed; }));
 for (const auto& joint : avatar._jointData) assert(joint.value == value);
}
int main() {
 AvatarData avatar;
 // A received pose/orientation can precede asynchronous skeleton completion.
 avatar._jointData.resize(2);
 avatar._hasNewJointDataVec = {true, false};
 avatar._hasNewJointData = true;
 avatar.setRawJointData(QVector<JointData>(128, {7}));
 checkPose(avatar, 128, 7);
 // Replacing/reloading a skeleton must discard obsolete flag indices.
 avatar.setRawJointData(QVector<JointData>(4, {9}));
 checkPose(avatar, 4, 9);
 avatar.setRawJointData({});
 checkPose(avatar, 0, 0);
 avatar.setRawJointData(QVector<JointData>(1, {3}));
 checkPose(avatar, 1, 3);
 // Foreign-thread replacement queues work without partially changing arrays.
 std::thread worker([&] { avatar.setRawJointData(QVector<JointData>(12, {5})); });
 worker.join();
 checkPose(avatar, 1, 3);
 avatar.setRawJointData(avatar.queued);
 checkPose(avatar, 12, 5);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            cpp = pathlib.Path(directory) / 'pose.cpp'
            binary = pathlib.Path(directory) / 'pose'
            cpp.write_text(source)
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-D_GLIBCXX_ASSERTIONS', '-pthread', str(cpp), '-o', str(binary)],
                           check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
