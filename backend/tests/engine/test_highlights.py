import pytest
from app.engine.highlights import build_transcript_text

def test_build_transcript_text_with_speakers():
    transcript = {
        "segments": [
            {"start": 0.0, "speaker": "SPEAKER_00", "text": " Hello world. "},
            {"start": 5.234, "speaker": "SPEAKER_01", "text": "Hi there."},
        ]
    }
    result = build_transcript_text(transcript)
    expected = "[0][0.0s] [SPEAKER_00]: Hello world.\n[1][5.2s] [SPEAKER_01]: Hi there."
    assert result == expected

def test_build_transcript_text_without_speakers():
    transcript = {
        "segments": [
            {"start": 0.0, "text": " Hello world. "},
            {"start": 5.26, "text": "Hi there."},
        ]
    }
    result = build_transcript_text(transcript)
    expected = "[0][0.0s] Hello world.\n[1][5.3s] Hi there."
    assert result == expected

def test_build_transcript_text_mixed():
    transcript = {
        "segments": [
            {"start": 1.11, "speaker": "SPEAKER_00", "text": "  First part."},
            {"start": 2.22, "text": "Second part."},
            {"start": 3.33, "speaker": "SPEAKER_02", "text": "Third part.  "},
        ]
    }
    result = build_transcript_text(transcript)
    expected = "[0][1.1s] [SPEAKER_00]: First part.\n[1][2.2s] Second part.\n[2][3.3s] [SPEAKER_02]: Third part."
    assert result == expected

def test_build_transcript_text_empty_segments():
    transcript = {"segments": []}
    result = build_transcript_text(transcript)
    assert result == ""

def test_build_transcript_text_missing_segments():
    transcript = {}
    result = build_transcript_text(transcript)
    assert result == ""
