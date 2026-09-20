import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from director_core.engine import ConflictError, DirectorStore


def make_store():
    return DirectorStore()


def make_scene(store):
    return store.create_scene({
        "title": "授权记录",
        "location": "董事会会议室",
        "actors": [
            {"id": "a", "name": "甲", "role": "CEO", "location": "董事会会议室"},
            {"id": "b", "name": "乙", "role": "财务", "location": "董事会会议室"},
            {"id": "c", "name": "丙", "role": "法务", "location": "董事会会议室"},
        ],
        "facts": [
            {"id": "secret_a", "label": "甲知道的秘密", "known_by": ["a"]},
            {"id": "public", "label": "公开事实", "known_by": ["a", "b", "c"]},
        ],
    })


def test_draft_projection_does_not_change_formal_state():
    store = make_store(); scene = make_scene(store)
    before = store.current_state(scene["scene_id"])
    draft = store.create_draft(scene["scene_id"], {})
    after = store.current_state(scene["scene_id"])
    assert draft["status"] == "pending"
    assert before == after
    assert after["revision"] == 0 and after["events"] == []


def test_preview_commit_and_idempotent_commit():
    store = make_store(); scene = make_scene(store)
    draft = store.create_draft(scene["scene_id"], {})
    store.preview_draft(draft["draft_id"])
    store.commit_draft(draft["draft_id"],0,"key",1)
    committed = store.get_draft(draft["draft_id"])
    assert committed["status"] == "committed"
    state = store.current_state(scene["scene_id"])
    assert state["revision"] == 1 and len(state["events"]) == 3
    again = store.commit_draft(draft["draft_id"],0,"key",1)
    assert again["status"] == "committed"
    assert store.current_state(scene["scene_id"])["revision"] == 1


def test_branch_isolation():
    store = make_store(); scene = make_scene(store)
    sid = scene["scene_id"]
    draft = store.create_draft(sid, {})
    store.preview_draft(draft["draft_id"])
    store.preview_draft(draft["draft_id"]); store.commit_draft(draft["draft_id"])
    branch = store.create_branch(sid, {"name": "试演分支", "activate": True})
    bid = branch["branch_id"]
    branch_draft = store.create_draft(sid, {"branch_id": bid})
    store.preview_draft(branch_draft["draft_id"])
    store.preview_draft(branch_draft["draft_id"]); store.commit_draft(branch_draft["draft_id"])
    assert store.current_state(sid, bid)["revision"] == 2
    assert store.current_state(sid, "root")["revision"] == 1
    assert len(store.current_state(sid, "root")["events"]) == 3


def test_visibility_filters_private_facts_and_events():
    store = make_store(); scene = make_scene(store); sid = scene["scene_id"]
    assert {f["id"] for f in store.visible_facts(sid, "a")} == {"secret_a", "public"}
    assert {f["id"] for f in store.visible_facts(sid, "b")} == {"public"}
    draft = store.create_draft(sid, {})
    store.preview_draft(draft["draft_id"])
    store.preview_draft(draft["draft_id"]); store.commit_draft(draft["draft_id"])
    events_for_a = store.visible_events(sid, "a")
    events_for_b = store.visible_events(sid, "b")
    assert len(events_for_a) == len(events_for_b) == 3
    assert all("observed_by" in e and "a" in e["observed_by"] for e in events_for_a)


def test_revision_conflict_prevents_stale_commit():
    store = make_store(); scene = make_scene(store); sid = scene["scene_id"]
    first = store.create_draft(sid, {})
    second = store.create_draft(sid, {})
    store.preview_draft(first["draft_id"])
    store.preview_draft(first["draft_id"]); store.commit_draft(first["draft_id"])
    try:
        store.preview_draft(second["draft_id"]); store.commit_draft(second["draft_id"])
    except ConflictError:
        pass
    else:
        raise AssertionError("expected revision conflict")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from director_core.engine import DirectorStore

def test_directive_applies_to_candidate():
    store = DirectorStore()
    scene = store.create_scene({"title": "指令", "actors": [{"id": "a", "name": "甲", "location": "董事会会议室"}]})
    sid = scene["scene_id"]
    directive = store.add_directive(sid, {"text": "必须先观察文件", "target_actor_id": "a"})
    draft = store.create_draft(sid, {})
    assert "必须先观察文件" in draft["candidate_events"][0]["action"]
    assert directive["status"] == "pending"
    store.preview_draft(draft["draft_id"])
    store.preview_draft(draft["draft_id"]); store.commit_draft(draft["draft_id"])
    assert store.current_state(sid)["directives"][0]["status"] == "applied"
