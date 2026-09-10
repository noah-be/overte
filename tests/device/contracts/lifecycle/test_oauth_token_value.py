"""Compile the complete production OAuth value/header/stream implementation."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class OAuthTokenValue(unittest.TestCase):
    def test_actual_value_and_persisted_header_boundary(self):
        network = ROOT / 'libraries/networking/src'
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        moc = Path(subprocess.check_output(['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()) / 'moc'
        driver = r'''
#include "OAuthAccessToken.h"
#include <QDataStream>
#include <QIODevice>
#include <cassert>
int main() {
    QJsonObject response {{"access_token", "token-canary"}, {"token_type", "bEaReR"}, {"expires_in", 2147483647}};
    const auto before = QDateTime::currentMSecsSinceEpoch();
    OAuthAccessToken valid(response);
    assert(!valid.isExpired() && valid.authorizationHeaderValue() == "Bearer token-canary");
    assert(valid.expiryTimestamp >= before + qint64(2147483647) * 1000);
    assert(valid.expiryTimestamp <= QDateTime::currentMSecsSinceEpoch() + qint64(2147483647) * 1000);
    for (const auto& pair : {qMakePair(QString("access_token"), QString("a\r\nInjected: canary")),
                             qMakePair(QString("access_token"), QString("a=b")),
                             qMakePair(QString("token_type"), QString("Basic")),
                             qMakePair(QString("refresh_token"), QString("refresh\ncanary"))}) {
        auto bad = response; bad.insert(pair.first, pair.second);
        OAuthAccessToken rejected(bad);
        assert(rejected.token.isEmpty() && rejected.isExpired() && rejected.authorizationHeaderValue().isEmpty());
    }
    for (const auto& expiry : {QJsonValue(0), QJsonValue(-1), QJsonValue(0.5), QJsonValue(1e100)}) {
        auto bad = response; bad.insert("expires_in", expiry); OAuthAccessToken rejected(bad);
        assert(rejected.token.isEmpty() && rejected.isExpired());
    }
    // Actual existing stream layout is retained; malformed restored values must
    // fail at use, even when a legacy record bypassed the JSON response parser.
    for (int mode = 0; mode != 6; ++mode) {
        OAuthAccessToken original(valid);
        if (mode == 1) original.token = "a\ncanary";
        if (mode == 2) original.tokenType = "Basic";
        if (mode == 3) { original.expiryTimestamp = -1; original.tokenType.clear(); }
        if (mode == 4) original.expiryTimestamp = QDateTime::currentMSecsSinceEpoch();
        if (mode == 5) original.tokenType.clear();
        QByteArray bytes;
        { QDataStream out(&bytes, QIODevice::WriteOnly); out << original; }
        OAuthAccessToken restored;
        { QDataStream in(bytes); in >> restored; assert(in.status() == QDataStream::Ok); }
        const bool rejected = mode != 0 && mode != 3;
        assert(restored.isExpired() == rejected);
        assert(restored.authorizationHeaderValue().isEmpty() == rejected);
    }
}
'''
        with tempfile.TemporaryDirectory(prefix='overte-oauth-value-') as temporary:
            scratch = Path(temporary)
            (scratch / 'test.cpp').write_text(driver)
            subprocess.run([str(moc), str(network / 'OAuthAccessToken.h'), '-o', str(scratch / 'moc.cpp')], check=True, timeout=15)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(network),
                str(network / 'OAuthAccessToken.cpp'), str(scratch / 'moc.cpp'), str(scratch / 'test.cpp'),
                '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
