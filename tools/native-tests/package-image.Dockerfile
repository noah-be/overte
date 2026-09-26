# Portable Conan export only; no source checkout or credential database.
FROM scratch AS packages
COPY conan-packages.tgz /conan-packages.tgz

FROM docker.io/overte/overte-server-build:2026-02-09-ubuntu-24.04-amd64@sha256:babe51f7c369e303aac67f0a9e7620707319b1d017a3ac13c4376b0d9fed056e
# System Qt's Conan provider needs these packages in addition to the base image.
# Bake them into the reusable image so cache loss does not repeat apt downloads.
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    ccache libglm-dev nlohmann-json3-dev \
    qtbase5-private-dev qtwebengine5-dev-tools libqt5multimedia5-plugins \
    qt5-image-formats-plugins fcitx5-frontend-qt5 qtxmlpatterns5-dev-tools \
    qttools5-dev libqt5x11extras5-dev libqt5svg5-dev qml-module-qtwebchannel \
    qml-module-qtquick-controls qml-module-qtquick-controls2 qml-module-qt-labs-settings \
    qml-module-qtquick-dialogs qml-module-qtwebengine \
    && rm -rf /var/lib/apt/lists/*
LABEL org.opencontainers.image.source="https://github.com/noah-be/overte"
LABEL org.opencontainers.image.description="Qualified Linux native-test dependencies for noah-be/overte"
RUN --mount=type=bind,from=packages,target=/native-packages \
    conan cache restore /native-packages/conan-packages.tgz
COPY native-package.json /opt/overte-native-package.json
