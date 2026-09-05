// SPDX-License-Identifier: Apache-2.0
#include "../../../libraries/ui/src/CapabilityProfile.h"
#include <algorithm>
#include <cassert>
#include <iostream>
using namespace overte::ui;
int main() {
    assert(resolveProduct(true,false,"phoneInterface")==Product::Phone);
    assert(resolveProduct(true,false,"picoInterface")==Product::Pico);
    assert(resolveProduct(false,true,"")==Product::IOS);
    assert(resolveProduct(true,true,"phoneInterface")==Product::Unknown);
    assert(resolveProduct(true,false,"other")==Product::Unknown);
    assert(profileSelectors(Product::Phone,true)==std::vector<std::string>({"android_phoneInterface","android_interface","gles"}));
    assert(profileSelectors(Product::Pico,false)==std::vector<std::string>({"android_picoInterface","android_questInterface"}));
    assert(profileSelectors(Product::IOS,false)==std::vector<std::string>({"ios","mobile","touch","android_phoneInterface","android_interface","webview"}));
    for (auto product : {Product::Phone,Product::Pico,Product::IOS}) {
        auto selectors=profileSelectors(product,false);
        assert(std::find(selectors.begin(),selectors.end(),"webengine")==selectors.end());
        assert(controlSupport(product,"nav.back")==Support::Supported);
        assert(controlSupport(product,"unexpected-control")==Support::Hidden);
    }
    assert(controlSupport(Product::Phone,"settings.controllers")==Support::Hidden);
    assert(controlSupport(Product::IOS,"settings.hmd-preferences")==Support::Hidden);
    assert(controlSupport(Product::Pico,"settings.controllers")==Support::Supported);
    assert(controlSupport(Product::Unknown,"nav.back")==Support::Hidden);
    std::cout << "SH-003 pinned selector stacks and closed control classification PASS\n";
}
