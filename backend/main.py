"""Standalone FastAPI service for the short-drama director MVP."""
from __future__ import annotations
from typing import Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .director_core import images as image_assets
from .director_core.engine import ConflictError, NotFoundError
from .director_core.opening import expand
from .director_core.runtime import build_store, load_env_file, runtime_info

# 运行模式：live（真实模型）或 offline（离线规则）。
# 先读项目 .env，再按模式构建 store；模式信息通过 /api/v1/runtime 暴露给前端做徽标。
load_env_file()
store, RUNTIME = build_store()

app = FastAPI(title="可视化 AI 导演台 API", version="0.1.0", description="共享虚拟世界剧情沙盘与导演控制台")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5274", "http://localhost:5274"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


class PremiseInput(BaseModel):
    premise: str = Field(min_length=1)


class JsonPayload(BaseModel):
    model_config = {"extra": "allow"}

    def as_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump(exclude_unset=True)
        return self.dict(exclude_unset=True)


def _data(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    return value.dict(exclude_none=True)


def _handle(fn):
    try:
        return fn()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "short-drama-director", "version": app.version,
            "model_mode": RUNTIME["mode"], "generator": RUNTIME["generator"]}


@app.get("/api/v1/runtime")
def runtime() -> dict[str, Any]:
    """当前运行模式（供界面显示徽标）。只返回模式与模型名，绝不返回密钥。"""
    return runtime_info(RUNTIME["mode"])


@app.post("/api/v1/ideas/expand")
def expand_idea(body: PremiseInput) -> dict[str, Any]:
    return _handle(lambda: expand(body.premise.strip()))


@app.post("/api/v1/scenes")
def create_scene(body: JsonPayload) -> dict[str, Any]:
    return _handle(lambda: store.create_scene(body.as_dict()))


@app.get("/api/v1/scenes/{scene_id}")
def get_scene(scene_id: str, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    return _handle(lambda: store.scene_view(scene_id, branch_id))


@app.patch("/api/v1/scenes/{scene_id}")
def patch_scene(scene_id: str, body: JsonPayload) -> dict[str, Any]:
    return _handle(lambda: store.update_scene(scene_id, body.as_dict()))


@app.get("/api/v1/scenes/{scene_id}/state")
def get_state(scene_id: str, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    return _handle(lambda: store.current_state(scene_id, branch_id))


@app.get("/api/v1/scenes/{scene_id}/events")
def get_events(scene_id: str, actor_id: str | None = Query(default=None), branch_id: str | None = Query(default=None)) -> list[dict[str, Any]]:
    return _handle(lambda: store.visible_events(scene_id, actor_id, branch_id))


@app.get("/api/v1/scenes/{scene_id}/replay")
def get_replay(scene_id: str, branch_id: str | None = Query(default=None),
               expected_revision: int | None = Query(default=None, ge=0)) -> dict[str, Any]:
    return _handle(lambda: store.replay(scene_id, branch_id, expected_revision))


@app.get("/api/v1/scenes/{scene_id}/facts")
def get_facts(scene_id: str, actor_id: str | None = Query(default=None), branch_id: str | None = Query(default=None)) -> list[dict[str, Any]]:
    return _handle(lambda: store.visible_facts(scene_id, actor_id, branch_id))


@app.post("/api/v1/scenes/{scene_id}/drafts")
def create_draft(scene_id: str, body: JsonPayload) -> dict[str, Any]:
    return _handle(lambda: store.create_draft(scene_id, body.as_dict()))


@app.get("/api/v1/drafts/{draft_id}")
def get_draft(draft_id: str) -> dict[str, Any]:
    return _handle(lambda: store.get_draft(draft_id))


@app.patch("/api/v1/drafts/{draft_id}")
def patch_draft(draft_id: str, body: JsonPayload) -> dict[str, Any]:
    return _handle(lambda: store.patch_draft(draft_id, body.as_dict()))


@app.post("/api/v1/drafts/{draft_id}/preview")
def preview_draft(draft_id: str, body: JsonPayload | None = None) -> dict[str, Any]:
    payload = body.as_dict() if body is not None else {}
    return _handle(lambda: store.preview_draft(draft_id, expected_version=payload.get("expected_version", payload.get("version"))))


@app.post("/api/v1/drafts/{draft_id}/commit")
def commit_draft(draft_id: str, body: JsonPayload | None = None) -> dict[str, Any]:
    payload = body.as_dict() if body is not None else {}
    expected = payload.get("revision")
    return _handle(lambda: store.commit_draft(draft_id, expected_revision=expected, idempotency_key=payload.get("idempotency_key"), expected_version=payload.get("expected_version", payload.get("version"))))


@app.post("/api/v1/drafts/{draft_id}/discard")
def discard_draft(draft_id: str, body: JsonPayload | None = None) -> dict[str, Any]:
    payload = body.as_dict() if body is not None else {}
    return _handle(lambda: store.discard_draft(draft_id, expected_version=payload.get("expected_version", payload.get("version"))))

@app.post("/api/v1/requests/{request_id}/cancel")
def cancel_request(request_id: str) -> dict[str, Any]:
    return _handle(lambda: store.cancel_request(request_id))

@app.get("/api/v1/scenes/{scene_id}/actors/{actor_id}/context")
def get_context(scene_id: str, actor_id: str, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    return _handle(lambda: store.context(scene_id, actor_id, branch_id))


@app.post("/api/v1/scenes/{scene_id}/branches")
def create_branch(scene_id: str, body: JsonPayload) -> dict[str, Any]:
    return _handle(lambda: store.create_branch(scene_id, body.as_dict()))


@app.post("/api/v1/scenes/{scene_id}/directives")
def create_directive(scene_id: str, body: JsonPayload) -> dict[str, Any]:
    return _handle(lambda: store.add_directive(scene_id, body.as_dict()))


@app.delete("/api/v1/scenes/{scene_id}/directives/{directive_id}")
def delete_directive(scene_id: str, directive_id: str, branch_id: str | None = Query(default=None)) -> dict[str, Any]:
    return _handle(lambda: store.remove_directive(scene_id, directive_id, branch_id))


@app.post("/api/v1/scenes/{scene_id}/beats/advance")
def advance_beat(scene_id: str, body: JsonPayload) -> dict[str, Any]:
    """作者确认本拍完成 → 进入下一拍（系统不自动推进）。"""
    return _handle(lambda: store.advance_beat(scene_id, body.as_dict()))


@app.post("/api/v1/scenes/{scene_id}/outputs")
def create_output(scene_id: str, body: JsonPayload) -> dict[str, Any]:
    return _handle(lambda: store.create_output(scene_id, body.as_dict()))

@app.get("/api/v1/scenes/{scene_id}/outputs")
def list_outputs(scene_id: str) -> list[dict[str, Any]]:
    return _handle(lambda: store.list_outputs(scene_id))

@app.get("/api/v1/outputs/{output_id}")
def get_output(output_id: str) -> dict[str, Any]:
    return _handle(lambda: store.get_output(output_id))

@app.patch("/api/v1/outputs/{output_id}")
def patch_output(output_id: str, body: JsonPayload) -> dict[str, Any]:
    return _handle(lambda: store.update_output(output_id, body.as_dict()))


# ---------- T1 美术素材：文生图（背板 / 立绘 / 道具参考）----------
# 图只做视觉层，不参与世界状态裁决；每条素材都带提示词、模型与时间戳，可追溯。

class ArtifactRequest(BaseModel):
    model_config = {"extra": "forbid"}
    kind: str = Field(pattern="^(backdrop|portrait|prop)$")
    actor_id: str | None = None
    item_id: str | None = None
    prompt: str | None = None
    size: str | None = None


@app.get("/api/v1/images/runtime")
def images_runtime() -> dict[str, Any]:
    return image_assets.runtime_info()


@app.get("/api/v1/scenes/{scene_id}/artifacts")
def list_artifacts(scene_id: str) -> list[dict[str, Any]]:
    return _handle(lambda: image_assets.list_assets(scene_id))


@app.post("/api/v1/scenes/{scene_id}/artifacts", status_code=201)
def create_artifact(scene_id: str, body: ArtifactRequest) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        view = store.scene_view(scene_id)
        spec = view.get("scene_spec") or view.get("spec") or {}
        return image_assets.generate_artifact(scene_id, spec, body.kind, actor_id=body.actor_id,
                                             item_id=body.item_id, prompt=body.prompt, size=body.size)
    try:
        return run()
    except image_assets.MissingImageKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except image_assets.ImageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/assets/{asset_id}")
def get_asset(asset_id: str) -> FileResponse:
    path = image_assets.asset_file(asset_id)
    if path is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    return FileResponse(path, media_type="image/png")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8200, reload=False)