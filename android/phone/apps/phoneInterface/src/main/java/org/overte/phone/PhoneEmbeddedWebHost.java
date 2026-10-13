// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
package org.overte.phone;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.graphics.Color;
import android.graphics.Rect;
import android.net.Uri;
import android.provider.Settings;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.MimeTypeMap;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.util.IdentityHashMap;
import java.util.ArrayList;
import org.overte.web.EmbeddedWebHost;
import org.overte.web.EmbeddedWebView;
import org.overte.web.WebFilePickerState;

/** Native tablet content stays inside the real Qt surface; product UI stays outside it. */
final class PhoneEmbeddedWebHost implements EmbeddedWebHost {
    private final PhoneInterfaceActivity activity;
    private final IdentityHashMap<WebView, Card> cards = new IdentityHashMap<>();
    private FrameLayout overlay;
    private int sceneWidth, sceneHeight;
    private boolean initialized, resumed;
    private final WebFilePickerState<Uri[]> files = new WebFilePickerState<>();
    PhoneEmbeddedWebHost(PhoneInterfaceActivity activity) { this.activity = activity; }
    void initialize() {
        if (initialized) return;
        activity.prepareNativeWeb();
        EmbeddedWebView.initialize(this); initialized = true;
    }
    void foreground(boolean value) {
        resumed = value;
        if (initialized) EmbeddedWebView.setForeground(this, isForeground());
        files.deliver(isForeground());
    }
    void windowFocus() {
        if (initialized) EmbeddedWebView.setForeground(this, isForeground());
        files.deliver(isForeground()); reposition();
    }
    void scene(int width, int height) { sceneWidth = width; sceneHeight = height; reposition(); }
    void detach() {
        files.cancel();
        if (initialized) EmbeddedWebView.detach(this);
        initialized = false;
        if (overlay != null && overlay.getParent() instanceof ViewGroup) ((ViewGroup) overlay.getParent()).removeView(overlay);
        overlay = null; cards.clear();
    }
    @Override public Activity activity() { return activity; }
    @Override public boolean isForeground() { return resumed && activity.hasWindowFocus() && !activity.isFinishing(); }
    private View qtSurface(View view) {
        if (view.getClass().getName().equals("org.qtproject.qt5.android.QtSurface")) return view;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int index = 0; index < group.getChildCount(); ++index) { View found = qtSurface(group.getChildAt(index)); if (found != null) return found; }
        }
        return null;
    }
    @Override public boolean placeTabletView(WebView view, Rect bounds) { return placeTabletView(view, bounds, bounds); }
    @Override public boolean placeTabletView(WebView view, Rect bounds, Rect sceneClip) {
        ViewGroup content = activity.findViewById(android.R.id.content);
        if (content == null) return false;
        if (overlay == null) {
            overlay = new FrameLayout(activity); overlay.setClipChildren(true); overlay.setClipToPadding(true);
            content.addView(overlay, new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
            content.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> reposition());
        }
        Card card = cards.get(view);
        if (card == null) { card = new Card(view); cards.put(view, card); overlay.addView(card.frame); }
        card.bounds = new Rect(bounds); card.clip = new Rect(sceneClip);
        return position(card);
    }
    private boolean position(Card card) {
        View surface = qtSurface(activity.getWindow().getDecorView());
        if (surface == null || overlay == null || sceneWidth <= 1 || sceneHeight <= 1) { card.frame.setVisibility(View.GONE); return false; }
        int[] origin = new int[2], base = new int[2]; surface.getLocationOnScreen(origin); overlay.getLocationOnScreen(base);
        Rect visible = new Rect(); if (!surface.getGlobalVisibleRect(visible)) { card.frame.setVisibility(View.GONE); return false; }
        if (card.clip.isEmpty()) { card.frame.setVisibility(View.GONE); return true; }
        int[] screenClip = PhoneWebGeometry.map(sceneWidth, sceneHeight,
            new int[] {card.clip.left, card.clip.top, card.clip.right, card.clip.bottom},
            new int[] {origin[0], origin[1], origin[0] + surface.getWidth(), origin[1] + surface.getHeight()},
            new int[] {visible.left, visible.top, visible.right, visible.bottom});
        if (screenClip == null) { card.frame.setVisibility(View.GONE); return true; }
        int[] result = PhoneWebGeometry.map(sceneWidth, sceneHeight,
            new int[] {card.bounds.left, card.bounds.top, card.bounds.right, card.bounds.bottom},
            new int[] {origin[0], origin[1], origin[0] + surface.getWidth(), origin[1] + surface.getHeight()},
            new int[] {screenClip[4], screenClip[5], screenClip[6], screenClip[7]});
        if (result == null) { card.frame.setVisibility(View.GONE); return false; }
        FrameLayout.LayoutParams frame = new FrameLayout.LayoutParams(result[6] - result[4], result[7] - result[5]);
        frame.leftMargin = result[4] - base[0]; frame.topMargin = result[5] - base[1]; card.frame.setLayoutParams(frame);
        int fullWidth = result[2] - result[0], fullHeight = result[3] - result[1];
        int bannerHeight = 0;
        if (card.banner.getVisibility() == View.VISIBLE) {
            card.banner.measure(View.MeasureSpec.makeMeasureSpec(fullWidth, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(Math.max(1, fullHeight / 3), View.MeasureSpec.AT_MOST));
            bannerHeight = Math.min(card.banner.getMeasuredHeight(), Math.max(0, fullHeight - 1));
        }
        FrameLayout.LayoutParams notice = new FrameLayout.LayoutParams(fullWidth, bannerHeight);
        notice.leftMargin = result[0] - result[4]; notice.topMargin = result[1] - result[5]; card.banner.setLayoutParams(notice);
        FrameLayout.LayoutParams browser = new FrameLayout.LayoutParams(fullWidth, fullHeight - bannerHeight);
        browser.leftMargin = result[0] - result[4]; browser.topMargin = result[1] - result[5] + bannerHeight; card.web.setLayoutParams(browser);
        card.frame.setVisibility(card.web.getVisibility() == View.VISIBLE ? View.VISIBLE : View.GONE);
        return true;
    }
    private void reposition() {
        for (Card card : new ArrayList<>(cards.values())) position(card);
        if (initialized) EmbeddedWebView.relayout(this);
    }
    @Override public void removeTabletView(WebView view) { Card card = cards.remove(view); if (card != null && overlay != null) overlay.removeView(card.frame); }
    boolean back() {
        for (Card card : cards.values()) {
            if (card.frame.getVisibility() == View.VISIBLE && card.web.hasFocus() && card.web.canGoBack()) { card.web.goBack(); return true; }
        }
        return false;
    }
    @Override public boolean openExternal(Uri url) {
        if (!isForeground() || !("https".equals(url.getScheme()) || "http".equals(url.getScheme())) || url.getUserInfo() != null) return false;
        try { activity.startActivity(Intent.createChooser(new Intent(Intent.ACTION_VIEW, url).addCategory(Intent.CATEGORY_BROWSABLE), "Open in browser")); return true; }
        catch (ActivityNotFoundException | SecurityException unavailable) { return false; }
    }
    @Override public boolean chooseFiles(ValueCallback<Uri[]> result, WebChromeClient.FileChooserParams request) {
        if (!isForeground() || request.getMode() != WebChromeClient.FileChooserParams.MODE_OPEN && request.getMode() != WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE) return false;
        int requestCode = files.begin(result::onReceiveValue);
        if (requestCode == 0) return false;
        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
        picker.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, request.getMode() == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE);
        ArrayList<String> types = new ArrayList<>();
        for (String value : request.getAcceptTypes()) {
            String mime = value.startsWith(".") ? MimeTypeMap.getSingleton().getMimeTypeFromExtension(value.substring(1).toLowerCase(java.util.Locale.ROOT)) : value;
            if (mime != null && mime.matches("[A-Za-z0-9!#$&^_.+\\-]+/[A-Za-z0-9!#$&^_.+*\\-]+") && types.size() < 16) types.add(mime);
        }
        if (!types.isEmpty()) picker.putExtra(Intent.EXTRA_MIME_TYPES, types.toArray(new String[0]));
        try { activity.startActivityForResult(picker, requestCode); return true; }
        catch (ActivityNotFoundException | SecurityException unavailable) { files.cancel(); return false; }
    }
    boolean fileResult(int requestCode, int resultCode, Intent data) {
        if (!files.owns(requestCode)) return false;
        ArrayList<Uri> values = new ArrayList<>();
        if (resultCode == Activity.RESULT_OK && data != null) {
            ClipData clips = data.getClipData();
            if (clips != null) for (int index = 0; index < Math.min(16, clips.getItemCount()); ++index) addSelected(values, clips.getItemAt(index).getUri());
            else addSelected(values, data.getData());
        }
        return files.receive(requestCode, values.isEmpty() ? null : values.toArray(new Uri[0]), isForeground());
    }
    private static void addSelected(ArrayList<Uri> values, Uri value) { if (value != null && "content".equals(value.getScheme()) && value.getAuthority() != null) values.add(value); }
    @Override public void statusChanged(WebView view, int status) {
        Card card = cards.get(view); if (card == null) return;
        card.message.setText(message(status)); card.banner.setVisibility(status == 0 ? View.GONE : View.VISIBLE);
        card.update.setVisibility(status == EmbeddedWebView.BRIDGE_UNAVAILABLE ? View.VISIBLE : View.GONE);
        position(card);
    }
    @Override public void diagnostic(int status) { /* Generic user status is already visible; no page data is logged. */ }
    private static String message(int status) {
        switch (status) {
            case 1: return "This page needs a newer Android System WebView for the Overte bridge.";
            case 2: return "The page could not be loaded. Use Reload to try again.";
            case 3: return "The WebView stopped. Reopen this page.";
            case 4: return "The tablet browser could not be placed on screen.";
            case 5: return "No file picker is available.";
            case 6: return "This page has no approved application resource source.";
            case 7: return "The page script could not be loaded. Use Reload to try again.";
            case 8: return "No external browser is available.";
            case 9: return "Return to the original page to use its Overte bridge.";
            default: return "";
        }
    }
    private final class Card {
        final WebView web; final FrameLayout frame; final LinearLayout banner; final TextView message; final Button update;
        Rect bounds = new Rect(), clip = new Rect();
        Card(WebView view) {
            web = view; frame = new FrameLayout(activity); frame.setClipChildren(true); frame.setClipToPadding(true); frame.addView(view);
            banner = new LinearLayout(activity); banner.setOrientation(LinearLayout.HORIZONTAL); banner.setBackgroundColor(Color.rgb(38, 38, 38));
            message = new TextView(activity); message.setTextColor(Color.WHITE); message.setPadding(12, 8, 12, 8);
            banner.addView(message, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
            update = new Button(activity); update.setText("Update WebView"); banner.addView(update);
            update.setOnClickListener(button -> {
                PackageInfo provider = WebView.getCurrentWebViewPackage();
                if (provider == null) { message.setText("Enable an Android System WebView provider in Android settings."); return; }
                try { activity.startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", provider.packageName, null))); }
                catch (ActivityNotFoundException | SecurityException unavailable) { message.setText("Update the active WebView provider in Android settings."); }
            });
            frame.addView(banner, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
            banner.setVisibility(View.GONE);
        }
    }
}
