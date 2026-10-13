// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
(function () {
    if (window !== window.top || window.__overteEditor) { return; }
    var composing = null;
    function editable(element) {
        return element && (element instanceof HTMLTextAreaElement ||
            element instanceof HTMLInputElement && /^(text|search|email|url|tel|password|number)$/.test(element.type)
            || element.isContentEditable);
    }
    function selection(element) {
        if (typeof element.selectionStart === "number") {
            return element.selectionDirection === "backward" ? [element.selectionEnd, element.selectionStart] : [element.selectionStart, element.selectionEnd];
        }
        if (element instanceof HTMLInputElement && element.type === "number") { return [element.value.length, element.value.length]; }
        var selected = window.getSelection();
        if (!selected.rangeCount || !element.contains(selected.anchorNode) || !element.contains(selected.focusNode)) {
            return [0, 0];
        }
        function offset(node, index) {
            var range = document.createRange(); range.selectNodeContents(element);
            range.setEnd(node, index); return range.toString().length;
        }
        return [offset(selected.anchorNode, selected.anchorOffset), offset(selected.focusNode, selected.focusOffset)];
    }
    function publish() {
        var element = document.activeElement;
        if (!editable(element)) { window.__overteTransport.editor({ active: false }); return; }
        var sensitive = element.type === "password", text = element.value === undefined ? element.textContent : element.value;
        var selected = selection(element), start = Math.max(0, selected[1] - 8192), bounds = element.getBoundingClientRect();
        // Password contents never cross the DOM/native boundary.
        window.__overteTransport.editor({ active: true, sensitive: sensitive,
            text: sensitive ? "" : text.slice(start, start + 16384), cursor: selected[1] - start, anchor: selected[0] - start, absoluteCursor: selected[1],
            x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height,
            kind: element.type || "text" });
    }
    function boundary(text, index) {
        return index >= 0 && index <= text.length && !(index > 0 && index < text.length
            && text.charCodeAt(index - 1) >= 0xD800 && text.charCodeAt(index - 1) <= 0xDBFF
            && text.charCodeAt(index) >= 0xDC00 && text.charCodeAt(index) <= 0xDFFF);
    }
    function point(element, offset) {
        var walk = document.createTreeWalker(element, NodeFilter.SHOW_TEXT), node;
        while ((node = walk.nextNode())) {
            if (offset <= node.length) { return [node, offset]; }
            offset -= node.length;
        }
        return [element, element.childNodes.length];
    }
    function select(element, start, end) {
        if (typeof element.setSelectionRange === "function") { element.setSelectionRange(Math.min(start, end), Math.max(start, end), start > end ? "backward" : "forward"); return; }
        var left = point(element, start), right = point(element, end), range = document.createRange();
        var selected = window.getSelection();
        if (selected.setBaseAndExtent) { selected.setBaseAndExtent(left[0], left[1], right[0], right[1]); return; }
        range.setStart(left[0], left[1]); range.setEnd(right[0], right[1]);
        selected.removeAllRanges(); selected.addRange(range);
    }
    function replace(element, text, start, end, insertion) {
        if (element instanceof HTMLInputElement && element.type === "number") element.value = text.slice(0, start) + insertion + text.slice(end);
        else if (typeof element.setRangeText === "function") element.setRangeText(insertion, start, end, "end");
        else { select(element, start, end); document.execCommand("insertText", false, insertion); }
    }
    function ime(element, command, text, selected) {
        var previous = composing && composing.element === element, left = previous ? composing.start : Math.min(selected[0], selected[1]);
        var right = previous ? composing.end : Math.max(selected[0], selected[1]);
        var base = text.slice(0, left) + text.slice(right), start = left + command.replaceStart, end = start + command.replaceLength;
        if (!boundary(base, start) || !boundary(base, end) || start > end) return;
        var commit = command.commit || "", preedit = command.preedit || "";
        var committed = base.slice(0, start) + commit + base.slice(end), position = start + commit.length;
        if (command.selection) {
            var requested = command.selection.start;
            if (boundary(committed, requested)) position = requested;
        }
        var result = committed.slice(0, position) + preedit + committed.slice(position);
        // Replace only the changed DOM range so surrounding rich text retains its nodes.
        var first = 0, oldEnd = text.length, newEnd = result.length;
        while (first < oldEnd && first < newEnd && text.charAt(first) === result.charAt(first)) ++first;
        while (oldEnd > first && newEnd > first && text.charAt(oldEnd - 1) === result.charAt(newEnd - 1)) { --oldEnd; --newEnd; }
        if (!boundary(text, first) || !boundary(result, first)) --first;
        if (!boundary(text, oldEnd)) ++oldEnd;
        if (!boundary(result, newEnd)) ++newEnd;
        var entering = preedit.length > 0, completed = previous && (commit.length > 0 || !entering);
        var inputType = entering ? "insertCompositionText" : "insertText";
        if (element.dispatchEvent(new InputEvent("beforeinput", { bubbles: true, cancelable: true,
                inputType: inputType, data: commit + preedit, isComposing: entering })) === false) return;
        if (completed) element.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: commit }));
        if (entering && (!previous || completed)) element.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true, data: "" }));
        replace(element, text, first, oldEnd, result.slice(first, newEnd));
        composing = entering ? { element: element, start: position, end: position + preedit.length } : null;
        var caret = position + Math.max(0, Math.min(preedit.length, command.cursor));
        if (boundary(result, caret)) select(element, caret, caret);
        if (!entering && command.selection && boundary(result, position + command.selection.length)) select(element, position, position + command.selection.length);
        if (entering) element.dispatchEvent(new CompositionEvent("compositionupdate", { bubbles: true, data: preedit }));
        element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: inputType, data: commit + preedit, isComposing: entering }));
        publish();
    }
    window.__overteEditor = {
        publish: publish,
        edit: function (command) {
            var element = document.activeElement;
            if (!editable(element)) { return; }
            var text = element.value === undefined ? element.textContent : element.value, selected = selection(element);
            if (command.action === "ime") { ime(element, command, text, selected); return; }
            var start = Math.min(selected[0], selected[1]), end = Math.max(selected[0], selected[1]);
            if (composing && composing.element === element) { start = composing.start; end = composing.end; }
            if (command.replaceStart || command.replaceLength) {
                var base = composing && composing.element === element ? composing.start : selected[1];
                start = base + command.replaceStart; end = start + command.replaceLength;
                // Qt replacements count committed text, skipping the old preedit range.
                if (composing && composing.element === element) {
                    if (start > composing.start) { start += composing.end - composing.start; }
                    if (end >= composing.start) { end += composing.end - composing.start; }
                }
            }
            if (command.action === "backspace" && start === end && start > 0) {
                --start; if (!boundary(text, start)) { --start; }
            }
            if (command.action === "delete" && start === end && end < text.length) {
                ++end; if (!boundary(text, end)) { ++end; }
            }
            if (!boundary(text, start) || !boundary(text, end) || start > end) { return; }
            if (command.action === "left" || command.action === "right" || command.action === "home" || command.action === "end") {
                var next = selected[1];
                if (command.action === "home") next = text.lastIndexOf("\n", next - 1) + 1;
                else if (command.action === "end") { next = text.indexOf("\n", next); if (next < 0) next = text.length; }
                else { next = Math.max(0, Math.min(text.length, next + (command.action === "left" ? -1 : 1))); if (!boundary(text, next)) next += command.action === "left" ? -1 : 1; }
                select(element, command.extend ? selected[0] : next, next); composing = null; publish(); return;
            }
            if (command.action === "selection") {
                if (boundary(text, command.start) && boundary(text, command.start + command.length)) {
                    select(element, command.start, command.start + command.length); composing = null; publish();
                }
                return;
            }
            var insertion = command.text || "";
            var wasComposing = composing && composing.element === element;
            if (command.composing && !wasComposing) element.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true, data: "" }));
            if (element instanceof HTMLInputElement && element.type === "number") {
                element.value = text.slice(0, start) + insertion + text.slice(end);
            } else if (typeof element.setRangeText === "function") {
                element.setRangeText(insertion, start, end, "end");
            } else {
                select(element, start, end);
                document.execCommand("insertText", false, insertion);
            }
            if (command.composing) element.dispatchEvent(new CompositionEvent("compositionupdate", { bubbles: true, data: insertion }));
            else if (wasComposing) element.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: insertion }));
            composing = command.composing ? { element: element, start: start, end: start + insertion.length } : null;
            element.dispatchEvent(new InputEvent("input", { bubbles: true,
                inputType: command.composing ? "insertCompositionText" : "insertText", data: insertion,
                isComposing: command.composing === true }));
            if (command.composing && typeof command.cursor === "number") {
                var caret = start + Math.max(0, Math.min(insertion.length, command.cursor));
                if (boundary(element.value === undefined ? element.textContent : element.value, caret)) select(element, caret, caret);
            }
            publish();
        },
        blur: function () { composing = null; if (document.activeElement) { document.activeElement.blur(); } publish(); }
    };
    ["focusin", "focusout", "input", "selectionchange", "compositionend"].forEach(function (name) {
        document.addEventListener(name, publish, true);
    });
}());
