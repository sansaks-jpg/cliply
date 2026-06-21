from typing import Any, Dict, List
import pytest

from app.engine.subtitles import build_karaoke_fill

def test_build_karaoke_fill_basic():
    """Test basic karaoke fill with simple text and segment duration."""
    segments = [
        {
            "start_time": 0.0,
            "end_time": 1.0,
            "text": "Hello world"
        }
    ]
    style = {
        "_font_size": 48,
        "_play_res_x": 1080
    }

    lines = build_karaoke_fill(segments, style)

    assert len(lines) == 1
    # Check that it uses \k instead of \kf (which is the default in _build_karaoke_base)
    assert r"{\k" in lines[0]
    assert "Hello" in lines[0]
    assert "world" in lines[0]

    # 1.0s duration = 100 centiseconds
    # Since there are 2 words, each word should get 50 centiseconds: {\k50}Hello {\k50}world
    assert r"{\k50}Hello" in lines[0]
    assert r"{\k50}world" in lines[0]


def test_build_karaoke_fill_with_word_timings():
    """Test karaoke fill when precise word timings are provided."""
    segments = [
        {
            "start_time": 0.0,
            "end_time": 1.0,
            "text": "Hello fast world",
            "words": [
                {"start": 0.0, "end": 0.2, "word": "Hello"},
                {"start": 0.2, "end": 0.4, "word": "fast"},
                {"start": 0.4, "end": 1.0, "word": "world"},
            ]
        }
    ]
    style = {}

    lines = build_karaoke_fill(segments, style)

    assert len(lines) == 1
    # The durations in cs: 20, 20, 60
    assert r"{\k20}Hello" in lines[0]
    assert r"{\k20}fast" in lines[0]
    assert r"{\k60}world" in lines[0]


def test_build_karaoke_fill_empty_segments():
    """Test with an empty list of segments."""
    assert build_karaoke_fill([], {}) == []


def test_build_karaoke_fill_empty_text():
    """Test with a segment that has empty text."""
    segments = [
        {
            "start_time": 0.0,
            "end_time": 1.0,
            "text": "   "
        }
    ]
    assert build_karaoke_fill(segments, {}) == []


def test_build_karaoke_fill_invalid_duration():
    """Test with segments that have end_time <= start_time."""
    segments = [
        {
            "start_time": 1.0,
            "end_time": 0.5,
            "text": "Backward"
        },
        {
            "start_time": 1.0,
            "end_time": 1.0,
            "text": "Instant"
        }
    ]
    assert build_karaoke_fill(segments, {}) == []


def test_build_karaoke_fill_with_blur():
    """Test that blur tag is correctly prepended if style has blur."""
    segments = [
        {
            "start_time": 0.0,
            "end_time": 0.5,
            "text": "Glow"
        }
    ]
    style = {
        "blur": 2
    }

    lines = build_karaoke_fill(segments, style)
    assert len(lines) == 1
    assert lines[0].startswith(r"Dialogue: ")
    assert r"{\blur2}" in lines[0]
