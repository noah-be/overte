//
//  ScriptHighlighting.cpp
//  interface/src
//
//  Created by Thijs Wenker on 4/15/14.
//  Copyright 2014 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "ScriptHighlighting.h"
#include <QTextDocument>

ScriptHighlighting::ScriptHighlighting(QTextDocument* parent) :
    QSyntaxHighlighter(parent)
{
    _keywordRegex = QRegularExpression("\\b(break|case|catch|continue|debugger|default|delete|do|else|finally|for|function|if|in|instanceof|new|return|switch|this|throw|try|typeof|var|void|while|with)\\b");
    _quotedTextRegex = QRegularExpression("(\"[^\"]*(\"){0,1}|\'[^\']*(\'){0,1})");
    _multiLineCommentBegin = QRegularExpression("/\\*");
    _multiLineCommentEnd = QRegularExpression("\\*/");
    _numberRegex = QRegularExpression("[0-9]+(\\.[0-9]+){0,1}");
    _singleLineComment = QRegularExpression("//[^\n]*");
    _truefalseRegex = QRegularExpression("\\b(true|false)\\b");
    _alphacharRegex = QRegularExpression("[A-Za-z]");
}

void ScriptHighlighting::highlightBlock(const QString& text) {
    this->highlightKeywords(text);
    this->formatNumbers(text);
    this->formatTrueFalse(text);
    this->formatQuotedText(text);
    this->formatComments(text);
}

void ScriptHighlighting::highlightKeywords(const QString& text) {
    auto match = _keywordRegex.match(text);
    while (match.hasMatch()) {
        const int index = match.capturedStart();
        const int length = match.capturedLength();
        setFormat(index, length, Qt::blue);
        match = _keywordRegex.match(text, index + length);
    }
}

void ScriptHighlighting::formatComments(const QString& text) {

    setCurrentBlockState(BlockStateClean);

    auto beginMatch = _multiLineCommentBegin.match(text);
    int start = (previousBlockState() != BlockStateInMultiComment) ? beginMatch.capturedStart() : 0;

    while (start > -1) {
        const auto endMatch = _multiLineCommentEnd.match(text, start);
        const int end = endMatch.capturedStart();
        const int length = (end == -1 ? text.length() : (end + endMatch.capturedLength())) - start;
        setFormat(start, length, Qt::lightGray);
        beginMatch = _multiLineCommentBegin.match(text, start + length);
        start = beginMatch.capturedStart();
        if (end == -1) {
            setCurrentBlockState(BlockStateInMultiComment);
        }
    }

    auto commentMatch = _singleLineComment.match(text);
    while (commentMatch.hasMatch()) {
        const int index = commentMatch.capturedStart();
        const int length = commentMatch.capturedLength();
        auto quotedMatch = _quotedTextRegex.match(text);
        int quoted_index = quotedMatch.capturedStart();
        bool valid = true;
        while (quoted_index >= 0 && valid) {
            const int quoted_length = quotedMatch.capturedLength();
            if (quoted_index <= index && index <= (quoted_index + quoted_length)) {
                valid = false;
            }
            quotedMatch = _quotedTextRegex.match(text, quoted_index + quoted_length);
            quoted_index = quotedMatch.capturedStart();
        }

        if (valid) {
            setFormat(index, length, Qt::lightGray);
        }
        commentMatch = _singleLineComment.match(text, index + length);
    }
}

void ScriptHighlighting::formatQuotedText(const QString& text){
    auto match = _quotedTextRegex.match(text);
    while (match.hasMatch()) {
        const int index = match.capturedStart();
        const int length = match.capturedLength();
        setFormat(index, length, Qt::red);
        match = _quotedTextRegex.match(text, index + length);
    }
}

void ScriptHighlighting::formatNumbers(const QString& text){
    auto match = _numberRegex.match(text);
    while (match.hasMatch()) {
        const int index = match.capturedStart();
        const int length = match.capturedLength();
        if (index == 0 || _alphacharRegex.match(text, index - 1).capturedStart() != (index - 1)) {
            setFormat(index, length, Qt::green);
        }
        match = _numberRegex.match(text, index + length);
    }
}

void ScriptHighlighting::formatTrueFalse(const QString& text){
    auto match = _truefalseRegex.match(text);
    while (match.hasMatch()) {
        const int index = match.capturedStart();
        const int length = match.capturedLength();
        QFont* font = new QFont(this->document()->defaultFont());
        font->setBold(true);
        setFormat(index, length, *font);
        match = _truefalseRegex.match(text, index + length);
    }
}
