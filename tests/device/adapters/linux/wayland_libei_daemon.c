/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Persistent, target-scoped input sender for an interactive Wayland desktop.
 *
 * The XDG RemoteDesktop portal is used only to obtain a private EIS fd.  All
 * input is sent through libei after ConnectToEIS(), as required by portal v2.
 * A single daemon/session serves many short adapter operations over a private
 * AF_UNIX socket.  No screen content is requested or captured here.
 */
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <gio/gio.h>
#include <gio/gunixfdlist.h>
#include <glib/gstdio.h>
#include <libei.h>
#include <linux/input-event-codes.h>
#include <math.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>

#define PORTAL_BUS "org.freedesktop.portal.Desktop"
#define PORTAL_PATH "/org/freedesktop/portal/desktop"
#define REMOTE_DESKTOP "org.freedesktop.portal.RemoteDesktop"
#define REQUEST_INTERFACE "org.freedesktop.portal.Request"
#define SESSION_INTERFACE "org.freedesktop.portal.Session"
#define REQUEST_LIMIT 4096
#define TOKEN_LIMIT 16384
#define MAX_DEVICES 16
#define PORTAL_KEYBOARD (1u << 0)
#define PORTAL_POINTER (1u << 1)

typedef struct {
    struct ei_device *device;
    bool resumed;
    bool emulating;
} InputDevice;

typedef struct {
    GDBusConnection *bus;
    char *session_path;
    unsigned portal_timeout_seconds;
    struct ei *ei;
    InputDevice devices[MAX_DEVICES];
    uint32_t sequence;
    bool ei_disconnected;
    int listener_fd;
    int lock_fd;
    char *socket_path;
    bool stop;
    bool keys_down[KEY_MAX + 1];
    bool buttons_down[KEY_MAX + 1];
} App;

typedef struct {
    GMainLoop *loop;
    GVariant *results;
    guint response;
    bool received;
    bool timed_out;
} RequestWait;

static volatile sig_atomic_t interrupted;

static GQuark
input_error_quark(void)
{
    return g_quark_from_static_string("overte-wayland-libei-error");
}

static void
on_signal(int signal_number)
{
    (void)signal_number;
    interrupted = 1;
}

static bool
valid_target(const char *value)
{
    size_t length;

    if (!value || !(length = strlen(value)) || length > 80)
        return false;
    if (!g_ascii_isalnum(value[0]))
        return false;
    for (size_t i = 0; i < length; i++) {
        char c = value[i];
        if (!g_ascii_isalnum(c) && c != '.' && c != '_' && c != '-')
            return false;
    }
    return strcmp(value, ".") != 0 && strcmp(value, "..") != 0;
}

static bool
validate_private_directory(const char *path, GError **error)
{
    struct stat st;

    if (lstat(path, &st) != 0) {
        g_set_error(error, input_error_quark(), errno,
                    "cannot inspect private directory: %s", g_strerror(errno));
        return false;
    }
    if (!S_ISDIR(st.st_mode) || S_ISLNK(st.st_mode) || st.st_uid != getuid() ||
        (st.st_mode & 077) != 0) {
        g_set_error_literal(error, input_error_quark(), EPERM,
                            "state/runtime directory must be user-owned mode 0700");
        return false;
    }
    return true;
}

static bool
ensure_private_directory(const char *path, GError **error)
{
    struct stat st;

    if (lstat(path, &st) == 0)
        return validate_private_directory(path, error);
    if (errno != ENOENT) {
        g_set_error(error, input_error_quark(), errno,
                    "cannot inspect private directory: %s", g_strerror(errno));
        return false;
    }
    if (g_mkdir_with_parents(path, 0700) != 0) {
        g_set_error(error, input_error_quark(), errno,
                    "cannot create private directory: %s", g_strerror(errno));
        return false;
    }
    if (chmod(path, 0700) != 0) {
        g_set_error(error, input_error_quark(), errno,
                    "cannot protect private directory: %s", g_strerror(errno));
        return false;
    }
    return validate_private_directory(path, error);
}

static char *
read_restore_token(const char *directory, GError **error)
{
    int directory_fd = -1, fd = -1;
    struct stat st;
    char *contents = NULL, *cursor;
    size_t length, remaining;

    directory_fd = open(directory, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (directory_fd < 0) {
        g_set_error(error, input_error_quark(), errno,
                    "cannot open restore-token directory: %s", g_strerror(errno));
        return NULL;
    }
    fd = openat(directory_fd, "restore-token", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        if (errno != ENOENT) {
            g_set_error(error, input_error_quark(), errno,
                        "cannot open restore token: %s", g_strerror(errno));
        }
        close(directory_fd);
        return NULL;
    }
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || st.st_uid != getuid() ||
        (st.st_mode & 077) != 0 || st.st_size <= 0 || st.st_size > TOKEN_LIMIT) {
        g_set_error_literal(error, input_error_quark(), EPERM,
                            "restore token must be a private regular file");
        goto out;
    }
    length = (size_t)st.st_size;
    contents = g_malloc(length + 1);
    cursor = contents;
    remaining = length;
    while (remaining) {
        ssize_t count = read(fd, cursor, remaining);
        if (count < 0 && errno == EINTR)
            continue;
        if (count <= 0) {
            g_set_error(error, input_error_quark(), count < 0 ? errno : EIO,
                        "cannot read restore token: %s",
                        count < 0 ? g_strerror(errno) : "unexpected end of file");
            g_clear_pointer(&contents, g_free);
            goto out;
        }
        cursor += count;
        remaining -= (size_t)count;
    }
    if (!length || length > TOKEN_LIMIT || memchr(contents, '\0', length) ||
        !g_utf8_validate(contents, (gssize)length, NULL)) {
        g_set_error_literal(error, input_error_quark(), EINVAL,
                            "restore token is empty or malformed");
        g_clear_pointer(&contents, g_free);
        goto out;
    }
    contents[length] = '\0';
out:
    close(fd);
    close(directory_fd);
    return contents;
}

static bool
write_all(int fd, const char *data, size_t length)
{
    while (length) {
        ssize_t written = write(fd, data, length);
        if (written < 0) {
            if (errno == EINTR)
                continue;
            return false;
        }
        data += written;
        length -= (size_t)written;
    }
    return true;
}

static bool
store_restore_token(const char *directory, const char *token, GError **error)
{
    int directory_fd = -1, fd = -1;
    char *temporary = NULL;
    bool success = false;
    size_t length;

    if (!token || !(length = strlen(token)) || length > TOKEN_LIMIT ||
        !g_utf8_validate(token, -1, NULL)) {
        g_set_error_literal(error, input_error_quark(), EINVAL,
                            "portal returned a malformed restore token");
        return false;
    }
    directory_fd = open(directory, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (directory_fd < 0) {
        g_set_error(error, input_error_quark(), errno,
                    "cannot open token directory: %s", g_strerror(errno));
        goto out;
    }
    for (unsigned attempt = 0; attempt < 8 && fd < 0; attempt++) {
        char *uuid = g_uuid_string_random();
        temporary = g_strdup_printf(".restore-token.%s.tmp", uuid);
        g_free(uuid);
        fd = openat(directory_fd, temporary,
                    O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
        if (fd < 0 && errno == EEXIST) {
            g_clear_pointer(&temporary, g_free);
            continue;
        }
    }
    if (fd < 0) {
        g_set_error(error, input_error_quark(), errno,
                    "cannot create token replacement: %s", g_strerror(errno));
        goto out;
    }
    if (!write_all(fd, token, length) || fchmod(fd, 0600) != 0 || fsync(fd) != 0) {
        g_set_error(error, input_error_quark(), errno,
                    "cannot persist restore token: %s", g_strerror(errno));
        goto out;
    }
    if (close(fd) != 0) {
        fd = -1;
        g_set_error(error, input_error_quark(), errno,
                    "cannot close restore token: %s", g_strerror(errno));
        goto out;
    }
    fd = -1;
    if (renameat(directory_fd, temporary, directory_fd, "restore-token") != 0 ||
        fsync(directory_fd) != 0) {
        g_set_error(error, input_error_quark(), errno,
                    "cannot rotate restore token atomically: %s", g_strerror(errno));
        goto out;
    }
    success = true;
out:
    if (!success && temporary && directory_fd >= 0)
        unlinkat(directory_fd, temporary, 0);
    if (fd >= 0)
        close(fd);
    if (directory_fd >= 0)
        close(directory_fd);
    g_free(temporary);
    return success;
}

static char *
new_handle_token(void)
{
    char *uuid = g_uuid_string_random();
    for (char *cursor = uuid; *cursor; cursor++) {
        if (*cursor == '-')
            *cursor = '_';
    }
    return uuid;
}

static char *
sender_component(GDBusConnection *bus)
{
    const char *unique = g_dbus_connection_get_unique_name(bus);
    char *component = g_strdup(unique && unique[0] == ':' ? unique + 1 : unique);
    for (char *cursor = component; cursor && *cursor; cursor++) {
        if (*cursor == '.')
            *cursor = '_';
    }
    return component;
}

static gboolean
request_timeout(gpointer user_data)
{
    RequestWait *wait = user_data;
    wait->timed_out = true;
    g_main_loop_quit(wait->loop);
    return G_SOURCE_REMOVE;
}

static void
request_response(GDBusConnection *connection, const gchar *sender_name,
                 const gchar *object_path, const gchar *interface_name,
                 const gchar *signal_name, GVariant *parameters,
                 gpointer user_data)
{
    RequestWait *wait = user_data;
    (void)connection;
    (void)sender_name;
    (void)object_path;
    (void)interface_name;
    (void)signal_name;

    if (!wait->received) {
        g_variant_get(parameters, "(u@a{sv})", &wait->response, &wait->results);
        wait->received = true;
        g_main_loop_quit(wait->loop);
    }
}

static GVariant *
portal_request(App *app, const char *method, const char *request_path,
               GVariant *parameters, GError **error)
{
    RequestWait wait = {0};
    guint subscription, timeout_source;
    GVariant *reply = NULL;
    const char *returned_path = NULL;

    wait.loop = g_main_loop_new(NULL, FALSE);
    subscription = g_dbus_connection_signal_subscribe(
        app->bus, PORTAL_BUS, REQUEST_INTERFACE, "Response", request_path, NULL,
        G_DBUS_SIGNAL_FLAGS_NONE, request_response, &wait, NULL);
    reply = g_dbus_connection_call_sync(
        app->bus, PORTAL_BUS, PORTAL_PATH, REMOTE_DESKTOP, method, parameters,
        G_VARIANT_TYPE("(o)"), G_DBUS_CALL_FLAGS_NONE, 30000, NULL, error);
    if (!reply)
        goto out;
    g_variant_get(reply, "(&o)", &returned_path);
    if (strcmp(returned_path, request_path) != 0) {
        g_set_error_literal(error, input_error_quark(), EPROTO,
                            "portal returned an unexpected request handle");
        goto out;
    }
    if (!wait.received) {
        timeout_source = g_timeout_add_seconds(app->portal_timeout_seconds,
                                               request_timeout, &wait);
        g_main_loop_run(wait.loop);
        if (!wait.timed_out)
            g_source_remove(timeout_source);
    }
    if (wait.timed_out) {
        g_set_error_literal(error, input_error_quark(), ETIMEDOUT,
                            "portal request timed out");
        goto out;
    }
    if (!wait.received || wait.response != 0) {
        g_set_error(error, input_error_quark(), ECANCELED,
                    "portal request was denied or cancelled (response %u)",
                    wait.received ? wait.response : 2u);
        goto out;
    }
out:
    g_dbus_connection_signal_unsubscribe(app->bus, subscription);
    if (reply)
        g_variant_unref(reply);
    g_main_loop_unref(wait.loop);
    if (error && *error) {
        if (wait.results)
            g_variant_unref(wait.results);
        return NULL;
    }
    return wait.results;
}

static bool
portal_uint32_property(App *app, const char *name, guint32 *result, GError **error)
{
    GVariant *reply, *boxed = NULL, *value = NULL;

    reply = g_dbus_connection_call_sync(
        app->bus, PORTAL_BUS, PORTAL_PATH, "org.freedesktop.DBus.Properties", "Get",
        g_variant_new("(ss)", REMOTE_DESKTOP, name), G_VARIANT_TYPE("(v)"),
        G_DBUS_CALL_FLAGS_NONE, 10000, NULL, error);
    if (!reply)
        return false;
    g_variant_get(reply, "(@v)", &boxed);
    value = g_variant_get_variant(boxed);
    if (!g_variant_is_of_type(value, G_VARIANT_TYPE_UINT32)) {
        g_set_error(error, input_error_quark(), EPROTO,
                    "portal property %s has an unexpected type", name);
        g_variant_unref(value);
        g_variant_unref(boxed);
        g_variant_unref(reply);
        return false;
    }
    *result = g_variant_get_uint32(value);
    g_variant_unref(value);
    g_variant_unref(boxed);
    g_variant_unref(reply);
    return true;
}

static bool
portal_version_supported(App *app, GError **error)
{
    guint32 version, available;

    if (!portal_uint32_property(app, "version", &version, error) ||
        !portal_uint32_property(app, "AvailableDeviceTypes", &available, error))
        return false;
    if (version < 2) {
        g_set_error(error, input_error_quark(), ENOTSUP,
                    "RemoteDesktop portal v2 is required (found v%u)", version);
        return false;
    }
    if ((available & (PORTAL_KEYBOARD | PORTAL_POINTER)) !=
        (PORTAL_KEYBOARD | PORTAL_POINTER)) {
        g_set_error_literal(error, input_error_quark(), ENOTSUP,
                            "portal does not offer keyboard and pointer control");
        return false;
    }
    return true;
}

static char *
portal_create_session(App *app, GError **error)
{
    char *request_token = new_handle_token();
    char *session_token = new_handle_token();
    char *sender = sender_component(app->bus);
    char *request_path = g_strdup_printf(
        "/org/freedesktop/portal/desktop/request/%s/%s", sender, request_token);
    GVariantBuilder options;
    GVariant *results;
    const char *session = NULL;
    char *result = NULL;

    g_variant_builder_init(&options, G_VARIANT_TYPE_VARDICT);
    g_variant_builder_add(&options, "{sv}", "handle_token",
                          g_variant_new_string(request_token));
    g_variant_builder_add(&options, "{sv}", "session_handle_token",
                          g_variant_new_string(session_token));
    results = portal_request(app, "CreateSession", request_path,
                             g_variant_new("(a{sv})", &options), error);
    if (results) {
        if (g_variant_lookup(results, "session_handle", "&s", &session) &&
            g_variant_is_object_path(session))
            result = g_strdup(session);
        else
            g_set_error_literal(error, input_error_quark(), EPROTO,
                                "portal omitted the session handle");
        g_variant_unref(results);
    }
    g_free(request_path);
    g_free(sender);
    g_free(session_token);
    g_free(request_token);
    return result;
}

static bool
portal_select_devices(App *app, const char *restore_token, GError **error)
{
    char *token = new_handle_token();
    char *sender = sender_component(app->bus);
    char *request_path = g_strdup_printf(
        "/org/freedesktop/portal/desktop/request/%s/%s", sender, token);
    GVariantBuilder options;
    GVariant *results;

    g_variant_builder_init(&options, G_VARIANT_TYPE_VARDICT);
    g_variant_builder_add(&options, "{sv}", "handle_token", g_variant_new_string(token));
    g_variant_builder_add(&options, "{sv}", "types",
                          g_variant_new_uint32(PORTAL_KEYBOARD | PORTAL_POINTER));
    g_variant_builder_add(&options, "{sv}", "persist_mode", g_variant_new_uint32(2));
    if (restore_token)
        g_variant_builder_add(&options, "{sv}", "restore_token",
                              g_variant_new_string(restore_token));
    results = portal_request(app, "SelectDevices", request_path,
                             g_variant_new("(oa{sv})", app->session_path, &options), error);
    if (results)
        g_variant_unref(results);
    g_free(request_path);
    g_free(sender);
    g_free(token);
    return results != NULL;
}

static char *
portal_start(App *app, const char *parent_window, GError **error)
{
    char *token = new_handle_token();
    char *sender = sender_component(app->bus);
    char *request_path = g_strdup_printf(
        "/org/freedesktop/portal/desktop/request/%s/%s", sender, token);
    GVariantBuilder options;
    GVariant *results;
    const char *restore = NULL;
    guint32 devices = 0;
    char *result = NULL;

    g_variant_builder_init(&options, G_VARIANT_TYPE_VARDICT);
    g_variant_builder_add(&options, "{sv}", "handle_token", g_variant_new_string(token));
    results = portal_request(app, "Start", request_path,
                             g_variant_new("(osa{sv})", app->session_path,
                                           parent_window ? parent_window : "", &options), error);
    if (results) {
        if (!g_variant_lookup(results, "devices", "u", &devices) ||
            (devices & (PORTAL_KEYBOARD | PORTAL_POINTER)) !=
                (PORTAL_KEYBOARD | PORTAL_POINTER)) {
            g_set_error_literal(error, input_error_quark(), EPERM,
                                "portal did not grant keyboard and pointer access");
        } else if (!g_variant_lookup(results, "restore_token", "&s", &restore) ||
                   !restore || !restore[0]) {
            g_set_error_literal(error, input_error_quark(), EPERM,
                                "portal did not grant persistent access");
        } else {
            result = g_strdup(restore);
        }
        g_variant_unref(results);
    }
    g_free(request_path);
    g_free(sender);
    g_free(token);
    return result;
}

static int
portal_connect_to_eis(App *app, GError **error)
{
    GVariantBuilder options;
    GVariant *reply;
    GUnixFDList *fd_list = NULL;
    gint handle = -1, fd = -1;

    g_variant_builder_init(&options, G_VARIANT_TYPE_VARDICT);
    reply = g_dbus_connection_call_with_unix_fd_list_sync(
        app->bus, PORTAL_BUS, PORTAL_PATH, REMOTE_DESKTOP, "ConnectToEIS",
        g_variant_new("(oa{sv})", app->session_path, &options), G_VARIANT_TYPE("(h)"),
        G_DBUS_CALL_FLAGS_NONE, 30000, NULL, &fd_list, NULL, error);
    if (!reply)
        return -1;
    g_variant_get(reply, "(h)", &handle);
    if (!fd_list || handle < 0 || handle >= g_unix_fd_list_get_length(fd_list))
        g_set_error_literal(error, input_error_quark(), EPROTO,
                            "portal returned an invalid EIS fd handle");
    else
        fd = g_unix_fd_list_get(fd_list, handle, error);
    g_variant_unref(reply);
    if (fd_list)
        g_object_unref(fd_list);
    return fd;
}

static void
portal_close(App *app)
{
    GError *error = NULL;
    GVariant *reply;

    if (!app->bus || !app->session_path)
        return;
    reply = g_dbus_connection_call_sync(
        app->bus, PORTAL_BUS, app->session_path, SESSION_INTERFACE, "Close", NULL, NULL,
        G_DBUS_CALL_FLAGS_NONE, 5000, NULL, &error);
    if (reply)
        g_variant_unref(reply);
    g_clear_error(&error);
}

static InputDevice *
find_input_device(App *app, enum ei_device_capability capability)
{
    for (size_t i = 0; i < MAX_DEVICES; i++) {
        InputDevice *slot = &app->devices[i];
        if (slot->device && slot->resumed &&
            ei_device_has_capability(slot->device, capability))
            return slot;
    }
    return NULL;
}

static bool
input_ready(App *app)
{
    return find_input_device(app, EI_DEVICE_CAP_POINTER) &&
           find_input_device(app, EI_DEVICE_CAP_BUTTON) &&
           find_input_device(app, EI_DEVICE_CAP_KEYBOARD);
}

static InputDevice *
device_slot(App *app, struct ei_device *device)
{
    for (size_t i = 0; i < MAX_DEVICES; i++) {
        if (app->devices[i].device == device)
            return &app->devices[i];
    }
    return NULL;
}

static void
dispatch_ei(App *app)
{
    struct ei_event *event;

    ei_dispatch(app->ei);
    while ((event = ei_get_event(app->ei))) {
        struct ei_device *device = ei_event_get_device(event);
        InputDevice *slot;

        switch (ei_event_get_type(event)) {
        case EI_EVENT_DISCONNECT:
            app->ei_disconnected = true;
            break;
        case EI_EVENT_SEAT_ADDED:
            ei_seat_bind_capabilities(ei_event_get_seat(event),
                                      EI_DEVICE_CAP_POINTER,
                                      EI_DEVICE_CAP_BUTTON,
                                      EI_DEVICE_CAP_KEYBOARD,
                                      NULL);
            break;
        case EI_EVENT_DEVICE_ADDED:
            if (!device_slot(app, device)) {
                bool supported = ei_device_has_capability(device, EI_DEVICE_CAP_POINTER) ||
                                 ei_device_has_capability(device, EI_DEVICE_CAP_BUTTON) ||
                                 ei_device_has_capability(device, EI_DEVICE_CAP_KEYBOARD);
                bool stored = false;
                for (size_t i = 0; supported && !stored && i < MAX_DEVICES; i++) {
                    if (!app->devices[i].device) {
                        app->devices[i].device = ei_device_ref(device);
                        stored = true;
                    }
                }
                if (!supported || !stored)
                    ei_device_close(device);
            }
            break;
        case EI_EVENT_DEVICE_RESUMED:
            slot = device_slot(app, device);
            if (slot) {
                slot->resumed = true;
                if (!slot->emulating) {
                    ei_device_start_emulating(slot->device, ++app->sequence);
                    slot->emulating = true;
                }
            }
            break;
        case EI_EVENT_DEVICE_PAUSED:
            slot = device_slot(app, device);
            if (slot) {
                slot->resumed = false;
                slot->emulating = false;
                if (ei_device_has_capability(device, EI_DEVICE_CAP_KEYBOARD))
                    memset(app->keys_down, 0, sizeof(app->keys_down));
                if (ei_device_has_capability(device, EI_DEVICE_CAP_BUTTON))
                    memset(app->buttons_down, 0, sizeof(app->buttons_down));
            }
            break;
        case EI_EVENT_DEVICE_REMOVED:
            slot = device_slot(app, device);
            if (slot) {
                if (ei_device_has_capability(device, EI_DEVICE_CAP_KEYBOARD))
                    memset(app->keys_down, 0, sizeof(app->keys_down));
                if (ei_device_has_capability(device, EI_DEVICE_CAP_BUTTON))
                    memset(app->buttons_down, 0, sizeof(app->buttons_down));
                slot->device = ei_device_unref(slot->device);
                slot->resumed = false;
                slot->emulating = false;
            }
            break;
        default:
            break;
        }
        ei_event_unref(event);
    }
}

static bool
wait_for_input(App *app, unsigned timeout_seconds, GError **error)
{
    gint64 deadline = g_get_monotonic_time() + (gint64)timeout_seconds * G_USEC_PER_SEC;

    while (!input_ready(app) && !app->ei_disconnected && !interrupted) {
        gint64 remaining = deadline - g_get_monotonic_time();
        struct pollfd descriptor = { .fd = ei_get_fd(app->ei), .events = POLLIN };
        int timeout = remaining > 0 ? (int)MIN(remaining / 1000, 1000) : 0;
        int result;

        if (remaining <= 0)
            break;
        result = poll(&descriptor, 1, timeout);
        if (result < 0 && errno != EINTR) {
            g_set_error(error, input_error_quark(), errno,
                        "libei poll failed: %s", g_strerror(errno));
            return false;
        }
        if (result > 0)
            dispatch_ei(app);
    }
    if (!input_ready(app)) {
        g_set_error_literal(error, input_error_quark(),
                            app->ei_disconnected ? ECONNRESET : ETIMEDOUT,
                            app->ei_disconnected ? "libei disconnected" :
                                                   "libei devices did not become ready");
        return false;
    }
    return true;
}

static bool
parse_unsigned(const char *text, unsigned minimum, unsigned maximum, unsigned *result)
{
    char *end = NULL;
    unsigned long value;

    errno = 0;
    value = strtoul(text ? text : "", &end, 10);
    if (errno || !text || !text[0] || !end || *end || value < minimum || value > maximum)
        return false;
    *result = (unsigned)value;
    return true;
}

static bool
parse_delta(const char *text, double *result)
{
    char *end = NULL;
    double value;

    errno = 0;
    value = g_ascii_strtod(text ? text : "", &end);
    if (errno || !text || !text[0] || !end || *end || !isfinite(value) ||
        fabs(value) > 100000.0)
        return false;
    *result = value;
    return true;
}

static void
input_frame(struct ei_device *device, struct ei *ei)
{
    ei_device_frame(device, ei_now(ei));
}

static char *
handle_command(App *app, char *line)
{
    char *save = NULL;
    char *command = strtok_r(line, " \t\r\n", &save);
    char *first = strtok_r(NULL, " \t\r\n", &save);
    char *second = strtok_r(NULL, " \t\r\n", &save);
    char *extra = strtok_r(NULL, " \t\r\n", &save);
    InputDevice *slot;
    unsigned code;

    if (!command)
        return g_strdup("ERR invalid empty-command\n");
    if (strcmp(command, "status") == 0 && !first)
        return g_strdup_printf("OK ready=%u pointer=%u button=%u keyboard=%u\n",
            input_ready(app) ? 1 : 0,
            find_input_device(app, EI_DEVICE_CAP_POINTER) ? 1 : 0,
            find_input_device(app, EI_DEVICE_CAP_BUTTON) ? 1 : 0,
            find_input_device(app, EI_DEVICE_CAP_KEYBOARD) ? 1 : 0);
    if (strcmp(command, "shutdown") == 0 && !first) {
        app->stop = true;
        return g_strdup("OK\n");
    }
    if (!input_ready(app))
        return g_strdup("ERR not-ready input-devices-unavailable\n");
    if (strcmp(command, "motion") == 0 && first && second && !extra) {
        double dx, dy;
        slot = find_input_device(app, EI_DEVICE_CAP_POINTER);
        if (!parse_delta(first, &dx) || !parse_delta(second, &dy))
            return g_strdup("ERR invalid invalid-motion\n");
        ei_device_pointer_motion(slot->device, dx, dy);
        input_frame(slot->device, app->ei);
        return g_strdup("OK\n");
    }
    if (strcmp(command, "button") == 0 && first && second && !extra) {
        bool press;
        slot = find_input_device(app, EI_DEVICE_CAP_BUTTON);
        if (!parse_unsigned(first, BTN_MISC, KEY_MAX, &code) ||
            (strcmp(second, "down") != 0 && strcmp(second, "up") != 0 &&
             strcmp(second, "click") != 0))
            return g_strdup("ERR invalid invalid-button\n");
        press = strcmp(second, "down") == 0;
        if (strcmp(second, "click") == 0) {
            if (app->buttons_down[code])
                return g_strdup("ERR state button-already-down\n");
            ei_device_button_button(slot->device, code, true);
            input_frame(slot->device, app->ei);
            ei_device_button_button(slot->device, code, false);
            input_frame(slot->device, app->ei);
        } else {
            if (app->buttons_down[code] == press)
                return g_strdup("ERR state duplicate-button-state\n");
            ei_device_button_button(slot->device, code, press);
            input_frame(slot->device, app->ei);
            app->buttons_down[code] = press;
        }
        return g_strdup("OK\n");
    }
    if (strcmp(command, "key") == 0 && first && second && !extra) {
        bool press;
        slot = find_input_device(app, EI_DEVICE_CAP_KEYBOARD);
        if (!parse_unsigned(first, 1, KEY_MAX, &code) ||
            (strcmp(second, "down") != 0 && strcmp(second, "up") != 0 &&
             strcmp(second, "tap") != 0))
            return g_strdup("ERR invalid invalid-key\n");
        press = strcmp(second, "down") == 0;
        if (strcmp(second, "tap") == 0) {
            if (app->keys_down[code])
                return g_strdup("ERR state key-already-down\n");
            ei_device_keyboard_key(slot->device, code, true);
            input_frame(slot->device, app->ei);
            ei_device_keyboard_key(slot->device, code, false);
            input_frame(slot->device, app->ei);
        } else {
            if (app->keys_down[code] == press)
                return g_strdup("ERR state duplicate-key-state\n");
            ei_device_keyboard_key(slot->device, code, press);
            input_frame(slot->device, app->ei);
            app->keys_down[code] = press;
        }
        return g_strdup("OK\n");
    }
    return g_strdup("ERR invalid unsupported-command\n");
}

static bool
send_response(int fd, const char *response)
{
    size_t remaining = strlen(response);
    while (remaining) {
        ssize_t sent = send(fd, response, remaining, MSG_NOSIGNAL);
        if (sent < 0) {
            if (errno == EINTR)
                continue;
            return false;
        }
        response += sent;
        remaining -= (size_t)sent;
    }
    return true;
}

static void
serve_client(App *app)
{
    int client = accept4(app->listener_fd, NULL, NULL, SOCK_CLOEXEC);
    struct ucred credentials;
    socklen_t credentials_length = sizeof(credentials);
    struct timeval timeout = { .tv_sec = 2 };
    char buffer[REQUEST_LIMIT + 1];
    size_t used = 0;

    if (client < 0)
        return;
    if (getsockopt(client, SOL_SOCKET, SO_PEERCRED, &credentials,
                   &credentials_length) != 0 || credentials.uid != getuid()) {
        close(client);
        return;
    }
    setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    while (used < REQUEST_LIMIT) {
        ssize_t count = recv(client, buffer + used, REQUEST_LIMIT - used, 0);
        if (count <= 0)
            break;
        used += (size_t)count;
        if (memchr(buffer, '\n', used))
            break;
    }
    if (!used || used == REQUEST_LIMIT || !memchr(buffer, '\n', used)) {
        send_response(client, "ERR invalid request-must-be-one-bounded-line\n");
    } else {
        char *newline = memchr(buffer, '\n', used);
        char *response;
        *newline = '\0';
        if ((size_t)(newline - buffer + 1) != used)
            response = g_strdup("ERR invalid trailing-data\n");
        else
            response = handle_command(app, buffer);
        send_response(client, response);
        g_free(response);
    }
    close(client);
}

static bool
create_listener(App *app, const char *runtime_directory, GError **error)
{
    struct sockaddr_un address = { .sun_family = AF_UNIX };
    struct stat st;

    app->socket_path = g_build_filename(runtime_directory, "input.sock", NULL);
    if (strlen(app->socket_path) >= sizeof(address.sun_path)) {
        g_set_error_literal(error, input_error_quark(), ENAMETOOLONG,
                            "runtime socket path is too long");
        return false;
    }
    if (lstat(app->socket_path, &st) == 0) {
        if (!S_ISSOCK(st.st_mode) || st.st_uid != getuid()) {
            g_set_error_literal(error, input_error_quark(), EPERM,
                                "refusing to replace an unsafe runtime path");
            return false;
        }
        if (unlink(app->socket_path) != 0) {
            g_set_error(error, input_error_quark(), errno,
                        "cannot remove stale socket: %s", g_strerror(errno));
            return false;
        }
    } else if (errno != ENOENT) {
        g_set_error(error, input_error_quark(), errno,
                    "cannot inspect runtime socket: %s", g_strerror(errno));
        return false;
    }
    app->listener_fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (app->listener_fd < 0) {
        g_set_error(error, input_error_quark(), errno,
                    "cannot create runtime socket: %s", g_strerror(errno));
        return false;
    }
    memcpy(address.sun_path, app->socket_path, strlen(app->socket_path) + 1);
    if (bind(app->listener_fd, (struct sockaddr *)&address, sizeof(address)) != 0 ||
        chmod(app->socket_path, 0600) != 0 || listen(app->listener_fd, 8) != 0) {
        g_set_error(error, input_error_quark(), errno,
                    "cannot publish runtime socket: %s", g_strerror(errno));
        return false;
    }
    return true;
}

static void
release_held_input(App *app)
{
    InputDevice *keyboard, *button;
    bool keyboard_changed = false, button_changed = false;

    if (!app->ei)
        return;
    keyboard = find_input_device(app, EI_DEVICE_CAP_KEYBOARD);
    button = find_input_device(app, EI_DEVICE_CAP_BUTTON);
    for (unsigned code = 1; keyboard && code <= KEY_MAX; code++) {
        if (app->keys_down[code]) {
            ei_device_keyboard_key(keyboard->device, code, false);
            keyboard_changed = true;
        }
    }
    for (unsigned code = BTN_MISC; button && code <= KEY_MAX; code++) {
        if (app->buttons_down[code]) {
            ei_device_button_button(button->device, code, false);
            button_changed = true;
        }
    }
    if (keyboard_changed)
        input_frame(keyboard->device, app->ei);
    if (button_changed)
        input_frame(button->device, app->ei);
}

static void
cleanup(App *app)
{
    release_held_input(app);
    if (app->listener_fd >= 0)
        close(app->listener_fd);
    if (app->socket_path)
        unlink(app->socket_path);
    if (app->ei) {
        for (size_t i = 0; i < MAX_DEVICES; i++) {
            if (app->devices[i].device) {
                if (app->devices[i].emulating)
                    ei_device_stop_emulating(app->devices[i].device);
                ei_device_close(app->devices[i].device);
                app->devices[i].device = ei_device_unref(app->devices[i].device);
            }
        }
        app->ei = ei_unref(app->ei);
    }
    portal_close(app);
    if (app->bus)
        g_object_unref(app->bus);
    if (app->lock_fd >= 0)
        close(app->lock_fd);
    g_free(app->session_path);
    g_free(app->socket_path);
}

static void
usage(FILE *stream, const char *program)
{
    fprintf(stream,
        "Usage: %s --target ID [--state-root PATH] [--runtime-root PATH]\n"
        "          [--parent-window HANDLE] [--authorize]\n"
        "          [--portal-timeout SECONDS]\n\n"
        "Without --authorize, an existing private restore token is required.\n"
        "Use --authorize only for the deliberate first interactive approval.\n",
        program);
}

int
main(int argc, char **argv)
{
    App app = { .listener_fd = -1, .lock_fd = -1, .portal_timeout_seconds = 300 };
    const char *target = NULL, *state_root = NULL, *runtime_root = NULL;
    const char *parent_window = "";
    bool authorize = false;
    char *default_state_root = NULL, *default_runtime_root = NULL;
    char *state_directory = NULL, *runtime_directory = NULL, *lock_path = NULL;
    char *restore_token = NULL, *new_restore_token = NULL;
    GError *error = NULL;
    int eis_fd = -1;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--target") == 0 && i + 1 < argc)
            target = argv[++i];
        else if (strcmp(argv[i], "--state-root") == 0 && i + 1 < argc)
            state_root = argv[++i];
        else if (strcmp(argv[i], "--runtime-root") == 0 && i + 1 < argc)
            runtime_root = argv[++i];
        else if (strcmp(argv[i], "--parent-window") == 0 && i + 1 < argc)
            parent_window = argv[++i];
        else if (strcmp(argv[i], "--portal-timeout") == 0 && i + 1 < argc) {
            unsigned value;
            if (!parse_unsigned(argv[++i], 10, 1800, &value)) {
                usage(stderr, argv[0]);
                return 2;
            }
            app.portal_timeout_seconds = value;
        } else if (strcmp(argv[i], "--authorize") == 0)
            authorize = true;
        else if (strcmp(argv[i], "--help") == 0) {
            usage(stdout, argv[0]);
            return 0;
        } else {
            usage(stderr, argv[0]);
            return 2;
        }
    }
    if (!valid_target(target) || !parent_window || strchr(parent_window, '\n') ||
        strlen(parent_window) > 512) {
        usage(stderr, argv[0]);
        return 2;
    }
    default_state_root = g_build_filename(g_get_user_state_dir(), "overte-device-lab",
                                           "wayland-input", NULL);
    default_runtime_root = g_build_filename(g_get_user_runtime_dir(), "overte-device-lab",
                                             "wayland-input", NULL);
    state_directory = g_build_filename(state_root ? state_root : default_state_root,
                                       target, NULL);
    runtime_directory = g_build_filename(runtime_root ? runtime_root : default_runtime_root,
                                         target, NULL);
    if (!g_path_is_absolute(state_directory) || !g_path_is_absolute(runtime_directory) ||
        !ensure_private_directory(state_directory, &error) ||
        !ensure_private_directory(runtime_directory, &error))
        goto failure;

    lock_path = g_build_filename(state_directory, "daemon.lock", NULL);
    app.lock_fd = open(lock_path, O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (app.lock_fd < 0 || fchmod(app.lock_fd, 0600) != 0 ||
        flock(app.lock_fd, LOCK_EX | LOCK_NB) != 0) {
        g_set_error_literal(&error, input_error_quark(), EBUSY,
                            "another target input daemon owns the state");
        goto failure;
    }
    restore_token = read_restore_token(state_directory, &error);
    if (error)
        goto failure;
    if (!restore_token && !authorize) {
        g_set_error_literal(&error, input_error_quark(), ENOENT,
            "no restore token; rerun once with --authorize to approve interactively");
        goto failure;
    }

    app.bus = g_bus_get_sync(G_BUS_TYPE_SESSION, NULL, &error);
    if (!app.bus || !portal_version_supported(&app, &error))
        goto failure;
    app.session_path = portal_create_session(&app, &error);
    if (!app.session_path || !portal_select_devices(&app, restore_token, &error))
        goto failure;
    new_restore_token = portal_start(&app, parent_window, &error);
    if (!new_restore_token || !store_restore_token(state_directory, new_restore_token, &error))
        goto failure;
    eis_fd = portal_connect_to_eis(&app, &error);
    if (eis_fd < 0)
        goto failure;

    app.ei = ei_new_sender(NULL);
    if (!app.ei) {
        g_set_error_literal(&error, input_error_quark(), ENOMEM,
                            "cannot allocate libei sender");
        goto failure;
    }
    ei_configure_name(app.ei, "Overte E2E device lab");
    if (ei_setup_backend_fd(app.ei, eis_fd) < 0) {
        close(eis_fd);
        eis_fd = -1;
        g_set_error_literal(&error, input_error_quark(), EIO,
                            "cannot attach the portal EIS fd to libei");
        goto failure;
    }
    eis_fd = -1; /* libei owns it */
    if (!wait_for_input(&app, 30, &error) ||
        !create_listener(&app, runtime_directory, &error))
        goto failure;

    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    printf("READY socket=%s\n", app.socket_path);
    fflush(stdout);
    while (!app.stop && !app.ei_disconnected && !interrupted) {
        struct pollfd descriptors[2] = {
            { .fd = app.listener_fd, .events = POLLIN },
            { .fd = ei_get_fd(app.ei), .events = POLLIN },
        };
        int result = poll(descriptors, 2, 1000);
        if (result < 0) {
            if (errno == EINTR)
                continue;
            fprintf(stderr, "wayland-libei: poll failed: %s\n", g_strerror(errno));
            break;
        }
        if (descriptors[1].revents)
            dispatch_ei(&app);
        if (descriptors[0].revents & POLLIN)
            serve_client(&app);
    }

    cleanup(&app);
    g_free(new_restore_token);
    g_free(restore_token);
    g_free(lock_path);
    g_free(runtime_directory);
    g_free(state_directory);
    g_free(default_runtime_root);
    g_free(default_state_root);
    return app.ei_disconnected ? 1 : 0;

failure:
    fprintf(stderr, "wayland-libei: %s\n", error ? error->message : "unknown failure");
    g_clear_error(&error);
    if (eis_fd >= 0)
        close(eis_fd);
    cleanup(&app);
    g_free(new_restore_token);
    g_free(restore_token);
    g_free(lock_path);
    g_free(runtime_directory);
    g_free(state_directory);
    g_free(default_runtime_root);
    g_free(default_state_root);
    return 1;
}
