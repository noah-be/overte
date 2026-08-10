#include "PhoneLoginState.h"
#include "test_assertions.h"

int main() {
    PhoneLoginState firstDialog;
    PhoneLoginState secondDialog;

    OVERTE_EXPECT(firstDialog.beginRequest());
    OVERTE_EXPECT(firstDialog.requestPending());
    OVERTE_EXPECT(!secondDialog.requestPending());

    OVERTE_EXPECT(secondDialog.beginRequest());
    OVERTE_EXPECT(secondDialog.requestPending());

    firstDialog.finishRequest();
    OVERTE_EXPECT(!firstDialog.requestPending());
    OVERTE_EXPECT(secondDialog.requestPending());

    secondDialog.finishRequest();
    OVERTE_EXPECT(!secondDialog.requestPending());

    // A completed object can immediately serve the next dialog lifecycle.
    OVERTE_EXPECT(firstDialog.beginRequest());
    OVERTE_EXPECT(!firstDialog.beginRequest());
    OVERTE_EXPECT(!secondDialog.requestPending());

    return 0;
}
