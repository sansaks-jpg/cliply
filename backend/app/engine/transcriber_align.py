"""Forced alignment: attach Groq word-level timestamps to YouTube/Gemini segments.

YouTube transcripts have accurate text but only segment-level timestamps (3-10s blocks),
which causes karaoke subtitles to drift from actual speech. Groq Whisper provides
per-word timestamps but transcribes from audio, sometimes with worse phrasing/
speaker labels than YT/Gemini.

This module merges them: keep YT/Gemini segment text, distribute timestamps from
matching Groq words. Result: per-word `start`/`end` synced to lips, while preserving
the higher-quality source text.
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _norm(word: str) -> str:
    return _PUNCT_RE.sub("", word).lower().strip()


def _interpolate(words_in_seg: List[str], t0: float, t1: float) -> List[Dict[str, Any]]:
    """Even split when no Groq match — fallback only."""
    n = len(words_in_seg)
    if n == 0 or t1 <= t0:
        return []
    step = (t1 - t0) / n
    return [
        {"word": w, "start": t0 + i * step, "end": t0 + (i + 1) * step}
        for i, w in enumerate(words_in_seg)
    ]


def align_words(
    segments: List[Dict[str, Any]],
    groq_words: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Attach per-word timestamps from `groq_words` to each segment in `segments`.

    For each segment, take the Groq words whose mid-time falls within [start, end],
    then SequenceMatcher them against the segment's own words. Matched words inherit
    Groq timestamps; unmatched words are interpolated between neighbouring matches.

    Returns a new list of segments with `words` key populated. Original list untouched.
    """
    if not segments:
        return []
    if not groq_words:
        log.info("[align] no Groq words available, returning segments unchanged")
        return [dict(s) for s in segments]

    groq_indexed = sorted(
        ({"word": w["word"], "start": float(w["start"]), "end": float(w["end"]),
          "mid": (float(w["start"]) + float(w["end"])) / 2.0}
         for w in groq_words if w.get("word")),
        key=lambda x: x["mid"],
    )

    aligned: List[Dict[str, Any]] = []
    interp_total = 0
    matched_total = 0

    for seg in segments:
        t0 = float(seg.get("start", 0.0))
        t1 = float(seg.get("end", t0))
        text = (seg.get("text") or "").strip()
        seg_words_raw = text.split()
        if not seg_words_raw or t1 <= t0:
            aligned.append(dict(seg))
            continue

        win_lo = t0 - 0.3
        win_hi = t1 + 0.3
        window = [g for g in groq_indexed if win_lo <= g["mid"] <= win_hi]

        if not window:
            new_seg = dict(seg)
            new_seg["words"] = _interpolate(seg_words_raw, t0, t1)
            interp_total += len(seg_words_raw)
            aligned.append(new_seg)
            continue

        seg_norm = [_norm(w) for w in seg_words_raw]
        win_norm = [_norm(g["word"]) for g in window]

        matcher = SequenceMatcher(a=seg_norm, b=win_norm, autojunk=False)
        per_word_ts: List[Optional[Dict[str, Any]]] = [None] * len(seg_words_raw)
        for block in matcher.get_matching_blocks():
            for k in range(block.size):
                i = block.a + k
                j = block.b + k
                g = window[j]
                per_word_ts[i] = {
                    "word": seg_words_raw[i],
                    "start": g["start"],
                    "end": g["end"],
                }
                matched_total += 1

        last_anchor_t = t0
        i = 0
        while i < len(per_word_ts):
            if per_word_ts[i] is not None:
                last_anchor_t = per_word_ts[i]["end"]
                i += 1
                continue
            j = i
            while j < len(per_word_ts) and per_word_ts[j] is None:
                j += 1
            next_anchor_t = per_word_ts[j]["start"] if j < len(per_word_ts) else t1
            gap_len = j - i
            span = max(0.0, next_anchor_t - last_anchor_t)
            step = span / gap_len if gap_len else 0.0
            for k in range(gap_len):
                ws = last_anchor_t + k * step
                we = last_anchor_t + (k + 1) * step if step > 0 else ws + 0.05
                per_word_ts[i + k] = {"word": seg_words_raw[i + k], "start": ws, "end": we}
                interp_total += 1
            i = j

        prev_end = t0
        for w in per_word_ts:
            assert w is not None
            w["start"] = max(t0, min(t1, w["start"]))
            w["end"] = max(t0, min(t1, w["end"]))
            if w["start"] < prev_end:
                w["start"] = prev_end
            if w["end"] <= w["start"]:
                w["end"] = w["start"] + 0.05
            prev_end = w["end"]

        new_seg = dict(seg)
        new_seg["words"] = per_word_ts
        aligned.append(new_seg)

    total = matched_total + interp_total
    log.info(
        "[align] attached word timestamps: %d total, %d via Groq match, %d interpolated",
        total, matched_total, interp_total,
    )
    return aligned


if __name__ == "__main__":
    segs = [
        {"start": 0.0, "end": 3.0, "text": "Halo apa kabar semuanya"},
        {"start": 3.0, "end": 5.0, "text": "Selamat datang"},
    ]
    groq = [
        {"word": "halo", "start": 0.10, "end": 0.45},
        {"word": "apa", "start": 0.50, "end": 0.80},
        {"word": "kabar", "start": 0.85, "end": 1.30},
        {"word": "semuanya", "start": 1.40, "end": 2.10},
        {"word": "selamat", "start": 3.05, "end": 3.55},
        {"word": "datang", "start": 3.60, "end": 4.10},
    ]
    out = align_words(segs, groq)
    assert len(out[0]["words"]) == 4
    assert abs(out[0]["words"][0]["start"] - 0.10) < 0.01
    assert abs(out[0]["words"][3]["end"] - 2.10) < 0.01
    assert len(out[1]["words"]) == 2

    segs2 = [{"start": 0.0, "end": 2.0, "text": "halo dunia indah sekali"}]
    groq2 = [
        {"word": "halo", "start": 0.10, "end": 0.40},
        {"word": "sekali", "start": 1.70, "end": 1.95},
    ]
    out2 = align_words(segs2, groq2)
    assert len(out2[0]["words"]) == 4
    assert 0.4 <= out2[0]["words"][1]["start"] <= 1.7
    print("OK")
