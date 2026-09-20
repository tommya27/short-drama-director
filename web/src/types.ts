export type SceneManifest = Record<string, unknown> & { scene_key?: string; renderer_type?: string; camera_presets?: Array<string | { id: string; label?: string; position?: [number, number, number]; target?: [number, number, number] }> };
export type ActorSpec = { id: string; name: string; role: string; goal?: string; secret?: string; location?: string; color?: string; position?: { x: number; y: number; z?: number } };
export type SceneSpec = {
  scene_id: string; title: string; premise: string; genre: string; location: string; locations: string[];
  actors: ActorSpec[]; characters?: ActorSpec[]; goals: string[]; goal?: string; conflict: string;
  relationships: string[]; items: ItemState[]; facts: FactState[]; author_facts: string[]; scene_manifest: SceneManifest;
  contract?: Record<string, string>; beats?: DramaticBeat[]; dramatic_source?: { contract?: string; beats?: string };
};
export type ActorState = ActorSpec & { status?: "active" | "watching" | "waiting" | string; history?: string[]; known_fact_ids?: string[] };
export type ItemState = { id: string; name: string; holder?: string | null; location?: string | null; state?: string; [key: string]: unknown };
export type FactState = { id: string; label: string; value?: string; text?: string; description?: string; source?: string; known_by?: string[]; visibility?: string; owner?: string; confidence?: string; [key: string]: unknown };
export type SceneEvent = {
  id: string; step: number; actor_id: string; target_id?: string | null; action: string; dialogue?: string;
  inner_thought?: string; action_type?: string; location?: string; move_to?: string; visibility?: string; source?: string;
  beat_id?: string; tension_delta?: number; intent?: string; obstacle?: string; consequence?: string; revealed_information?: string[]; caused_by_event_ids?: string[];
  proposed_change?: Record<string, unknown>; committed_change?: boolean; observed_by?: string[]; checks?: Array<Record<string, unknown>>;
  created_at?: string; transfer?: { item_id: string; to_actor_id: string }; reveal_fact_ids?: string[]; [key: string]: unknown;
};
export type Directive = { id: string; text: string; target_actor_id?: string | null; start_step: number; end_step?: number | null; status: "pending" | "applied" | string; created_at?: string; applied_step?: number };
export type WorldSnapshot = {
  branch_id: string; revision: number; step: number; actors: Record<string, ActorState>; locations: string[];
  items: Record<string, ItemState>; facts: FactState[]; events: SceneEvent[]; directives: Directive[]; beat_state?: BeatState; [key: string]: unknown;
};
export type SceneDraft = {
  request_id?: string;
  draft_id: string; scene_id: string; branch_id: string; version: number; base_revision: number; candidate_events: SceneEvent[];
  state_diff?: Record<string, unknown>; preview_state?: WorldSnapshot; proposed_state?: WorldSnapshot; locks: string[];
  validation?: { valid?: boolean; ok?: boolean; errors?: string[]; warnings?: string[]; checks?: Array<Record<string, unknown>> };
  generation_source?: string | null; assessment?: DramaticAssessment | null;
  status: "pending" | "previewed" | "committed" | "discarded" | string; committed_revision?: number; updated_at?: string; [key: string]: unknown;
};
export type RunPhase = "idle" | "generating" | "review" | "scheduled" | "cancelling";
export type Branch = { branch_id: string; name: string; parent_branch_id?: string | null; created_at?: string };
export type SceneRecord = { scene_id: string; scene_spec: SceneSpec; spec?: SceneSpec; state?: WorldSnapshot; active_branch_id: string; branches: Branch[]; created_at?: string; updated_at?: string };
export type OutputType = "scene_card" | "screenplay" | "storyboard";
export type SceneOutput = { version?: number; output_id?: string; scene_id: string; branch_id: string; type: OutputType; content: string | Record<string, unknown> | unknown[]; source_event_ids: string[]; revision: number; created_at?: string; source?: string; polished?: boolean; polish_reason?: string | null };
export type ReplayFrame = { frame_id: string; source_branch_id: string; revision: number; reason: string; scene_spec: SceneSpec; state: WorldSnapshot };
export type ReplayHistory = { scene_id: string; branch_id: string; revision: number; frames: ReplayFrame[] };
export type StageMotion = { paused: boolean; speed: number; seek: number };
/** 剧情结构层：本拍信息、逐项检查与整体评估（来自后端 assessment）。 */
export type DramaticBeat = { beat_id: string; purpose: string; pressure?: string; information_change?: string; completion_signal?: string };
export type DramaticCheck = { item: string; status: string; detail: string };
export type DramaticAssessment = { beat?: DramaticBeat; beat_index?: number; beat_total?: number; tension?: number; checks?: DramaticCheck[]; warnings?: string[]; passed?: number; total?: number; suggestion?: string };
export type BeatState = { index?: number; completed_beats?: string[]; tension?: number };
/** T1 美术素材：文生图产出，带提示词/模型/时间戳；仅作视觉层，不参与世界状态裁决。 */
export type SceneArtifact = {
  asset_id: string; scene_id: string; kind: "backdrop" | "portrait" | "prop"; label: string;
  prompt: string; model: string; size?: string; created_at: string; url: string;
  actor_id?: string | null; item_id?: string | null; sha256?: string; bytes?: number;
};
export type WorldStageProps = { scene: SceneSpec; snapshot: WorldSnapshot; events: SceneEvent[]; selectedActor: string | null; onActorSelect: (actorId: string) => void; motion?: StageMotion; activeEventId?: string | null; artifacts?: SceneArtifact[]; dialogueLines?: boolean; showBubbles?: boolean };
export function actorsList(snapshot?: WorldSnapshot | null): ActorState[] { return snapshot ? Object.values(snapshot.actors ?? {}) : []; }
export function eventActorName(event: SceneEvent, scene: SceneSpec | null, snapshot?: WorldSnapshot | null): string { return snapshot?.actors?.[event.actor_id]?.name ?? scene?.actors.find((actor) => actor.id === event.actor_id)?.name ?? event.actor_id; }
export function outputText(content: SceneOutput["content"]): string { return typeof content === "string" ? content : JSON.stringify(content, null, 2); }
