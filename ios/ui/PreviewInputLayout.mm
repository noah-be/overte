// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#import "PreviewInputLayout.h"

void installPreviewKeyboardLayout(UIView* view, UILabel* footer) {
    // UIKit already includes the bottom safe area in its docked keyboard guide.
    // Do not add the safe inset a second time or shrink the scene for floating IME.
    view.keyboardLayoutGuide.followsUndockedKeyboard = NO;
    [footer.bottomAnchor constraintEqualToAnchor:view.keyboardLayoutGuide.topAnchor constant:-16].active = YES;
}

void updatePreviewInputLayout(UIView* view, UIStackView* inputRow) {
    CGFloat width = view.bounds.size.width - view.safeAreaInsets.left - view.safeAreaInsets.right;
    BOOL vertical = width < 480 || UIContentSizeCategoryIsAccessibilityCategory(
        view.traitCollection.preferredContentSizeCategory);
    inputRow.axis = vertical ? UILayoutConstraintAxisVertical : UILayoutConstraintAxisHorizontal;
}
