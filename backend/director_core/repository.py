"""Owner-scoped SQLite authority for preview, author edits, and atomic commit.

Complete JSON checkpoints preserve engine state without a lossy projection.
This repository does not simulate, call a model, or implicitly preview.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import now_iso, new_id


class ConflictError(ValueError):
    """An optimistic version, lifecycle or lock constraint failed (HTTP 409)."""


class SchemaVersionError(RuntimeError):
    """An explicit, non-destructive database migration is required."""


class NarrativeRepository:
    SCHEMA_VERSION = 2

    def __init__(self, path: Path | str | None = None):
        default = Path(__file__).resolve().parents[2] / "data" / "director.db"
        self.path = Path(path if path is not None else os.environ.get("DIRECTOR_DB") or default)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _connection(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init(self) -> None:
        with self._connection(write=True) as c:
            version = c.execute("PRAGMA user_version").fetchone()[0]
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if version == self.SCHEMA_VERSION:
                if not {"scenes", "branches", "drafts", "commits", "checkpoints"}.issubset(tables):
                    raise SchemaVersionError("短剧数据库结构不完整；请恢复备份，不会自动覆盖现有数据")
                return
            if version != 0 or tables:
                raise SchemaVersionError(
                    f"短剧数据库版本 {version} 与当前版本 {self.SCHEMA_VERSION} 不兼容；"
                    "原数据已保留。请显式迁移，或通过 DIRECTOR_DB 指向新数据库。")
            statements = [
                """CREATE TABLE scenes (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, spec_json TEXT NOT NULL,
                    revision INTEGER NOT NULL, active_branch TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
                """CREATE TABLE branches (
                    id TEXT NOT NULL, scene_id TEXT NOT NULL, owner TEXT NOT NULL,
                    name TEXT NOT NULL, parent_branch TEXT, base_revision INTEGER NOT NULL,
                    revision INTEGER NOT NULL, spec_revision INTEGER NOT NULL,
                    spec_json TEXT NOT NULL, state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(scene_id,id),
                    FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE)""",
                """CREATE TABLE drafts (
                    id TEXT PRIMARY KEY, scene_id TEXT NOT NULL, branch_id TEXT NOT NULL,
                    owner TEXT NOT NULL, base_revision INTEGER NOT NULL,
                    base_spec_revision INTEGER NOT NULL, version INTEGER NOT NULL,
                    original_payload_json TEXT NOT NULL, payload_json TEXT NOT NULL,
                    locks_json TEXT NOT NULL, status TEXT NOT NULL,
                    preview_json TEXT, preview_fingerprint TEXT, preview_version INTEGER,
                    regenerated_from TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    FOREIGN KEY(scene_id,branch_id) REFERENCES branches(scene_id,id) ON DELETE CASCADE)""",
                """CREATE TABLE commits (
                    draft_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL, draft_version INTEGER NOT NULL,
                    result_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(draft_id) REFERENCES drafts(id) ON DELETE CASCADE)""",
                """CREATE TABLE checkpoints (
                    scene_id TEXT NOT NULL, branch_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    spec_revision INTEGER NOT NULL, spec_json TEXT NOT NULL,
                    state_json TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(scene_id,branch_id,revision),
                    FOREIGN KEY(scene_id,branch_id) REFERENCES branches(scene_id,id) ON DELETE CASCADE)""",
                "CREATE INDEX drafts_branch ON drafts(owner,scene_id,branch_id,created_at)",
                "CREATE INDEX scenes_owner ON scenes(owner,updated_at)",
            ]
            for statement in statements:
                c.execute(statement)
            c.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)

    @classmethod
    def _hash(cls, value: Any) -> str:
        return hashlib.sha256(cls._json(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        for key in list(data):
            if key.endswith("_json"):
                value = data.pop(key)
                data[key[:-5]] = json.loads(value) if value is not None else None
        return data

    def _branch(self, c: sqlite3.Connection, owner: str, scene_id: str, branch_id: str) -> dict[str, Any]:
        row = c.execute(
            "SELECT b.* FROM branches b JOIN scenes s ON s.id=b.scene_id "
            "WHERE b.owner=? AND s.owner=? AND b.scene_id=? AND b.id=?",
            (owner, owner, scene_id, branch_id)).fetchone()
        if row is None:
            raise LookupError("场景或分支不存在")
        return self._decode(row)

    def _draft(self, c: sqlite3.Connection, owner: str, draft_id: str) -> dict[str, Any]:
        row = c.execute("SELECT * FROM drafts WHERE id=? AND owner=?", (draft_id, owner)).fetchone()
        if row is None:
            raise LookupError("草稿不存在")
        return self._decode(row)

    @staticmethod
    def _editable(draft: dict[str, Any], expected_version: int) -> None:
        if draft["status"] != "awaiting_approval":
            raise ConflictError("草稿已提交或已放弃，不能继续修改、预览或提交")
        if expected_version != draft["version"]:
            raise ConflictError("草稿版本已变化，请刷新后重试")

    @staticmethod
    def _current(draft: dict[str, Any], branch: dict[str, Any]) -> None:
        if draft["base_revision"] != branch["revision"] or draft["base_spec_revision"] != branch["spec_revision"]:
            raise ConflictError("正式版本已变化，请基于当前状态重新生成草稿")

    @staticmethod
    def _lock_paths(payload: dict[str, Any]) -> list[str]:
        paths = payload.get("locks", [])
        if not isinstance(paths, list) or any(not isinstance(p, str) or not p for p in paths):
            raise ValueError("locks 必须为非空字段路径的列表")
        return list(dict.fromkeys(paths))

    @staticmethod
    def _locked_value(payload: dict[str, Any], path: str) -> Any:
        value: Any = payload
        for part in path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            elif isinstance(value, list):
                if part.isdigit():
                    index = int(part)
                    if index < 0 or index >= len(value):
                        raise ValueError(f"锁定路径不存在：{path}")
                    value = value[index]
                    continue
                matches = [v for v in value if isinstance(v, dict) and (v.get("id") == part or v.get("event_id") == part)]
                if len(matches) != 1:
                    raise ValueError(f"锁定路径不存在或不唯一：{path}")
                value = matches[0]
            else:
                raise ValueError(f"锁定路径不存在：{path}")
        return value

    def _check_locked(self, before: dict[str, Any], after: dict[str, Any], locks: list[str]) -> None:
        for path in locks:
            try:
                unchanged = self._locked_value(before, path) == self._locked_value(after, path)
            except ValueError as exc:
                raise ConflictError(f"锁定内容不可删除：{path}") from exc
            if not unchanged:
                raise ConflictError(f"锁定内容不可覆盖：{path}；请先单独解锁")

    def _checkpoint(self, c: sqlite3.Connection, branch: dict[str, Any], reason: str, stamp: str) -> None:
        c.execute("INSERT INTO checkpoints VALUES (?,?,?,?,?,?,?,?)",
                  (branch["scene_id"], branch["id"], branch["revision"], branch["spec_revision"],
                   self._json(branch["spec"]), self._json(branch["state"]), reason, stamp))

    def _touch(self, c: sqlite3.Connection, owner: str, scene_id: str, stamp: str) -> None:
        c.execute("UPDATE scenes SET revision=revision+1,updated_at=? WHERE id=? AND owner=?", (stamp, scene_id, owner))

    def create_scene(self, owner: str, spec: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        sid, stamp = new_id("scene"), now_iso()
        snapshot = copy.deepcopy(state)
        snapshot["revision"] = 0
        with self._connection(write=True) as c:
            c.execute("INSERT INTO scenes VALUES (?,?,?,?,?,?,?)", (sid, owner, self._json(spec), 0, "main", stamp, stamp))
            c.execute("INSERT INTO branches VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      ("main", sid, owner, "主线", None, 0, 0, 0, self._json(spec), self._json(snapshot), stamp, stamp))
            self._checkpoint(c, self._branch(c, owner, sid, "main"), "created", stamp)
        return self.get_scene(owner, sid)

    def get_scene(self, owner: str, scene_id: str) -> dict[str, Any] | None:
        with self._connection() as c:
            data = self._decode(c.execute("SELECT * FROM scenes WHERE id=? AND owner=?", (scene_id, owner)).fetchone())
            if data is not None:
                data["branches"] = [self._decode(r) for r in c.execute(
                    "SELECT * FROM branches WHERE scene_id=? AND owner=? ORDER BY created_at,id", (scene_id, owner))]
            return data

    def list_scenes(self, owner: str) -> list[dict[str, Any]]:
        with self._connection() as c:
            return [self._decode(r) for r in c.execute("SELECT * FROM scenes WHERE owner=? ORDER BY updated_at DESC,id", (owner,))]

    def get_branch(self, owner: str, scene_id: str, branch_id: str = "main") -> dict[str, Any] | None:
        with self._connection() as c:
            try:
                return self._branch(c, owner, scene_id, branch_id)
            except LookupError:
                return None

    def update_branch(self, owner: str, scene_id: str, branch_id: str, base_revision: int,
                      *, spec: dict[str, Any] | None = None, state: dict[str, Any] | None = None,
                      reason: str = "author_edit", activate: bool = False) -> dict[str, Any]:
        """Save an explicit author/config/directive edit as a complete checkpoint."""
        if spec is None and state is None:
            raise ValueError("至少需要提供 spec 或 state")
        stamp = now_iso()
        with self._connection(write=True) as c:
            branch = self._branch(c, owner, scene_id, branch_id)
            if base_revision != branch["revision"]:
                raise ConflictError("正式版本已变化，请刷新后重试")
            if spec is not None:
                branch["spec"] = copy.deepcopy(spec)
                branch["spec_revision"] += 1
            if state is not None:
                branch["state"] = copy.deepcopy(state)
            branch["revision"] += 1
            branch["state"]["revision"] = branch["revision"]
            c.execute("UPDATE branches SET revision=?,spec_revision=?,spec_json=?,state_json=?,updated_at=? WHERE scene_id=? AND id=? AND owner=?",
                      (branch["revision"], branch["spec_revision"], self._json(branch["spec"]), self._json(branch["state"]), stamp, scene_id, branch_id, owner))
            if branch_id == "main" and spec is not None:
                c.execute("UPDATE scenes SET spec_json=? WHERE id=? AND owner=?", (self._json(spec), scene_id, owner))
            if activate:
                c.execute("UPDATE scenes SET active_branch=? WHERE id=? AND owner=?", (branch_id, scene_id, owner))
            self._checkpoint(c, branch, reason, stamp)
            self._touch(c, owner, scene_id, stamp)
            branch["updated_at"] = stamp
            return branch

    def activate_branch(self, owner: str, scene_id: str, branch_id: str,
                        base_revision: int | None = None) -> None:
        """Validate and select a branch without changing its story revision."""
        with self._connection(write=True) as c:
            branch = self._branch(c, owner, scene_id, branch_id)
            if base_revision is not None and branch['revision'] != base_revision:
                raise ConflictError('正式版本已变化，请刷新后重试')
            c.execute('UPDATE scenes SET active_branch=? WHERE id=? AND owner=?',
                      (branch_id, scene_id, owner))

    def update_spec(self, owner: str, scene_id: str, spec: dict[str, Any], *, base_revision: int,
                    branch_id: str = "main", state: dict[str, Any] | None = None) -> dict[str, Any]:
        self.update_branch(owner, scene_id, branch_id, base_revision, spec=spec, state=state, reason="spec_edit")
        return self.get_scene(owner, scene_id)

    def create_draft(self, owner: str, scene_id: str, branch_id: str, base_revision: int,
                     payload: dict[str, Any], *, regenerate_from: str | None = None,
                     regenerate_version: int | None = None) -> dict[str, Any]:
        did, stamp = new_id("draft"), now_iso()
        payload = copy.deepcopy(payload)
        locks = self._lock_paths(payload)
        payload["locks"] = locks
        for path in locks:
            self._locked_value(payload, path)
        with self._connection(write=True) as c:
            branch = self._branch(c, owner, scene_id, branch_id)
            if branch["revision"] != base_revision:
                raise ConflictError("正式版本已变化，生成结果已过期")
            if regenerate_from is not None:
                source = self._draft(c, owner, regenerate_from)
                self._editable(source, regenerate_version)
                if (source["scene_id"], source["branch_id"]) != (scene_id, branch_id):
                    raise ConflictError("重新生成的草稿必须属于同一场景分支")
                self._current(source, branch)
                self._check_locked(source["payload"], payload, source["locks"])
                if not set(source["locks"]).issubset(locks):
                    raise ConflictError("重新生成不能删除锁定字段")
            c.execute("INSERT INTO drafts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (did, scene_id, branch_id, owner, base_revision, branch["spec_revision"], 1,
                       self._json(payload), self._json(payload), self._json(locks), "awaiting_approval",
                       None, None, None, regenerate_from, stamp, stamp))
            return self._draft(c, owner, did)

    def get_draft(self, owner: str, draft_id: str) -> dict[str, Any] | None:
        with self._connection() as c:
            try:
                return self._draft(c, owner, draft_id)
            except LookupError:
                return None

    def list_drafts(self, owner: str, scene_id: str, branch_id: str = "main", status: str | None = None) -> list[dict[str, Any]]:
        with self._connection() as c:
            self._branch(c, owner, scene_id, branch_id)
            query = "SELECT * FROM drafts WHERE owner=? AND scene_id=? AND branch_id=?"
            args = [owner, scene_id, branch_id]
            if status is not None:
                query += " AND status=?"
                args.append(status)
            return [self._decode(r) for r in c.execute(query + " ORDER BY created_at,id", args)]

    def update_draft(self, owner: str, draft_id: str, payload: dict[str, Any], *, expected_version: int,
                     unlock_paths: list[str] | None = None) -> dict[str, Any]:
        with self._connection(write=True) as c:
            draft = self._draft(c, owner, draft_id)
            self._editable(draft, expected_version)
            self._current(draft, self._branch(c, owner, draft["scene_id"], draft["branch_id"]))
            revised = {**draft["payload"], **copy.deepcopy(payload)}
            unlock = set(unlock_paths or [])
            old_locks = set(draft["locks"])
            if not unlock.issubset(old_locks):
                raise ConflictError("只能显式解锁当前已锁定的字段")
            # Unlocking and changing the previously locked value require two
            # separate author requests, avoiding a silent lock bypass.
            self._check_locked(draft["payload"], revised, draft["locks"])
            if "locks" not in payload:
                revised["locks"] = [p for p in draft["locks"] if p not in unlock]
            locks = self._lock_paths(revised)
            if not (old_locks - unlock).issubset(locks) or unlock.intersection(locks):
                raise ConflictError("移除锁定必须显式提供 unlock_paths")
            for path in locks:
                self._locked_value(revised, path)
            revised["locks"] = locks
            c.execute("UPDATE drafts SET version=version+1,payload_json=?,locks_json=?,preview_json=NULL,preview_fingerprint=NULL,preview_version=NULL,updated_at=? WHERE id=? AND owner=?",
                      (self._json(revised), self._json(locks), now_iso(), draft_id, owner))
            return self._draft(c, owner, draft_id)

    def _preview_fingerprint(self, draft: dict[str, Any], preview: dict[str, Any]) -> str:
        return self._hash({"draft_id": draft["id"], "version": draft["version"],
                           "base_revision": draft["base_revision"], "base_spec_revision": draft["base_spec_revision"],
                           "payload": draft["payload"], "locks": draft["locks"], "preview": preview})

    def _check_preview_state(self, draft: dict[str, Any], branch: dict[str, Any], preview: dict[str, Any]) -> None:
        state = preview["state"]
        if not set(branch["state"]).issubset(state):
            raise ConflictError("预览缺少完整世界状态字段")
        history = branch["state"].get("events", [])
        events = state.get("events", [])
        if not isinstance(events, list) or events[:len(history)] != history:
            raise ConflictError("预览不得删除或改写已经提交的事件")
        ids = [e.get("id", e.get("event_id")) if isinstance(e, dict) else None for e in events]
        if any(not isinstance(eid, str) or not eid for eid in ids) or len(ids) != len(set(ids)):
            raise ValueError("预览事件必须有唯一稳定 ID")
        projection = {**draft["payload"], "events": events[len(history):]}
        self._check_locked(draft["payload"], projection, draft["locks"])

    def save_preview(self, owner: str, draft_id: str, preview: dict[str, Any], *, expected_version: int) -> dict[str, Any]:
        if not isinstance(preview.get("state"), dict):
            raise ValueError("预览必须包含完整 state 对象")
        with self._connection(write=True) as c:
            draft = self._draft(c, owner, draft_id)
            self._editable(draft, expected_version)
            branch = self._branch(c, owner, draft["scene_id"], draft["branch_id"])
            self._current(draft, branch)
            if preview.get("base_revision", draft["base_revision"]) != draft["base_revision"]:
                raise ConflictError("预览基准版本不匹配")
            snapshot = copy.deepcopy(preview)
            snapshot.update(base_revision=draft["base_revision"], revision=draft["base_revision"] + 1,
                            draft_version=draft["version"], status="preview_only")
            snapshot["state"]["revision"] = snapshot["revision"]
            self._check_preview_state(draft, branch, snapshot)
            fingerprint = self._preview_fingerprint(draft, snapshot)
            c.execute("UPDATE drafts SET preview_json=?,preview_fingerprint=?,preview_version=?,updated_at=? WHERE id=? AND owner=?",
                      (self._json(snapshot), fingerprint, draft["version"], now_iso(), draft_id, owner))
            return self._draft(c, owner, draft_id)

    def discard_draft(self, owner: str, draft_id: str, *, expected_version: int) -> dict[str, Any]:
        with self._connection(write=True) as c:
            draft = self._draft(c, owner, draft_id)
            self._editable(draft, expected_version)
            c.execute("UPDATE drafts SET status='discarded',version=version+1,preview_json=NULL,preview_fingerprint=NULL,preview_version=NULL,updated_at=? WHERE id=? AND owner=?",
                      (now_iso(), draft_id, owner))
            return self._draft(c, owner, draft_id)

    def get_commit_result(self, owner: str, draft_id: str, idempotency_key: str) -> dict[str, Any] | None:
        with self._connection() as c:
            self._draft(c, owner, draft_id)
            row = c.execute("SELECT * FROM commits WHERE draft_id=? AND owner=?", (draft_id, owner)).fetchone()
            if row is None:
                return None
            if row["idempotency_key"] != idempotency_key:
                raise ConflictError("草稿已经使用其他幂等键提交")
            return json.loads(row["result_json"])

    def commit(self, owner: str, draft_id: str, *, idempotency_key: str, expected_version: int) -> dict[str, Any]:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("必须提供非空 idempotency_key")
        stamp = now_iso()
        with self._connection(write=True) as c:
            draft = self._draft(c, owner, draft_id)
            old = c.execute("SELECT * FROM commits WHERE draft_id=? AND owner=?", (draft_id, owner)).fetchone()
            if old is not None:
                if old["idempotency_key"] != idempotency_key or old["draft_version"] != expected_version:
                    raise ConflictError("草稿已经提交，重试必须使用原幂等键和草稿版本")
                return json.loads(old["result_json"])
            self._editable(draft, expected_version)
            branch = self._branch(c, owner, draft["scene_id"], draft["branch_id"])
            self._current(draft, branch)
            preview = draft["preview"]
            if (preview is None or draft["preview_version"] != draft["version"] or
                    draft["preview_fingerprint"] != self._preview_fingerprint(draft, preview)):
                raise ConflictError("请先预览当前草稿版本，再确认提交")
            if preview.get("valid") is False:
                raise ConflictError("预览检查未通过，请修改草稿后重新预览")
            self._check_preview_state(draft, branch, preview)
            state = copy.deepcopy(preview["state"])
            revision = branch["revision"] + 1
            state["revision"] = revision
            # Diff IDs instead of slicing: an empty candidate never claims the
            # entire existing history, and event order remains stable.
            old_ids = {e.get("id", e.get("event_id")) for e in branch["state"].get("events", [])}
            event_ids = [e.get("id", e.get("event_id")) for e in state.get("events", [])
                         if e.get("id", e.get("event_id")) not in old_ids]
            if any(e is None for e in event_ids) or len(event_ids) != len(set(event_ids)):
                raise ValueError("预览事件必须有唯一稳定 ID")
            result = {"scene_id": draft["scene_id"], "branch_id": draft["branch_id"],
                      "draft_id": draft_id, "draft_version": draft["version"],
                      "revision": revision, "event_ids": event_ids,
                      "preview_fingerprint": draft["preview_fingerprint"]}
            c.execute("UPDATE branches SET revision=?,state_json=?,updated_at=? WHERE scene_id=? AND id=? AND owner=?",
                      (revision, self._json(state), stamp, draft["scene_id"], draft["branch_id"], owner))
            c.execute("UPDATE drafts SET status='committed',updated_at=? WHERE id=? AND owner=?", (stamp, draft_id, owner))
            c.execute("INSERT INTO commits VALUES (?,?,?,?,?,?)",
                      (draft_id, owner, idempotency_key, draft["version"], self._json(result), stamp))
            branch.update(revision=revision, state=state)
            self._checkpoint(c, branch, f"commit:{draft_id}", stamp)
            self._touch(c, owner, draft["scene_id"], stamp)
            return result

    def create_branch(self, owner: str, scene_id: str, source_branch: str, name: str,
                      *, base_revision: int | None = None) -> dict[str, Any]:
        bid, stamp = new_id("branch"), now_iso()
        with self._connection(write=True) as c:
            source = self._branch(c, owner, scene_id, source_branch)
            if base_revision is not None and base_revision != source["revision"]:
                raise ConflictError("分支源版本已变化，请刷新后重试")
            c.execute("INSERT INTO branches VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (bid, scene_id, owner, name, source_branch, source["revision"], source["revision"],
                       source["spec_revision"], self._json(source["spec"]), self._json(source["state"]), stamp, stamp))
            branch = self._branch(c, owner, scene_id, bid)
            self._checkpoint(c, branch, f"fork:{source_branch}", stamp)
            self._touch(c, owner, scene_id, stamp)
            return branch

    def get_checkpoint(self, owner: str, scene_id: str, branch_id: str, revision: int) -> dict[str, Any] | None:
        with self._connection() as c:
            self._branch(c, owner, scene_id, branch_id)
            return self._decode(c.execute("SELECT * FROM checkpoints WHERE scene_id=? AND branch_id=? AND revision=?",
                                          (scene_id, branch_id, revision)).fetchone())

    def replay_checkpoints(self, owner: str, scene_id: str, branch_id: str,
                           expected_revision: int | None = None) -> tuple[int, list[dict[str, Any]]]:
        """Read immutable history, including only ancestry before the fork point."""
        with self._connection() as c:
            branch = self._branch(c, owner, scene_id, branch_id)
            if expected_revision is not None and expected_revision != branch['revision']:
                raise ConflictError('正式版本已变化，请刷新后再回看')
            def collect(current: dict[str, Any], ceiling: int) -> list[dict[str, Any]]:
                inherited = []
                if current['parent_branch']:
                    parent = self._branch(c, owner, scene_id, current['parent_branch'])
                    inherited = collect(parent, min(ceiling, current['base_revision'] - 1))
                own = [self._decode(row) for row in c.execute(
                    'SELECT * FROM checkpoints WHERE scene_id=? AND branch_id=? AND revision<=? ORDER BY revision',
                    (scene_id, current['id'], ceiling))]
                return inherited + own
            return branch['revision'], collect(branch, branch['revision'])
