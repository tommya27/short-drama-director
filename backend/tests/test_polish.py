"""剧本润色的安全边界：来源标记必须全保留，否则退回可复现草稿（离线，桩客户端）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.director_core.dramatic import polish_screenplay, render_screenplay  # noqa: E402

SPEC = {"location": "董事会会议室", "contract": {"protagonist": "a", "scene_goal": "暂停表决"}}
EVENTS = [
    {"id": "e1", "actor_id": "a", "action": "把文件夹推到桌子中央", "dialogue": "先看原始记录。",
     "location": "董事会会议室"},
    {"id": "e2", "actor_id": "b", "action": "站起来", "dialogue": "这件事到此为止。",
     "location": "董事会会议室"},
]


class StubClient:
    def __init__(self, payload):
        self.payload = payload

    def chat_json(self, system_prompt, user_prompt, tag="", temperature=None):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_polish_keeps_source_markers_and_returns_model_text():
    base = render_screenplay(SPEC, EVENTS)
    polished = base.replace("内景", "内景（润色）")
    result = polish_screenplay(SPEC, EVENTS, client=StubClient({"text": polished}), draft_text=base)
    assert result["polished"] is True
    assert "润色" in result["text"]
    assert result["text"].count("【来源：") == 2


def test_polish_falls_back_when_markers_missing():
    base = render_screenplay(SPEC, EVENTS)
    result = polish_screenplay(SPEC, EVENTS, client=StubClient({"text": "内景 董事会会议室 日\n\n（模型把来源标记丢了）"}),
                               draft_text=base)
    assert result["polished"] is False
    assert result["text"] == base                      # 交付可追溯的草稿
    assert "来源标记" in result["reason"]


def test_polish_falls_back_on_empty_or_error():
    base = render_screenplay(SPEC, EVENTS)
    empty = polish_screenplay(SPEC, EVENTS, client=StubClient({"text": "   "}), draft_text=base)
    assert empty["polished"] is False and empty["text"] == base and "为空" in empty["reason"]
    broken = polish_screenplay(SPEC, EVENTS, client=StubClient(RuntimeError("上游 502")), draft_text=base)
    assert broken["polished"] is False and broken["text"] == base and "RuntimeError" in broken["reason"]
