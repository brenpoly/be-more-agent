import unittest
import sys
import re


def clean_transcription(transcription):
    transcription = transcription.strip()
    if re.fullmatch(r"\[[^\]]+\]", transcription):
        return ""
    return transcription


class TestClean(unittest.TestCase):
    def test_blank(self):
        self.assertEqual(clean_transcription("[BLANK_AUDIO]"), "")
    def test_no_speech(self):
        self.assertEqual(clean_transcription("[NO_SPEECH]"), "")
    def test_normal(self):
        self.assertEqual(clean_transcription("hello world"), "hello world")
    def test_with_brackets_inside(self):
        self.assertEqual(clean_transcription("say [ok]"), "say [ok]")


def test_transcription_cleanup():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestClean)
    result = unittest.TestResult()
    suite.run(result)
    for fail in result.failures + result.errors:
        print(fail)
    return result.wasSuccessful()


if __name__ == "__main__":
    sys.exit(0 if test_transcription_cleanup() else 1)