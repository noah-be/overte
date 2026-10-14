#!/usr/bin/env python3
"""Structural lifetime guard; does not execute UIKit/Photos or Clang Blocks.

Clang Blocks preserve captured C++ reference types. Escaping callback entry
points must therefore own their request and returned payload by value. The
negative control restores the original dangling-reference signature.
"""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]

def owned_arguments(source, function):
    signature=re.search(r'(?:void|bool) '+re.escape(function)+r'\(([^\n]+)\)\s*\{',source)
    return bool(signature) and not re.search(r'&\s*(?:operation|status|error|caption|filter)\b',signature[1])

class Lifetime(unittest.TestCase):
    def test_escaping_native_request_arguments_are_owned(self):
        paths={"ios/snapshot/IOSSnapshotAdapter.mm":('dismissShare','cancelNative','saveToPhotos','shareWithSystem'),
               "ios/documents/IOSDocumentPicker.mm":('finish','importDocuments')}
        for file,functions in paths.items():
            source=(ROOT/file).read_text()
            for function in functions:
                with self.subTest(file=file,function=function):
                    self.assertTrue(owned_arguments(source,function))
                    unsafe=re.sub(r'(void '+re.escape(function)+r'\()std::shared_ptr<([^>]+)> operation',
                        r'\1const std::shared_ptr<\2>\& operation',source)
                    self.assertNotEqual(unsafe,source)
                    self.assertFalse(owned_arguments(unsafe,function))
        snapshot=(ROOT/'ios/snapshot/IOSSnapshotAdapter.mm').read_text()
        for name in ('status','error'):
            signature=re.search(r'void dismissShare\([^\n]+',snapshot)[0]
            self.assertIn('QString '+name,signature)
            unsafe=snapshot.replace(signature,signature.replace('QString '+name,'const QString& '+name))
            self.assertFalse(owned_arguments(unsafe,'dismissShare'))
        documents=(ROOT/'ios/documents/IOSDocumentPicker.mm').read_text()
        self.assertTrue(owned_arguments(documents,'openPicker'))
        for name in ('caption','filter'):
            unsafe=documents.replace('QString '+name,'const QString& '+name)
            self.assertFalse(owned_arguments(unsafe,'openPicker'))

if __name__=='__main__':unittest.main()
