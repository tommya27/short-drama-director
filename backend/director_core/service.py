"""Author-controlled sessions: generation, pure preview, transactional commit."""
from __future__ import annotations

import copy
from typing import Any, Callable

from .models import default_boardroom_spec, default_state, normalize_spec, new_id
from .repository import NarrativeRepository, ConflictError
from .sandbox import AgentSandbox, LLMCandidateGenerator, project
from .dramatic import assess, ensure_dramatic, render_screenplay, render_storyboard


class NarrativeService:
    def __init__(self, repo: NarrativeRepository | None = None, generator_factory: Callable | None = None):
        self.repo = repo or NarrativeRepository()
        self.generator_factory = generator_factory

    def branch(self, owner: str, scene_id: str, branch_id: str = "main") -> dict:
        result = self.repo.get_branch(owner, scene_id, branch_id)
        if result is None:
            raise LookupError("场景或分支不存在")
        return result

    def draft(self, owner: str, draft_id: str) -> dict:
        result = self.repo.get_draft(owner, draft_id)
        if result is None:
            raise LookupError("草稿不存在")
        return result

    def create_scene(self, owner: str, payload: dict[str, Any]) -> dict:
        spec = normalize_spec(copy.deepcopy(payload))
        return self.repo.create_scene(owner, spec, default_state(spec))

    def generate_draft(self, owner: str, scene_id: str, branch_id: str = "main", *,
                       base_revision: int, regenerate_from: str | None = None,
                       regenerate_version: int | None = None,
                       progress: Callable = lambda *_: None) -> dict:
        branch = self.branch(owner, scene_id, branch_id)
        if branch["revision"] != base_revision:
            raise ConflictError("版本已变化，请刷新场景")
        source = None
        if regenerate_from:
            source = self.draft(owner, regenerate_from)
            if (source["scene_id"], source["branch_id"], source["base_revision"],
                    source["version"], source["status"]) != (
                    scene_id, branch_id, base_revision, regenerate_version, "awaiting_approval"):
                raise ConflictError("待重新生成的草稿已经改变")
        progress(5, "按角色视角准备候选")
        generator = self.generator_factory() if self.generator_factory else None
        completed = 0
        total = max(1, len(branch["spec"]["characters"]))
        def role_progress(actor_id, phase):
            nonlocal completed
            if phase == "proposed":
                completed += 1
            progress(5 + int(70 * completed / total), f"角色 {actor_id}：{'候选已返回' if phase == 'proposed' else '准备行动'}")
        events = AgentSandbox(branch["spec"], branch["state"], generator=generator).propose(progress=role_progress)
        progress(80, "检查候选世界变化")
        locks = copy.deepcopy(source["payload"].get("locks", [])) if source else []
        if source:
            # Conservatively preserve whole events containing locked fields.
            pinned = {p.split(".")[1] for p in locks if p.startswith("events.")}
            preserved = [copy.deepcopy(e) for e in source["payload"]["events"] if e["id"] in pinned]
            actors = {e["actor_id"] for e in preserved}
            events = [e for e in events if e["actor_id"] not in actors] + preserved
        payload = {"events": events, "locks": locks,
                   "source": getattr(generator, "source", "injected_test_generator") if generator and not isinstance(generator, LLMCandidateGenerator) else "llm_role_agents"}
        project(branch["spec"], branch["state"], events)
        # 剧情检查：只提示，不改事件；作者可据此决定干预或进入下一拍
        payload["assessment"] = assess(branch["spec"], branch["state"], events,
                                       contract=branch["spec"].get("contract"),
                                       beats=branch["spec"].get("beats"),
                                       previous_tension=int((branch["state"].get("beat_state") or {}).get("tension", 0)))
        progress(95, "保存候选草稿（尚未提交）")
        return self.repo.create_draft(owner, scene_id, branch_id, base_revision, payload,
                                      regenerate_from=regenerate_from, regenerate_version=regenerate_version)

    def edit_draft(self, owner: str, draft_id: str, events: list[dict], locks: list[str], *,
                   expected_version: int, unlock_paths: list[str] | None = None) -> dict:
        draft = self.draft(owner, draft_id)
        branch = self.branch(owner, draft["scene_id"], draft["branch_id"])
        normalized = project(branch["spec"], branch["state"], events)["events"]
        payload = {**draft["payload"], "events": normalized, "locks": locks}
        return self.repo.update_draft(owner, draft_id, payload, expected_version=expected_version,
                                      unlock_paths=unlock_paths or [])

    def preview(self, owner: str, draft_id: str, *, expected_version: int) -> dict:
        draft = self.draft(owner, draft_id)
        branch = self.branch(owner, draft["scene_id"], draft["branch_id"])
        if branch["revision"] != draft["base_revision"]:
            raise ConflictError("正式状态已变化，请重新生成草稿")
        preview = project(branch["spec"], branch["state"], draft["payload"]["events"])
        originals = {e["id"]: e for e in draft["original_payload"].get("events", [])}
        final_events = preview.get("events", [])
        for e in final_events:
            e["original_proposal"] = copy.deepcopy(originals.get(e["id"]))
            e["author_modified"] = originals.get(e["id"]) != next(
                (x for x in draft["payload"]["events"] if x["id"] == e["id"]), None)
            e["source_draft_id"] = draft_id
            e["branch_id"] = draft["branch_id"]
            e["revision"] = branch["revision"] + 1
        by_id = {e["id"]: e for e in final_events}
        preview["state"]["events"] = [copy.deepcopy(by_id.get(e["id"], e)) for e in preview["state"]["events"]]
        preview.update(base_revision=draft["base_revision"], status="preview_only", event_count=len(final_events))
        return self.repo.save_preview(owner, draft_id, preview, expected_version=expected_version)

    def commit(self, owner: str, draft_id: str, idempotency_key: str, *, expected_version: int) -> dict:
        return self.repo.commit(owner, draft_id, idempotency_key=idempotency_key, expected_version=expected_version)

    def edit_scene(self, owner: str, scene_id: str, branch_id: str, base_revision: int, changes: dict,
                   *, activate: bool = False) -> dict:
        branch = self.branch(owner, scene_id, branch_id)
        changes = copy.deepcopy(changes)
        old_cards = {a["id"]: a for a in branch["spec"]["characters"]}
        position_changes = set()
        if "characters" in changes:
            if not isinstance(changes["characters"], list):
                raise ValueError("characters 必须是数组")
            # Character edits are ID-addressed patches. Preserve cards omitted
            # by the request so an editor can change one role without deleting
            # the rest of the cast. Explicit deletion remains unavailable once
            # the scene has history, and is validated below.
            updates = {}
            for update in changes["characters"]:
                if not isinstance(update, dict) or not isinstance(update.get("id"), str):
                    raise ValueError("角色必须提供 id")
                old = old_cards.get(update["id"], {})
                for primary, alias in (("goal", "hidden_goal"), ("location", "start_location")):
                    changed = [key for key in (primary, alias) if key in update and update[key] != old.get(key)]
                    if len(changed) == 2 and update[primary] != update[alias]:
                        raise ValueError(f"{primary} 与 {alias} 不能冲突")
                    if changed:
                        update[primary] = update[alias] = update[changed[0]]
                        if primary == "location":
                            position_changes.add(update["id"])
                updates[update["id"]] = {**old, **update}
            cards = [updates.get(actor_id, copy.deepcopy(card))
                     for actor_id, card in old_cards.items()]
            # Permit adding a new role by supplying a complete card, while
            # keeping deterministic order for existing roles.
            cards.extend(card for actor_id, card in updates.items() if actor_id not in old_cards)
            changes["characters"] = cards
        spec = normalize_spec({**copy.deepcopy(branch["spec"]), **changes})
        before = branch["state"]
        state = copy.deepcopy(before)
        fresh = default_state(spec)
        old_ids = {a["id"] for a in branch["spec"]["characters"]}
        new_ids = {a["id"] for a in spec["characters"]}
        if before.get("events") and not old_ids <= new_ids:
            raise ValueError("已有剧情的角色不能删除；请保留稳定 ID")
        if "characters" in changes:
            state["actors"] = {}
            for actor in spec["characters"]:
                aid = actor["id"]
                # Retain runtime memory; only editable position/card fields change.
                saved = copy.deepcopy(before.get("actors", {}).get(aid, fresh["actors"][aid]))
                if aid in position_changes or aid not in before.get("actors", {}):
                    saved["location"] = fresh["actors"][aid]["location"]
                state["actors"][aid] = saved
        if "items" in changes:
            state["items"] = fresh["items"]
        if "facts" in changes:
            old = {f["id"]: f for f in before["facts"]}
            new = {f["id"]: f for f in fresh["facts"]}
            if any(old.get(i) != new.get(i) for i in before.get("locked_fact_ids", [])):
                raise ConflictError("设定包含锁定事实，请先明确解锁")
            state["facts"] = fresh["facts"]
        if any(a["location"] not in spec["world"]["locations"] for a in state["actors"].values()):
            raise ValueError("不能删除角色当前所在地点；请先移动角色")
        if any(i.get("holder") and i["holder"] not in state["actors"] for i in state["items"].values()):
            raise ValueError("道具仍由被删除角色持有，请先修改道具")
        if any(aid not in state["actors"] for f in state["facts"] for aid in f.get("known_by", [])):
            raise ValueError("事实仍引用被删除角色，请先修改事实")
        return self.repo.update_branch(owner, scene_id, branch_id, base_revision,
                                       spec=spec, state=state, reason="author_scene_edit", activate=activate)

    def directive(self, owner: str, scene_id: str, branch_id: str, base_revision: int, *,
                  text: str, target_actor_id: str | None, start_step: int, end_step: int) -> dict:
        branch = self.branch(owner, scene_id, branch_id)
        actors = {a["id"] for a in branch["spec"]["characters"]}
        if target_actor_id is not None and target_actor_id not in actors:
            raise ValueError("指令目标角色不存在")
        if not text.strip() or start_step <= branch["state"]["step"] or end_step < start_step:
            raise ValueError("指令范围应从未来步骤开始，结束不能早于开始")
        state = copy.deepcopy(branch["state"])
        directive = {"id": new_id("directive"), "text": text, "target_actor_id": target_actor_id,
                     "start_step": start_step, "end_step": end_step, "status": "pending"}
        state.setdefault("directives", []).append(directive)
        result = self.repo.update_branch(owner, scene_id, branch_id, base_revision, state=state, reason="add_directive")
        return {"directive": directive, "revision": result["revision"]}

    def cancel_directive(self, owner: str, scene_id: str, branch_id: str, base_revision: int, directive_id: str) -> dict:
        branch = self.branch(owner, scene_id, branch_id)
        state = copy.deepcopy(branch["state"])
        directive = next((d for d in state.get("directives", []) if d["id"] == directive_id), None)
        if directive is None:
            raise LookupError("导演指令不存在")
        if directive["status"] != "pending":
            raise ConflictError("只有未执行指令可以取消")
        directive["status"] = "cancelled"
        return self.repo.update_branch(owner, scene_id, branch_id, base_revision, state=state, reason="cancel_directive")

    def lock_facts(self, owner: str, scene_id: str, branch_id: str, base_revision: int, fact_ids: list[str]) -> dict:
        branch = self.branch(owner, scene_id, branch_id)
        if not set(fact_ids) <= {f["id"] for f in branch["state"]["facts"]}:
            raise ValueError("锁定事实不存在")
        state = copy.deepcopy(branch["state"])
        state["locked_fact_ids"] = list(dict.fromkeys(fact_ids))
        return self.repo.update_branch(owner, scene_id, branch_id, base_revision, state=state, reason="author_fact_locks")

    def output(self, owner: str, scene_id: str, branch_id: str, kind: str, event_ids: list[str], *, base_revision: int) -> dict:
        branch = self.branch(owner, scene_id, branch_id)
        if branch["revision"] != base_revision:
            raise ConflictError("输出来源版本已变化")
        if kind not in {"scene_card", "script", "storyboard"} or not event_ids:
            raise ValueError("请选择事件及有效输出类型")
        selected = set(event_ids)
        events = [e for e in branch["state"]["events"] if e["id"] in selected]
        if len(events) != len(selected):
            raise ValueError("选中事件不属于当前分支")
        names = {a["id"]: a["name"] for a in branch["spec"]["characters"]}
        lines = [f"# {branch['spec']['title']} · {kind}", "", f"来源分支：{branch_id} / revision {base_revision}"]
        for e in events:
            actor = names.get(e["actor_id"], e["actor_id"])
            lines += ["", f"[{e['id']}] {actor} · {e.get('location', '')}", e.get("action", ""), f"对白：{e.get('dialogue', '')}"]
            if kind == "storyboard":
                lines += ["景别/构图：待导演选择", "声音/时长：待定"]
        if kind == "scene_card":
            lines[2:2] = [f"场景目标：{branch['spec'].get('goal', '')}", ""]
        return {"kind": kind, "scene_id": scene_id, "branch_id": branch_id, "revision": base_revision,
                "event_ids": [e["id"] for e in events], "content": "\n".join(lines), "editable": True, "source": "selected_events"}
