from pathlib import Path
from tempfile import TemporaryDirectory
from backend.director_core.engine import DirectorStore, ConflictError

def test_sqlite_lifecycle_visibility_and_idempotency():
    with TemporaryDirectory() as tmp:
        s=DirectorStore(Path(tmp)/"director.db")
        scene=s.create_scene({"title":"合同","actors":[{"id":"a","name":"甲","location":"室内"},{"id":"b","name":"乙","location":"室内"}],"facts":[{"id":"secret","label":"秘密","known_by":["a"]}],"items":[{"id":"doc","name":"文件","holder":"a"}]})
        sid=scene["scene_id"]; assert s.visible_facts(sid,"b")==[]
        d=s.create_draft(sid,{"base_revision":0}); assert s.current_state(sid)["revision"]==0
        s.preview_draft(d["draft_id"],1); first=s.commit_draft(d["draft_id"],0,"k",1); second=s.commit_draft(d["draft_id"],0,"k",1)
        assert first==second and s.current_state(sid)["revision"]==1
        s2=DirectorStore(Path(tmp)/"director.db"); assert s2.current_state(sid)["revision"]==1

def test_commit_requires_preview_and_branch_isolation():
    with TemporaryDirectory() as tmp:
        s=DirectorStore(Path(tmp)/"x.db"); sid=s.create_scene({"title":"t"})["scene_id"]; d=s.create_draft(sid,{})
        try: s.commit_draft(d["draft_id"],0,"bad",1)
        except ConflictError: pass
        else: raise AssertionError("commit must require preview")
        s.preview_draft(d["draft_id"],1); s.commit_draft(d["draft_id"],0,"ok",1); b=s.create_branch(sid,{"name":"fork"}); assert b["state"]["revision"]==1
