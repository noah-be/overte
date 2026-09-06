"""Original AccountSettings header/methods; only clock is a deterministic seam."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class SettingsSnapshot(unittest.TestCase):
    def test_snapshot_keeps_settings_and_timestamp_together(self):
        source = (ROOT / 'libraries/networking/src/AccountSettings.cpp').read_text()
        # Compile all actual methods unchanged, with the actual public header.
        methods = source[source.index('static QString HOME_LOCATION_KEY'):]
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        driver = r'''
#include "libraries/networking/src/AccountSettings.h"
#include <atomic>
#include <cassert>
#include <thread>
std::atomic<quint64> ticks {0};
quint64 usecTimestampNow() { return ++ticks; }
'''
        checks = r'''
int main() {
    AccountSettings settings;
    auto initial = settings.snapshot();
    assert(initial.timestamp == 0 && initial.data["home_location"].toString().isEmpty());
    std::atomic<bool> started {false}, done {false};
    std::thread writer([&] {
        while (!started.load()) {}
        for (quint64 value = 1; value <= 20000; ++value) {
            settings.setHomeLocation(QString::number(value));
        }
        done = true;
    });
    started = true;
    unsigned observations = 0;
    do {
        const auto captured = settings.snapshot();
        assert(captured.data["home_location"].toString().toULongLong() == captured.timestamp);
        ++observations;
    } while (!done.load());
    writer.join();
    assert(observations > 0);
    const auto captured = settings.snapshot();
    assert(captured.timestamp == 20000 && settings.pack() == captured.data);
    settings.setHomeLocation("20000");
    assert(settings.lastChangeTimestamp() == captured.timestamp);
    settings.startedLoading();
    assert(settings.homeLocationState() == AccountSettings::Loading);
    settings.unpack({{"home_location", "server-home"}});
    assert(settings.homeLocationState() == AccountSettings::Loaded);
    assert(settings.snapshot().timestamp == 20001);
    assert(settings.snapshot().data["home_location"] == "server-home");
    quint64 applied = 999;
    assert(!settings.unpackIfUnchanged({{"home_location", "stale"}}, 20000, applied));
    assert(applied == 999 && settings.snapshot().timestamp == 20001);
    assert(settings.getHomeLocation() == "server-home");
    assert(settings.unpackIfUnchanged({{"home_location", "accepted"}}, 20001, applied));
    assert(applied == 20002 && settings.getHomeLocation() == "accepted");
    const auto beforeLocal = settings.snapshot();
    settings.startedLoading();
    settings.setHomeLocation("local-edit");
    assert(!settings.unpackIfUnchanged({{"home_location", "stale"}}, beforeLocal.timestamp, applied));
    assert(settings.getHomeLocation() == "local-edit" && settings.snapshot().timestamp == 20003);
    assert(settings.homeLocationState() == AccountSettings::Loaded);
    const auto beforeLogout = settings.snapshot();
    settings.loggedOut();
    assert(settings.homeLocationState() == AccountSettings::LoggedOut);
    assert(settings.getHomeLocation().isEmpty() && settings.pack()["home_location"].toString().isEmpty());
    assert(settings.snapshot().timestamp != beforeLogout.timestamp);
    assert(!settings.unpackIfUnchanged({{"home_location", "old-account"}}, beforeLogout.timestamp, applied));
    const auto beforeSameTick = settings.snapshot();
    ticks = beforeSameTick.timestamp - 1;
    settings.setHomeLocation("same-tick");
    assert(settings.snapshot().timestamp > beforeSameTick.timestamp);
    const auto beforeRollback = settings.snapshot();
    ticks = 0;
    settings.setHomeLocation("clock-rollback");
    assert(settings.snapshot().timestamp > beforeRollback.timestamp);
    assert(!settings.unpackIfUnchanged({{"home_location", "stale"}}, beforeRollback.timestamp, applied));
    AccountSettings intent;
    intent.unpack({{"home_location", "same-home"}});
    const auto requested = intent.snapshot();
    intent.startedLoading();
    intent.setHomeLocation("same-home");
    assert(intent.lastChangeTimestamp() > requested.timestamp);
    assert(!intent.unpackIfUnchanged({{"home_location", "remote-change"}}, requested.timestamp, applied));
    assert(intent.getHomeLocation() == "same-home");
    const auto loadedIntent = intent.snapshot();
    intent.setHomeLocation("same-home");
    assert(intent.lastChangeTimestamp() == loadedIntent.timestamp);
    intent.unpack({});
    const auto absentIntent = intent.snapshot();
    intent.setHomeLocation("");
    assert(intent.lastChangeTimestamp() > absentIntent.timestamp);
    assert(intent.homeLocationState() == AccountSettings::Loaded);
    AccountSettings pending;
    quint64 requestStamp = 777;
    assert(pending.beginDownload(requestStamp) && requestStamp == 0);
    pending.unpack({{"home_location", "initial"}});
    pending.setHomeLocation("unsent");
    const auto unsent = pending.snapshot();
    requestStamp = 777;
    assert(!pending.beginDownload(requestStamp) && requestStamp == 777);
    assert(pending.homeLocationState() == AccountSettings::Loaded);
    pending.acknowledgeSnapshot(unsent.timestamp - 1);
    assert(!pending.beginDownload(requestStamp));
    pending.setHomeLocation("newer");
    pending.acknowledgeSnapshot(unsent.timestamp);
    assert(!pending.beginDownload(requestStamp));
    pending.acknowledgeSnapshot(pending.lastChangeTimestamp());
    assert(pending.beginDownload(requestStamp));
    assert(requestStamp == pending.lastChangeTimestamp());
    pending.setHomeLocation("newer"); // Same-value local intent while Loading.
    assert(!pending.beginDownload(requestStamp));
    pending.loggedOut();
    assert(pending.beginDownload(requestStamp));
    ticks = std::numeric_limits<quint64>::max() - 1;
    settings.setHomeLocation("last-revision");
    try {
        settings.loggedOut();
        assert(false);
    } catch (const std::overflow_error&) {
        assert(settings.getHomeLocation() == "last-revision");
        assert(settings.snapshot().timestamp == std::numeric_limits<quint64>::max());
    }
}
'''
        with tempfile.TemporaryDirectory(prefix='overte-settings-snapshot-') as temporary:
            scratch = Path(temporary)
            unit = scratch / 'test.cpp'
            unit.write_text(driver + methods + checks)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-pthread', '-I', str(ROOT),
                            str(unit), '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
