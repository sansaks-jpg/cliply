import pytest
import json
from app.engine.highlights import _parse_json_loose

def test_parse_json_loose_plain_json():
    raw = '{"key": "value", "number": 42}'
    result = _parse_json_loose(raw)
    assert result == {"key": "value", "number": 42}

def test_parse_json_loose_with_json_markdown():
    raw = '```json\n{"key": "value"}\n```'
    result = _parse_json_loose(raw)
    assert result == {"key": "value"}

def test_parse_json_loose_with_plain_markdown():
    raw = '```\n{"key": "value"}\n```'
    result = _parse_json_loose(raw)
    assert result == {"key": "value"}

def test_parse_json_loose_with_extra_text_around_json():
    raw = 'Here is the response:\n```json\n{"key": "value"}\n```\nHope it helps!'
    # Due to regex in `_parse_json_loose`, it will strip ``` at start/end, but won't match here because of the extra text.
    # It will fall into `except json.JSONDecodeError` and use `find("{")` and `rfind("}")`.
    result = _parse_json_loose(raw)
    assert result == {"key": "value"}

def test_parse_json_loose_with_extra_text_without_markdown():
    raw = 'Some intro text\n{"key": "value", "nested": {"a": 1}}\nSome outro text'
    result = _parse_json_loose(raw)
    assert result == {"key": "value", "nested": {"a": 1}}

def test_parse_json_loose_malformed_json():
    raw = '{"key": "value", }'
    with pytest.raises(json.JSONDecodeError):
        _parse_json_loose(raw)

def test_parse_json_loose_no_braces():
    raw = 'Just some plain text without any JSON object'
    with pytest.raises(json.JSONDecodeError):
        _parse_json_loose(raw)
