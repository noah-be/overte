function normalizeAllowlist(value) {
    if (typeof value !== "string") {
        return "";
    }

    var parts = value.split(/[\s,]+/);
    var result = [];
    var seen = {};
    for (var i = 0; i < parts.length; i++) {
        var entry = parts[i];
        var key = "$" + entry;
        if (entry.length > 0 && !seen[key]) {
            seen[key] = true;
            result.push(entry);
        }
    }
    return result.join("\n");
}
