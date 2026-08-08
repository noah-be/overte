#pragma once

// Small, Qt-independent state contract for the phone's asynchronous login UI.
// Closing the view deliberately does not cancel the network request: a newly
// opened view must observe it until AccountManager reports a terminal result.
class PhoneLoginState {
public:
    bool beginRequest() {
        if (_requestPending) {
            return false;
        }
        _requestPending = true;
        return true;
    }

    void finishRequest() {
        _requestPending = false;
    }

    bool requestPending() const {
        return _requestPending;
    }

private:
    bool _requestPending { false };
};
