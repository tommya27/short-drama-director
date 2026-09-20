import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.main import app
from fastapi.testclient import TestClient


def test_api_smoke():
    client = TestClient(app)
    r = client.post('/api/v1/ideas/expand', json={'premise':'董事长发现授权记录被改写'})
    assert r.status_code == 200
    r = client.post('/api/v1/scenes', json={'title':'演示'})
    assert r.status_code == 200
    sid = r.json()['scene_id']
    r = client.post(f'/api/v1/scenes/{sid}/drafts', json={})
    assert r.status_code == 200
    assert client.get(f'/api/v1/scenes/{sid}/state').json()['revision'] == 0
    did = r.json()['draft_id']
    assert client.post(f'/api/v1/drafts/{did}/preview').status_code == 200
    assert client.post(f'/api/v1/drafts/{did}/commit').status_code == 200
    assert client.post(f'/api/v1/drafts/{did}/commit').status_code == 200
    assert client.get(f'/api/v1/scenes/{sid}/state').json()['revision'] == 1


def test_branch_view_returns_spec_and_state_from_same_branch(monkeypatch):
    from tempfile import TemporaryDirectory
    from backend import main
    from backend.director_core.engine import DirectorStore
    temp = TemporaryDirectory()
    monkeypatch.setattr(main, 'store', DirectorStore(Path(temp.name) / 'branches.db'))
    client = TestClient(app)
    scene = client.post('/api/v1/scenes', json={'title': '父场景'}).json()
    sid = scene['scene_id']
    child = client.post(f'/api/v1/scenes/{sid}/branches', json={'name': '子分支'}).json()
    bid = child['branch_id']
    changed = client.patch(f'/api/v1/scenes/{sid}', json={'branch_id': bid, 'base_revision': 0, 'title': '子场景'})
    assert changed.status_code == 200
    parent_view = client.get(f'/api/v1/scenes/{sid}?branch_id=main').json()
    child_view = client.get(f'/api/v1/scenes/{sid}?branch_id={bid}').json()
    assert parent_view['scene_spec']['title'] == '父场景'
    assert parent_view['state']['branch_id'] == 'main'
    assert child_view['scene_spec']['title'] == '子场景'
    assert child_view['state']['branch_id'] == bid
    assert child_view['state']['revision'] == 1

    temp.cleanup()
