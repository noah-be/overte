//
//  Created by Bradley Austin Davis on 2016/11/29
//  Copyright 2013-2016 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "GlobalAppProperties.h"

#include <QtCore/QtGlobal>

namespace hifi { namespace properties {

    const char* CRASHED = "com.highfidelity.crashed";
    const char* STEAM = "com.highfidelity.launchedFromSteam";
    const char* LOGGER = "com.highfidelity.logger";
    const char* OCULUS_STORE = "com.highfidelity.oculusStore";
    const char* STANDALONE = "com.highfidelity.standalone";
    const char* TEST = "com.highfidelity.test";
    const char* DISABLE_LOCAL_AVATAR = "overte.disableLocalAvatar";
    const char* MACOS_TEST_LIGHTWEIGHT_ENTITIES = "overte.macosTestLightweightEntities";
    const char* MACOS_TEST_REPRESENTATIVE_ENTITIES = "overte.macosTestRepresentativeEntities";
    const char* TRACING = "com.highfidelity.tracing";
    const char* HMD = "com.highfidelity.hmd";
    const char* APP_LOCAL_DATA_PATH = "com.highfidelity.appLocalDataPath";

    namespace gl {
        const char* BACKEND = "com.highfidelity.gl.backend";
        const char* PRIMARY_CONTEXT = "com.highfidelity.gl.primaryContext";
    }

    namespace vk {
        const char* CONTEXT = "com.highfidelity.vk.context";
    }

#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
    // Apple desktop OpenGL tops out at 4.1. Interface selects this explicitly,
    // but standalone tools and tests must also have a valid default before
    // they cache a surface format.
    static GraphicsAPI GRAPHICS_API { GraphicsAPI::GL41 };
#else
    static GraphicsAPI GRAPHICS_API { GraphicsAPI::GL45 };
#endif

    void setGraphicsAPI(GraphicsAPI api) {
        GRAPHICS_API = api;
    }

    GraphicsAPI getGraphicsAPI() {
        return GRAPHICS_API;
    }

} }
