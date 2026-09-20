import type { SceneDraft, SceneOutput, SceneRecord, SceneSpec, WorldSnapshot, OutputType, SceneEvent, Directive, ReplayHistory, SceneArtifact, DramaticBeat, BeatState } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") || "http://127.0.0.1:8200/api/v1";
/** 素材 URL 是后端相对路径（/api/v1/assets/...），这里补成绝对地址。 */
export const assetSrc = (url: string) => (url.startsWith("http") ? url : `${API_BASE.replace(/\/api\/v1$/, "")}${url}`);
export type ImageRuntime = { image_model: string; key_present: boolean; configured: boolean; kinds: Array<{ kind: string; label: string }>; assets_dir: string; style_suffix: string };

/** 后端运行模式：live=真实模型生成，offline=离线确定性规则。响应不含密钥。 */
export type RuntimeInfo = { mode: "live" | "offline"; generator: string; model: string; base_url: string; key_present: boolean; label: string; detail: string; mode_env: string; key_env_names: string[] };

export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }

async function request<T>(path: string, method = "GET", body?: unknown, options: { keepalive?: boolean } = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body), ...options });
  } catch {
    throw new ApiError(0, "无法连接本地剧情服务。请确认后端 8200 已启动，然后重试。你的未保存编辑仍在页面中。");
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : Array.isArray(payload.detail) ? payload.detail.map((x: { msg: string }) => x.msg).join("；") : "请求未完成";
    throw new ApiError(response.status, response.status === 409 ? `版本已变化：${detail}。请刷新正式状态后重试。` : detail);
  }
  return payload as T;
}

export function normalizeSpec(payload: Partial<SceneSpec> & Record<string, unknown>, premise = ""): SceneSpec {
  const source = payload ?? {};
  return {
    scene_id: String(source.scene_id ?? ""), title: String(source.title ?? "未命名场景"), premise: String(source.premise ?? premise),
    genre: String(source.genre ?? "短剧"), location: String(source.location ?? ""), locations: source.locations ?? [],
    actors: source.actors ?? source.characters ?? [], goals: source.goals ?? [], goal: source.goal ?? "",
    conflict: String(source.conflict ?? premise), relationships: source.relationships ?? [], items: source.items ?? [],
    facts: source.facts ?? [], author_facts: source.author_facts ?? [], scene_manifest: source.scene_manifest ?? { scene_key: "generic" },
    // 剧情结构层字段必须透传，否则前端拿不到节拍与契约（按钮会被误禁用）
    contract: (source.contract as Record<string, string>) ?? {},
    beats: (source.beats as DramaticBeat[]) ?? [],
    dramatic_source: (source.dramatic_source as { contract?: string; beats?: string }) ?? undefined
  };
}

function normalizeRecord(payload: SceneRecord): SceneRecord {
  return { ...payload, scene_spec: normalizeSpec((payload.scene_spec ?? payload.spec ?? payload) as SceneSpec & Record<string, unknown>), branches: payload.branches ?? [] };
}

type OutputResponse = Omit<SceneOutput, "type"> & { type?: OutputType; kind?: "scene_card" | "script" | "storyboard" };
function normalizeOutput(payload: OutputResponse): SceneOutput {
  const type = payload.type ?? (payload.kind === "script" ? "screenplay" : payload.kind) ?? "screenplay";
  return { ...payload, type };
}

export const api = {
  getRuntime: () => request<RuntimeInfo>("/runtime"),
  getImageRuntime: () => request<ImageRuntime>("/images/runtime"),
  listArtifacts: (sceneId: string) => request<SceneArtifact[]>(`/scenes/${encodeURIComponent(sceneId)}/artifacts`),
  generateArtifact: (sceneId: string, payload: { kind: "backdrop" | "portrait" | "prop"; actor_id?: string; item_id?: string; prompt?: string; size?: string }) =>
    request<SceneArtifact>(`/scenes/${encodeURIComponent(sceneId)}/artifacts`, "POST", payload),
  expandIdea: (premise: string) => request<{ premise: string; questions: string[]; scene_spec: SceneSpec; source?: "llm" | "rule"; fallback_reason?: string }>("/ideas/expand", "POST", { premise }),
  createScene: async (spec: SceneSpec) => normalizeRecord(await request<SceneRecord>("/scenes", "POST", spec)),
  getScene: async (id: string, branchId?: string) => normalizeRecord(await request<SceneRecord>(`/scenes/${encodeURIComponent(id)}${branchId ? `?branch_id=${encodeURIComponent(branchId)}` : ""}`)),
  patchScene: async (id: string, payload: Record<string, unknown>) => normalizeRecord(await request<SceneRecord>(`/scenes/${encodeURIComponent(id)}`, "PATCH", payload)),
  getState: (id: string, branchId: string) => request<WorldSnapshot>(`/scenes/${encodeURIComponent(id)}/state?branch_id=${encodeURIComponent(branchId)}`),
  getReplay: async (id: string, branchId: string, revision: number) => {
    const history = await request<ReplayHistory>(`/scenes/${encodeURIComponent(id)}/replay?branch_id=${encodeURIComponent(branchId)}&expected_revision=${revision}`);
    return { ...history, frames: history.frames.map(frame => ({ ...frame, scene_spec: normalizeSpec(frame.scene_spec as SceneSpec & Record<string, unknown>) })) };
  },
  getContext: (id: string, actorId: string, branchId: string) => request<unknown>(`/scenes/${encodeURIComponent(id)}/actors/${encodeURIComponent(actorId)}/context?branch_id=${encodeURIComponent(branchId)}`),
  createDraft: (id: string, branchId: string, revision: number, requestId: string) => request<SceneDraft>(`/scenes/${encodeURIComponent(id)}/drafts`, "POST", { branch_id: branchId, base_revision: revision, request_id: requestId }),
  cancelRequest: (requestId: string) => request<{ request_id: string; status: string }>(`/requests/${encodeURIComponent(requestId)}/cancel`, "POST", {}, { keepalive: true }),
  getDraft: (id: string) => request<SceneDraft>(`/drafts/${encodeURIComponent(id)}`),
  editDraft: (draft: SceneDraft, events: SceneEvent[], locks = draft.locks, unlockPaths: string[] = []) => request<SceneDraft>(`/drafts/${encodeURIComponent(draft.draft_id)}`, "PATCH", { expected_version: draft.version, candidate_events: events, locks, unlock_paths: unlockPaths }),
  previewDraft: (draft: SceneDraft) => request<SceneDraft>(`/drafts/${encodeURIComponent(draft.draft_id)}/preview`, "POST", { expected_version: draft.version }),
  commitDraft: (draft: SceneDraft, revision: number) => request<SceneDraft>(`/drafts/${encodeURIComponent(draft.draft_id)}/commit`, "POST", { expected_version: draft.version, revision, idempotency_key: draft.draft_id }),
  discardDraft: (draft: SceneDraft) => request<SceneDraft>(`/drafts/${encodeURIComponent(draft.draft_id)}/discard`, "POST", { expected_version: draft.version }),
  advanceBeat: (id: string, branchId: string, revision: number) => request<{ scene_id: string; branch_id: string; revision: number; beat_state: BeatState; beat: DramaticBeat; beat_total: number }>(`/scenes/${encodeURIComponent(id)}/beats/advance`, "POST", { branch_id: branchId, base_revision: revision }),
  createBranch: (id: string, branchId: string, name: string, revision: number) => request<{ branch_id: string }>(`/scenes/${encodeURIComponent(id)}/branches`, "POST", { from_branch_id: branchId, name, base_revision: revision, activate: true }),
  addDirective: (id: string, branchId: string, text: string, actorId: string | null, step: number) => request<Directive>(`/scenes/${encodeURIComponent(id)}/directives`, "POST", { branch_id: branchId, text, target_actor_id: actorId, start_step: step }),
  cancelDirective: (id: string, branchId: string, directiveId: string) => request(`/scenes/${encodeURIComponent(id)}/directives/${encodeURIComponent(directiveId)}?branch_id=${encodeURIComponent(branchId)}`, "DELETE"),
  getOutputs: async (id: string) => (await request<OutputResponse[]>(`/scenes/${encodeURIComponent(id)}/outputs`)).map(normalizeOutput),
  createOutput: async (id: string, branchId: string, type: OutputType, eventIds: string[], revision: number, polish = false) => normalizeOutput(await request<OutputResponse>(`/scenes/${encodeURIComponent(id)}/outputs`, "POST", { branch_id: branchId, type, source_event_ids: eventIds, base_revision: revision, polish })),
  saveOutput: async (output: SceneOutput, content: string) => normalizeOutput(await request<OutputResponse>(`/outputs/${encodeURIComponent(output.output_id ?? "")}`, "PATCH", { content, expected_version: output.version }))
};
