#pragma once

namespace phone {

// Framework-independent Activity lifecycle state. Android events may arrive
// before Application has connected AndroidHelper to its audio/render paths, so
// retain the latest state and emit only the transitions that Application must
// apply after its load-complete boundary.
class LifecycleHandoff {
public:
    enum class Action {
        None,
        EnterBackground,
        EnterForeground,
    };

    Action markReady() {
        _ready = true;
        return transition();
    }

    Action setForeground(bool foreground) {
        _foreground = foreground;
        return transition();
    }

    bool ready() const {
        return _ready;
    }

    bool foreground() const {
        return _foreground;
    }

    bool backgroundApplied() const {
        return _backgroundApplied;
    }

private:
    Action transition() {
        if (!_ready) {
            return Action::None;
        }
        if (!_foreground && !_backgroundApplied) {
            _backgroundApplied = true;
            return Action::EnterBackground;
        }
        if (_foreground && _backgroundApplied) {
            _backgroundApplied = false;
            return Action::EnterForeground;
        }
        return Action::None;
    }

    bool _ready { false };
    bool _foreground { true };
    bool _backgroundApplied { false };
};

} // namespace phone
