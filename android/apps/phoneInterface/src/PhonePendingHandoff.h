#pragma once

#include <utility>

namespace phone {

// Framework-independent "latest value wins" state used while Android has
// handed native code a value whose Qt consumer is not ready yet.
template<typename Value>
class PendingHandoff {
public:
    void replace(Value value, bool valid = true) {
        if (!valid) {
            clear();
            return;
        }
        _value = std::move(value);
        _pending = true;
    }

    bool takeIfReady(bool ready, Value& output) {
        if (!ready || !_pending) {
            return false;
        }
        output = std::move(_value);
        _value = Value {};
        _pending = false;
        return true;
    }

    bool pending() const {
        return _pending;
    }

    void clear() {
        _value = Value {};
        _pending = false;
    }

private:
    Value _value {};
    bool _pending { false };
};

} // namespace phone
