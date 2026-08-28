#include <cassert>

#include "PhoneLifecycleHandoff.h"

int main() {
    using Action = phone::LifecycleHandoff::Action;

    phone::LifecycleHandoff lifecycle;
    assert(!lifecycle.ready());
    assert(lifecycle.foreground());
    assert(!lifecycle.backgroundApplied());

    // The first Activity resume is part of normal startup. It must not restart
    // audio that Application is already starting through its regular path.
    assert(lifecycle.setForeground(true) == Action::None);
    assert(lifecycle.markReady() == Action::None);
    assert(lifecycle.setForeground(true) == Action::None);

    assert(lifecycle.setForeground(false) == Action::EnterBackground);
    assert(lifecycle.backgroundApplied());
    assert(lifecycle.setForeground(false) == Action::None);
    assert(lifecycle.setForeground(true) == Action::EnterForeground);
    assert(!lifecycle.backgroundApplied());
    assert(lifecycle.setForeground(true) == Action::None);

    // A pause received during native startup is retained until Application's
    // load-complete boundary, then applied exactly once.
    phone::LifecycleHandoff pausedDuringStartup;
    assert(pausedDuringStartup.setForeground(false) == Action::None);
    assert(pausedDuringStartup.markReady() == Action::EnterBackground);
    assert(pausedDuringStartup.markReady() == Action::None);
    assert(pausedDuringStartup.setForeground(true) == Action::EnterForeground);

    // A complete pause/resume pair before native startup finishes cancels out.
    phone::LifecycleHandoff resumedDuringStartup;
    assert(resumedDuringStartup.setForeground(false) == Action::None);
    assert(resumedDuringStartup.setForeground(true) == Action::None);
    assert(resumedDuringStartup.markReady() == Action::None);

    return 0;
}
