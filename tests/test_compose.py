from demolab.compose import build_segments, map_time, tighten


def ev(t, kind, **kw):
    return {"t": t, "kind": kind, **kw}


def test_long_wait_is_fast_forwarded_and_short_one_is_not():
    events = [ev(0, "seg_start"), ev(1, "ff_start", what="x"), ev(61, "ff_end"),
              ev(62, "ff_start", what="y"), ev(63, "ff_end"), ev(64, "seg_end")]
    segs = build_segments(events, 0, 64)
    labels = [s[3] for s in segs]
    assert labels.count("x") == 1 and "y" not in labels
    ff = next(s for s in segs if s[3] == "x")
    assert 3.0 <= ff[2] <= 8.0


def test_narration_plays_at_1x_and_silence_is_tightened():
    events = [ev(0, "seg_start"), ev(2, "say", dur=5.0), ev(20, "seg_end")]
    segs = tighten(build_segments(events, 0, 20), events)
    assert map_time(segs, 7) - map_time(segs, 2) == 5.0      # the clip keeps its length
    assert map_time(segs, 20) < 20 - 7                       # 13 s of silence after it shrinks
