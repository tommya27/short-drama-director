"""剧情结构层离线样例：契约、节拍、7 项检查、剧本/分镜渲染（不联网）。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.director_core.dramatic import (  # noqa: E402
    BEAT_TEMPLATE, assess, build_contract, default_beats, ensure_dramatic,
    normalize_event_fields, render_screenplay, render_storyboard,
)

SPEC = {
    "location": "董事会会议室", "goal": "让董事会暂停表决",
    "characters": [
        {"id": "a", "name": "顾沉", "role": "protagonist", "goal": "阻止表决",
         "hidden_goal": "查出谁改了合同"},
        {"id": "b", "name": "林岚", "role": "antagonist", "goal": "推动表决",
         "hidden_goal": "掩盖授权缺失", "secret": "授权记录是她抽走的"},
        {"id": "c", "name": "周衡", "role": "supporting", "goal": "维持程序"},
    ],
}
BEATS = default_beats()


def state(events=None, index=0, tension=0, completed=None):
    return {"step": len(events or []), "events": events or [],
            "beat_state": {"index": index, "tension": tension, "completed_beats": completed or []}}


def event(eid, actor, **fields):
    base = {"id": eid, "actor_id": actor, "action": "把文件推到桌子中央", "dialogue": "先看原始记录。",
            "location": "董事会会议室"}
    base.update(fields)
    return base


def check(result, item):
    return next(c for c in result["checks"] if c["item"] == item)


def test_contract_is_derived_when_missing():
    contract = build_contract(SPEC)
    assert contract["protagonist"] == "a" and contract["opposing_force"] == "b"
    assert contract["central_secret"].startswith("授权记录")
    assert all(contract[key] for key in ("scene_goal", "stakes", "required_change", "ending_condition"))


def test_ensure_dramatic_adds_contract_and_five_beats_without_model():
    spec = ensure_dramatic(dict(SPEC), use_model=False)
    assert len(spec["beats"]) == 5 and spec["contract"]["protagonist"] == "a"
    # 幂等：已有就不再重算
    again = ensure_dramatic(spec, use_model=False)
    assert again["beats"] == spec["beats"] and again["contract"] == spec["contract"]


def test_conflict_and_progress_pass_with_two_actors():
    events = [event("e1", "a", tension_delta=3, revealed_information=["缺少签名"]),
              event("e2", "b", tension_delta=2)]
    result = assess(SPEC, state(), events, previous_tension=0)
    assert check(result, "冲突")["status"] == "通过"
    assert check(result, "推进")["status"] == "通过"
    assert result["passed"] >= 5


def test_progress_weak_with_single_actor():
    result = assess(SPEC, state(), [event("e1", "a", tension_delta=2)], previous_tension=0)
    assert check(result, "推进")["status"] == "偏弱"


def test_information_change_required_by_shift_beat():
    result = assess(SPEC, state(index=2), [event("e1", "a", tension_delta=1)], previous_tension=0)
    assert check(result, "信息变化")["status"] == "未发生"
    assert any("信息变化" in w for w in result["warnings"])


def test_causality_detected_only_when_referencing_history():
    history = [event("h1", "b")]
    weak = assess(SPEC, state(history), [event("e1", "a", tension_delta=1)], previous_tension=0)
    assert check(weak, "因果关系")["status"] == "偏弱"
    strong = assess(SPEC, state(history),
                    [event("e2", "a", caused_by_event_ids=["h1"], tension_delta=2)], previous_tension=0)
    assert check(strong, "因果关系")["status"] == "通过"


def test_escalation_flags_flat_and_decreasing_tension():
    flat = assess(SPEC, state(), [event("e1", "a", tension_delta=2)], previous_tension=2)
    assert check(flat, "压力升级")["status"] == "未发生"
    down = assess(SPEC, state(), [event("e1", "a", tension_delta=1)], previous_tension=3)
    assert any("压力下降" in w for w in down["warnings"])


def test_agency_weak_when_protagonist_silent():
    result = assess(SPEC, state(), [event("e1", "b", tension_delta=2)], previous_tension=0)
    assert check(result, "人物主动性")["status"] == "偏弱"
    assert any("主角" in w for w in result["warnings"])


def test_playability_weak_without_action_or_location():
    bare = {"id": "e1", "actor_id": "a", "action": "", "location": "", "tension_delta": 1}
    result = assess(SPEC, state(), [bare], previous_tension=0)
    assert check(result, "可拍性")["status"] == "偏弱"


def test_ending_ready_only_at_last_beat_with_completion():
    events = [event("e1", "a", tension_delta=3)]
    early = assess(SPEC, state(), events, previous_tension=0)
    assert check(early, "结尾准备")["status"] == "尚未满足"
    late = assess(SPEC, state(events, index=4, completed=["beat_1_open"]), events, previous_tension=2)
    assert check(late, "结尾准备")["status"] == "通过"


def test_event_fields_normalized_with_beat_and_clamped_tension():
    event = normalize_event_fields({"tension_delta": 99, "revealed_information": "x"}, default_beat="beat_1_open")
    assert event["tension_delta"] == 5 and event["revealed_information"] == []
    assert event["beat_id"] == "beat_1_open" and event["intent"] == ""


def test_screenplay_and_storyboard_render_with_sources():
    events = [event("e1", "a"), event("e2", "b", dialogue="如果这份邮件没有签名，你为什么现在才拿出来？",
                                      consequence="会议室压力升高")]
    text = render_screenplay(SPEC, events)
    assert text.startswith("内景 董事会会议室 日")
    assert "顾沉" in text and "【来源：e1】" in text and "【来源：e2】" in text
    shots = render_storyboard(SPEC, events)
    assert [s["shot"] for s in shots] == [1, 2]
    assert shots[1]["dialogue"].startswith("如果这份邮件")
    assert all({"shot_size", "camera", "frame", "actor", "rhythm", "source_event_id"} <= set(s) for s in shots)


def test_exactly_five_beats_expected():
    assert [b["beat_id"] for b in BEAT_TEMPLATE] == [b["beat_id"] for b in BEATS]
    assert len(BEATS) == 5
