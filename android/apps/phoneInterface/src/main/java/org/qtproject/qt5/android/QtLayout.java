/****************************************************************************
**
** Copyright (C) 2022 The Qt Company Ltd.
** Copyright (C) 2012 BogDan Vatra <bogdan@kde.org>
** SPDX-License-Identifier: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only
**
****************************************************************************/

package org.qtproject.qt5.android;

import android.app.Activity;
import android.content.Context;
import android.os.Build;
import android.util.AttributeSet;
import android.util.DisplayMetrics;
import android.view.Display;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.WindowMetrics;

/**
 * Phone-local Qt 5 layout with an Android 11+ orientation-metrics fix.
 *
 * Android may report the Activity surface in the display's natural
 * orientation while maximumWindowMetrics already follows the requested
 * landscape orientation. Qt 5 must receive both pairs in the same
 * orientation or it creates a small compatibility surface.
 */
public class QtLayout extends ViewGroup {
    private Runnable startApplicationRunnable;
    private int activityDisplayRotation = -1;
    private int ownDisplayRotation = -1;
    private int nativeOrientation = -1;

    public QtLayout(Context context, Runnable startRunnable) {
        super(context);
        startApplicationRunnable = startRunnable;
    }

    public QtLayout(Context context, AttributeSet attrs) {
        super(context, attrs);
    }

    public QtLayout(Context context, AttributeSet attrs, int defStyle) {
        super(context, attrs, defStyle);
    }

    public void setActivityDisplayRotation(int rotation) {
        activityDisplayRotation = rotation;
    }

    public void setNativeOrientation(int orientation) {
        nativeOrientation = orientation;
    }

    public int displayRotation() {
        return ownDisplayRotation;
    }

    @Override
    protected void onSizeChanged(int width, int height, int oldWidth, int oldHeight) {
        Activity activity = (Activity) getContext();
        WindowManager windowManager = activity.getWindowManager();
        Display display;
        int maximumWidth;
        int maximumHeight;

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            display = windowManager.getDefaultDisplay();
            DisplayMetrics maximumMetrics = new DisplayMetrics();
            display.getRealMetrics(maximumMetrics);
            maximumWidth = maximumMetrics.widthPixels;
            maximumHeight = maximumMetrics.heightPixels;
        } else {
            display = activity.getDisplay();
            WindowMetrics maximumMetrics = windowManager.getMaximumWindowMetrics();
            maximumWidth = maximumMetrics.getBounds().width();
            maximumHeight = maximumMetrics.getBounds().height();
        }

        int applicationWidth = width;
        int applicationHeight = height;
        if ((applicationWidth > applicationHeight) != (maximumWidth > maximumHeight)) {
            int swapped = applicationWidth;
            applicationWidth = applicationHeight;
            applicationHeight = swapped;
        }

        DisplayMetrics metrics = activity.getResources().getDisplayMetrics();
        QtNative.setApplicationDisplayMetrics(
                maximumWidth, maximumHeight, applicationWidth, applicationHeight,
                metrics.xdpi, metrics.ydpi, metrics.scaledDensity,
                metrics.density, display.getRefreshRate());

        int newRotation = display.getRotation();
        if (ownDisplayRotation != activityDisplayRotation
                && newRotation == activityDisplayRotation) {
            QtNative.handleOrientationChanged(newRotation, nativeOrientation);
        }
        ownDisplayRotation = newRotation;

        if (startApplicationRunnable != null) {
            startApplicationRunnable.run();
            startApplicationRunnable = null;

            final int finalMaximumWidth = maximumWidth;
            final int finalMaximumHeight = maximumHeight;
            final int finalApplicationWidth = applicationWidth;
            final int finalApplicationHeight = applicationHeight;
            final double finalXDpi = metrics.xdpi;
            final double finalYDpi = metrics.ydpi;
            final double finalScaledDensity = metrics.scaledDensity;
            final double finalDensity = metrics.density;
            final float finalRefreshRate = display.getRefreshRate();
            postDelayed(() -> QtNative.setApplicationDisplayMetrics(
                    finalMaximumWidth, finalMaximumHeight,
                    finalApplicationWidth, finalApplicationHeight,
                    finalXDpi, finalYDpi, finalScaledDensity, finalDensity,
                    finalRefreshRate), 1000);
        }
    }

    @Override
    protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
        measureChildren(widthMeasureSpec, heightMeasureSpec);
        int maximumWidth = 0;
        int maximumHeight = 0;
        for (int index = 0; index < getChildCount(); ++index) {
            View child = getChildAt(index);
            if (child.getVisibility() != GONE) {
                LayoutParams params = (LayoutParams) child.getLayoutParams();
                maximumWidth = Math.max(maximumWidth, params.x + child.getMeasuredWidth());
                maximumHeight = Math.max(maximumHeight, params.y + child.getMeasuredHeight());
            }
        }
        maximumWidth = Math.max(maximumWidth, getSuggestedMinimumWidth());
        maximumHeight = Math.max(maximumHeight, getSuggestedMinimumHeight());
        setMeasuredDimension(
                resolveSize(maximumWidth, widthMeasureSpec),
                resolveSize(maximumHeight, heightMeasureSpec));
    }

    @Override
    protected void onLayout(boolean changed, int left, int top, int right, int bottom) {
        for (int index = 0; index < getChildCount(); ++index) {
            View child = getChildAt(index);
            if (child.getVisibility() != GONE) {
                LayoutParams params = (LayoutParams) child.getLayoutParams();
                child.layout(params.x, params.y,
                        params.x + child.getMeasuredWidth(),
                        params.y + child.getMeasuredHeight());
            }
        }
    }

    @Override
    protected ViewGroup.LayoutParams generateDefaultLayoutParams() {
        return new LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT, 0, 0);
    }

    @Override
    protected boolean checkLayoutParams(ViewGroup.LayoutParams params) {
        return params instanceof LayoutParams;
    }

    @Override
    protected ViewGroup.LayoutParams generateLayoutParams(ViewGroup.LayoutParams params) {
        return new LayoutParams(params);
    }

    public void moveChild(View view, int index) {
        if (view == null || indexOfChild(view) == -1) {
            return;
        }
        detachViewFromParent(view);
        requestLayout();
        invalidate();
        attachViewToParent(view, index, view.getLayoutParams());
    }

    public void setLayoutParams(
            View childView, ViewGroup.LayoutParams params, boolean forceRedraw) {
        if (childView == null || !checkLayoutParams(params)) {
            return;
        }
        if (this == childView.getParent()) {
            childView.setLayoutParams(params);
            if (forceRedraw) {
                invalidate();
            }
        } else {
            addView(childView, params);
        }
    }

    public static class LayoutParams extends ViewGroup.LayoutParams {
        public int x;
        public int y;

        public LayoutParams(int width, int height, int x, int y) {
            super(width, height);
            this.x = x;
            this.y = y;
        }

        public LayoutParams(ViewGroup.LayoutParams source) {
            super(source);
        }
    }
}
