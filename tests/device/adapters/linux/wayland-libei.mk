# SPDX-License-Identifier: Apache-2.0

CC ?= cc
PKG_CONFIG ?= pkg-config
BUILD_DIR ?= $(CURDIR)/_build/wayland-libei
TARGET := $(BUILD_DIR)/wayland-libei-daemon
PACKAGES := gio-unix-2.0 libei-1.0
CFLAGS ?= -O2
HARDENING_CFLAGS := -std=c11 -Wall -Wextra -Werror -D_FORTIFY_SOURCE=3 \
	-fstack-protector-strong -fPIE
HARDENING_LDFLAGS := -pie -Wl,-z,relro,-z,now

.PHONY: all clean test dependencies

all: $(TARGET)

dependencies:
	@$(PKG_CONFIG) --atleast-version=1.6.0 libei-1.0
	@$(PKG_CONFIG) --atleast-version=2.66 gio-unix-2.0

$(TARGET): wayland_libei_daemon.c | dependencies
	@mkdir -p "$(BUILD_DIR)"
	$(CC) $(CPPFLAGS) $(CFLAGS) $(HARDENING_CFLAGS) \
		$$( $(PKG_CONFIG) --cflags $(PACKAGES) ) "$<" \
		$(LDFLAGS) $(HARDENING_LDFLAGS) \
		$$( $(PKG_CONFIG) --libs $(PACKAGES) ) -lm -o "$@"

test:
	python3 -m unittest -v tests/test_wayland_libei_client.py

clean:
	rm -f "$(TARGET)"
