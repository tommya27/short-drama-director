import { useEffect, useMemo, useRef, useState } from "react";
import { api, normalizeSpec, ApiError, type RuntimeInfo } from "./api";
import { WorldStage } from "./WorldStage";
import { useReplay, type ReplayController } from "./useReplay";
import { ReplayControls } from "./ReplayControls";
import { sceneManifestOptions } from "./stage-manifest";
import type { ActorSpec, BeatState, Branch, DramaticBeat, FactState, OutputType, RunPhase, SceneArtifact, SceneDraft, SceneEvent, SceneOutput, SceneRecord, SceneSpec, WorldSnapshot } from "./types";
import { actorsList, eventActorName, outputText } from "./types";
import "./styles.css";

const outputNames: Record<OutputType, string> = { scene_card: "场次卡", screenplay: "剧本草稿", storyboard: "分镜草稿" };
const starters = ["暴雨夜，董事会要求创始人卖掉专利，但她带来一份新的授权书。", "客栈打烊前，掌柜、旅人和捕快发现三人找的是同一个人。", "古宅寿宴上，女儿拿出一封写给失踪母亲的信。"];
const copy = <T,>(v: T): T => JSON.parse(JSON.stringify(v));
const message = (reason: unknown) => reason instanceof Error ? reason.message : String(reason);
const draftStorage = (scene: string, branch: string) => `director-draft:${scene}:${branch}`;
const closed = (draft: SceneDraft | null) => !draft || ["committed", "discarded"].includes(draft.status);

function route() {
  const segments = window.location.pathname.split("/").filter(Boolean);
  const id = segments[0] === "scene" ? decodeURIComponent(segments[1] ?? "") : "";
  return { id, view: segments[2] === "outputs" ? "outputs" : segments[2] === "branches" ? "branches" : "stage", branch: new URLSearchParams(window.location.search).get("branch") ?? "" } as const;
}

export default function App() {
  const [location, setLocation] = useState(route);
  const [record, setRecord] = useState<SceneRecord | null>(null);
  const [snapshot, setSnapshot] = useState<WorldSnapshot | null>(null);
  const [draft, setDraft] = useState<SceneDraft | null>(null);
  const [candidateEvents, setCandidateEvents] = useState<SceneEvent[]>([]);
  const [selectedActor, setSelectedActor] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [premise, setPremise] = useState("");
  const [expanded, setExpanded] = useState<SceneSpec | null>(null);
  const [questions, setQuestions] = useState<string[]>([]);
  const [professional, setProfessional] = useState(localStorage.getItem("director-mode") === "professional");
  const [settings, setSettings] = useState<SceneSpec | null>(null);
  const [showFormal, setShowFormal] = useState(false);
  const [outputs, setOutputs] = useState<SceneOutput[]>([]);
  const [selectedOutputEvents, setSelectedOutputEvents] = useState<string[]>([]);
  const [continuous, setContinuous] = useState(false);
  const [runPhase, setRunPhase] = useState<RunPhase>("idle");
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [artifacts, setArtifacts] = useState<SceneArtifact[]>([]);
  const [openingSource, setOpeningSource] = useState("");
  const [dialogueLines, setDialogueLines] = useState(localStorage.getItem("director-dialogue-lines") !== "off");
  const [artBusy, setArtBusy] = useState("");
  const mounted = useRef(true);
  const viewEpoch = useRef(0);
  const loopEnabled = useRef(false);
  const loopEpoch = useRef(0);
  const nextRoundTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generation = useRef<{ requestId: string; epoch: number; cancelled: boolean } | null>(null);

  const scene = record?.scene_spec ?? null;
  const formal = snapshot;
  const activeDraft = closed(draft) ? null : draft;
  const replay = useReplay(location.id, formal?.branch_id ?? location.branch, formal?.revision ?? 0, location.view);
  const displayScene = replay.frame?.scene_spec ?? scene;
  const displaySnapshot = replay.frame?.state ?? (activeDraft && !showFormal ? (activeDraft.preview_state ?? activeDraft.proposed_state ?? formal) : formal);
  const displayEvents = activeDraft && !showFormal ? [...(formal?.events ?? []), ...candidateEvents] : formal?.events ?? [];
  const branchId = formal?.branch_id ?? record?.active_branch_id ?? "main";
  const dirty = !!activeDraft && JSON.stringify(candidateEvents) !== JSON.stringify(activeDraft.candidate_events);
  const visibleEvents = replay.frame?.state.events ?? displayEvents;
  const selected = visibleEvents.find((event) => event.id === selectedEvent) ?? visibleEvents.at(-1);
  const beats = scene?.beats ?? [];
  const beatState = (formal?.beat_state ?? {}) as BeatState;
  const assessment = activeDraft?.assessment ?? null;
  const beatIndex = beatState.index ?? assessment?.beat_index ?? 0;
  const beat = assessment?.beat ?? beats[beatIndex];
  const beatTotal = assessment?.beat_total ?? (beats.length || 5);
  const canAdvanceBeat = !!formal && !activeDraft && !busy && beatIndex < Math.max(1, beatTotal) - 1;
  useEffect(() => { let alive = true; void api.getRuntime().then((info) => { if (alive) setRuntime(info); }).catch(() => { if (alive) setRuntime(null); }); return () => { alive = false; }; }, []);
  useEffect(() => { const id = location.id; if (!id) { setArtifacts([]); return; } let alive = true; void api.listArtifacts(id).then((rows) => { if (alive) setArtifacts(rows); }).catch(() => { if (alive) setArtifacts([]); }); return () => { alive = false; }; }, [location.id, record?.active_branch_id]);
  useEffect(() => { if (!replay.frame) return; const event = replay.frame.state.events.find(e => e.id === replay.eventId) ?? replay.frame.state.events.at(-1); setSelectedEvent(event?.id ?? null); if (event) setSelectedActor(event.actor_id); }, [replay.frame, replay.eventId]);
  const latest = useRef({ scene, formal, activeDraft, busy, view: location.view });
  latest.current = { scene, formal, activeDraft, busy, view: location.view };

  // Stop the schedule immediately. Keep the generation HTTP response readable so
  // a response racing cancellation can still be discarded on the server.
  function stopRun(announce = true) {
    loopEnabled.current = false;
    loopEpoch.current += 1;
    if (nextRoundTimer.current !== null) clearTimeout(nextRoundTimer.current);
    nextRoundTimer.current = null;
    const pending = generation.current;
    if (pending) pending.cancelled = true;
    generation.current = null;
    if (mounted.current) {
      setContinuous(false);
      setRunPhase(pending ? "cancelling" : "idle");
      if (pending) setBusy("");
      if (announce) setNotice(pending ? "正在取消本轮请求；迟到结果不会加入剧情。" : "已停止慢速逐轮。现有候选保留，仍需你手动决定。");
    }
    if (pending) {
      const epoch = viewEpoch.current;
      void api.cancelRequest(pending.requestId)
        .then(() => { if (mounted.current && epoch === viewEpoch.current && !generation.current) { setRunPhase("idle"); if (announce) setNotice("请求已取消。迟到结果会被丢弃，正式剧情未改变。"); } })
        .catch((reason) => { if (mounted.current && epoch === viewEpoch.current) { setRunPhase("idle"); setError(`已停止本地推进，但后端取消尚未确认：${message(reason)}。迟到结果仍会被忽略。`); } });
    }
  }

  const navigate = (id = "", view = "stage", branch = "") => { stopRun(false); viewEpoch.current += 1; const path = id ? `/scene/${encodeURIComponent(id)}${view === "stage" ? "" : `/${view}`}${branch ? `?branch=${encodeURIComponent(branch)}` : ""}` : "/"; window.history.pushState({}, "", path); setLocation(route()); };
  useEffect(() => {
    mounted.current = true;
    const pop = () => { stopRun(false); viewEpoch.current += 1; setLocation(route()); };
    const leave = () => { stopRun(false); viewEpoch.current += 1; };
    window.addEventListener("popstate", pop);
    window.addEventListener("pagehide", leave);
    return () => { mounted.current = false; stopRun(false); viewEpoch.current += 1; window.removeEventListener("popstate", pop); window.removeEventListener("pagehide", leave); };
  }, []);

  async function load(sceneId: string, branch?: string, restore = false, epoch = viewEpoch.current) {
    const nextRecord = await api.getScene(sceneId, branch);
    const nextBranch = branch || nextRecord.active_branch_id;
    const nextState = await api.getState(sceneId, nextBranch);
    if (!mounted.current || epoch !== viewEpoch.current) return null;
    setRecord(nextRecord); setSnapshot(nextState); setSelectedActor((current) => current && nextState.actors[current] ? current : Object.keys(nextState.actors)[0] ?? null);
    if (restore) {
      const id = sessionStorage.getItem(draftStorage(sceneId, nextBranch));
      if (id) { const saved = await api.getDraft(id); if (!mounted.current || epoch !== viewEpoch.current) return null; if (saved.branch_id === nextBranch && !closed(saved)) { setDraft(saved); setCandidateEvents(copy(saved.candidate_events)); setRunPhase("review"); } else { sessionStorage.removeItem(draftStorage(sceneId, nextBranch)); setDraft(null); setCandidateEvents([]); } }
      else { setDraft(null); setCandidateEvents([]); }
    }
    return nextState;
  }
  useEffect(() => {
    const epoch = viewEpoch.current;
    if (!location.id) { setRecord(null); setSnapshot(null); setDraft(null); return; }
    setBusy("正在恢复场景"); setError(""); setRunPhase("idle");
    void load(location.id, location.branch, true, epoch)
      .then(async () => { if (location.view === "outputs") { const result = await api.getOutputs(location.id); if (mounted.current && epoch === viewEpoch.current) setOutputs(result); } })
      .catch((reason) => { if (mounted.current && epoch === viewEpoch.current) { stopRun(false); setError(message(reason)); } })
      .finally(() => { if (mounted.current && epoch === viewEpoch.current) setBusy(""); });
  }, [location.id, location.branch, location.view]);
  async function act(label: string, work: () => Promise<void>) { const epoch = viewEpoch.current; setBusy(label); setError(""); try { await work(); } catch (reason) { if (mounted.current && epoch === viewEpoch.current) { stopRun(false); setError(message(reason)); } } finally { if (mounted.current && epoch === viewEpoch.current) setBusy(""); } }
  function setDraftState(next: SceneDraft) { setDraft(next); setCandidateEvents(copy(next.candidate_events)); if (closed(next)) sessionStorage.removeItem(draftStorage(next.scene_id, next.branch_id)); else sessionStorage.setItem(draftStorage(next.scene_id, next.branch_id), next.draft_id); }
  function toggleMode() { setProfessional((old) => { localStorage.setItem("director-mode", old ? "guided" : "professional"); return !old; }); }

  async function expandIdea() { await act("正在拆解想法", async () => { const result = await api.expandIdea(premise.trim()); setExpanded(normalizeSpec(result.scene_spec as SceneSpec & Record<string, unknown>, premise)); setQuestions(result.questions ?? []); setOpeningSource(result.source === "llm" ? "开场由真模型生成，可直接编辑" : `开场由本地规则生成${result.fallback_reason ? `（模型不可用：${result.fallback_reason}）` : ""}，可直接编辑`); setNotice("建议设定仍可编辑；确认后才会建立正式沙盘。"); }); }
  async function createScene(spec: SceneSpec) { await act("正在建立沙盘", async () => { const next = await api.createScene(spec); setExpanded(null); setRecord(next); navigate(next.scene_id); setNotice("沙盘已建立。候选变化不会自动写入正式剧情。"); }); }
  async function step() {
    const current = latest.current;
    if (!current.scene || !current.formal || current.activeDraft || current.busy || current.view !== "stage" || generation.current) return;
    if (nextRoundTimer.current !== null) clearTimeout(nextRoundTimer.current);
    nextRoundTimer.current = null;
    const pending = { requestId: crypto.randomUUID(), epoch: viewEpoch.current, cancelled: false };
    generation.current = pending;
    setRunPhase("generating"); setBusy("角色正在形成候选行动"); setError(""); setShowFormal(false);
    try {
      const next = await api.createDraft(current.scene.scene_id, current.formal.branch_id, current.formal.revision, pending.requestId);
      if (!mounted.current || generation.current !== pending || pending.epoch !== viewEpoch.current) {
        // Cancellation may arrive after the server finished generating. Explicitly
        // discard that returned draft; never restore it into the selected scene.
        await api.discardDraft(next).catch((reason) => { if (mounted.current && pending.epoch === viewEpoch.current) setError(`迟到结果已从页面排除，但后端丢弃尚未确认：${message(reason)}`); });
        return;
      }
      generation.current = null;
      setDraftState(next); setSelectedEvent(next.candidate_events[0]?.id ?? null); setRunPhase("review");
      setNotice(loopEnabled.current ? "慢速逐轮已暂停待审。请手动预览并提交；提交成功 2 秒后生成下一轮。" : "候选已生成。请编辑、预览，再决定是否提交；不会自动提交。");
    } catch (reason) {
      if (mounted.current && generation.current === pending && pending.epoch === viewEpoch.current) {
        stopRun(false); setError(message(reason));
      }
    } finally {
      if (generation.current === pending) generation.current = null;
      if (mounted.current && !pending.cancelled && pending.epoch === viewEpoch.current && !generation.current) setBusy("");
    }
  }
  function startSlow() {
    if (latest.current.busy || latest.current.activeDraft || generation.current) return;
    loopEnabled.current = true; loopEpoch.current += 1; setContinuous(true);
    void step();
  }
  function scheduleNextRound() {
    const epoch = viewEpoch.current;
    const loop = loopEpoch.current;
    if (!loopEnabled.current || !mounted.current) return;
    setRunPhase("scheduled");
    setNotice("本轮已提交。慢速逐轮将在 2 秒后生成下一轮候选；可随时停止。");
    nextRoundTimer.current = setTimeout(() => {
      nextRoundTimer.current = null;
      if (mounted.current && epoch === viewEpoch.current && loop === loopEpoch.current && loopEnabled.current) void step();
    }, 2000);
  }
  async function saveCandidate() { if (!activeDraft) return; await act("正在保存候选编辑", async () => { setDraftState(await api.editDraft(activeDraft, candidateEvents)); setNotice("候选编辑已保存。重新预览后才能提交。"); }); }
  async function toggleLock(path: string, currentlyLocked: boolean) {
    if (!activeDraft) return;
    await act(currentlyLocked ? "正在解锁候选字段" : "正在锁定候选字段", async () => {
      const locks = currentlyLocked ? activeDraft.locks.filter((item) => item !== path) : [...activeDraft.locks, path];
      const next = await api.editDraft(activeDraft, candidateEvents, locks, currentlyLocked ? [path] : []);
      setDraftState(next); setNotice(currentlyLocked ? "字段已解锁。" : "字段已锁定，重新生成时会保留。");
    });
  }
  async function preview() { if (!activeDraft) return; await act("正在验证候选变化", async () => { const saved = dirty ? await api.editDraft(activeDraft, candidateEvents) : activeDraft; const next = await api.previewDraft(saved); setDraftState(next); setShowFormal(false); setNotice("预览完成。舞台展示候选投影，正式状态未改变。"); }); }
  async function commit() {
    if (!activeDraft || !formal || activeDraft.status !== "previewed" || dirty || !scene) return;
    const epoch = viewEpoch.current;
    await act("正在提交剧情", async () => {
      await api.commitDraft(activeDraft, formal.revision);
      const refreshed = await load(scene.scene_id, branchId, false, epoch);
      if (!refreshed || !mounted.current || epoch !== viewEpoch.current) return;
      sessionStorage.removeItem(draftStorage(scene.scene_id, branchId));
      setDraft(null); setCandidateEvents([]); setShowFormal(true); setRunPhase("idle");
      setNotice("已提交并刷新后端正式状态。");
      scheduleNextRound();
    });
  }
  async function discard() { if (!activeDraft) return; stopRun(false); await act("正在丢弃候选", async () => { await api.discardDraft(activeDraft); sessionStorage.removeItem(draftStorage(activeDraft.scene_id, activeDraft.branch_id)); setDraft(null); setCandidateEvents([]); setShowFormal(true); setNotice("候选已丢弃，慢速逐轮已停止，正式剧情保持不变。"); }); }
  async function saveSettings(spec: SceneSpec) { if (!scene || !formal) return; await act("正在保存场景设定", async () => { await api.patchScene(scene.scene_id, { ...spec, characters: spec.actors, branch_id: branchId, base_revision: formal.revision }); setSettings(null); await load(scene.scene_id, branchId); setNotice("设定已保存。"); }); }

  async function generateArtifacts() { if (!scene) return; setError(""); setArtBusy("生成场景背板…"); try { await api.generateArtifact(scene.scene_id, { kind: "backdrop" }); for (const actor of scene.actors) { setArtBusy(`生成 ${actor.name} 立绘…`); await api.generateArtifact(scene.scene_id, { kind: "portrait", actor_id: actor.id }); } setArtifacts(await api.listArtifacts(scene.scene_id)); setNotice("美术素材已生成：背板与立绘均为文生图，提示词、模型与生成时间已记录。"); } catch (reason) { setError(message(reason)); } finally { setArtBusy(""); } }

  async function advanceBeat() {
    if (!scene || !formal) return;
    await act("正在进入下一段剧情", async () => {
      const next = await api.advanceBeat(scene.scene_id, branchId, formal.revision);
      setDraft(null);
      await load(scene.scene_id, branchId);
      setNotice(`已进入剧情第 ${(next.beat_state?.index ?? 0) + 1} 段 / 共 ${next.beat_total} 段：${next.beat?.purpose ?? ""}（这一段的任务，见右栏剧情检查）。请重新生成候选。`);
    });
  }

  if (!location.id) return <Landing premise={premise} setPremise={setPremise} expanded={expanded} questions={questions} busy={busy} error={error} notice={notice} professional={professional} runtime={runtime} openingSource={openingSource} toggleMode={toggleMode} onExpand={expandIdea} onCreate={createScene} onCancel={() => setExpanded(null)} />;
  if (!scene || !formal || !displaySnapshot) return <div className="loading-page"><Brand onClick={() => navigate()} /><h1>{busy || "场景暂时无法加载"}</h1><Alert error={error} notice={notice} /><button className="secondary" onClick={() => setLocation(route())}>重试</button></div>;
  return <div className="app-shell"><header className="topbar"><Brand onClick={() => navigate()} /><div className="scene-heading"><span className={`eyebrow mode-badge mode-${runtime?.mode ?? "unknown"}`} title={runtime ? `${runtime.detail}（切换：${runtime.mode_env}）` : "正在读取运行模式"}>{runtime ? runtime.label : "读取运行模式…"}</span><h1>{scene.title}</h1></div><span className="revision">{record?.branches.find((b) => b.branch_id === branchId)?.name ?? "主线"} · 正式 r{formal.revision}</span><button className="ghost" onClick={toggleMode}>{professional ? "专业模式" : "小白引导"} ⇄</button><button className="ghost" onClick={() => navigate(scene.scene_id, "outputs", branchId)}>整理输出 ↗</button></header><Alert error={error} notice={notice} />{!professional && <div className="guide-bar"><b>{activeDraft ? "检查候选变化" : "先推进一步"}</b><span>{activeDraft ? "修改动作或对白后保存并预览。提交前正式世界不会改变。" : "每次只生成一轮候选，慢速模式也会停下来等你确认。"}</span><button onClick={toggleMode}>收起引导</button></div>}<main className={`workspace workspace-${location.view}`}><Sidebar scene={displayScene!} snapshot={displaySnapshot} selectedActor={selectedActor} onActor={setSelectedActor} view={location.view} onNavigate={(view) => navigate(scene.scene_id, view, branchId)} onEdit={() => { stopRun(false); setSettings(copy(scene)); }} disabled={!!activeDraft || !!replay.frame} /><section className="stage-column">{location.view === "stage" && <StageView replay={replay} scene={displayScene!} formal={formal} display={displaySnapshot} events={replay.frame?.state.events ?? displayEvents} selectedActor={selectedActor} onActor={setSelectedActor} selectedEvent={selectedEvent} onEvent={(id) => { setSelectedEvent(id); if (formal.events.some(e => e.id === id)) { stopRun(false); void replay.open(false, id); } else replay.exit(); }} showFormal={showFormal} setShowFormal={(value) => { replay.exit(); setShowFormal(value); }} activeDraft={activeDraft} candidateEvents={candidateEvents} setCandidateEvents={setCandidateEvents} dirty={dirty} busy={!!busy || !!replay.frame} onStep={step} onSave={saveCandidate} onPreview={preview} onCommit={commit} onDiscard={discard} onToggleLock={toggleLock} continuous={continuous} runPhase={runPhase} onStartSlow={startSlow} onStop={() => stopRun()} professional={professional} artifacts={artifacts} onGenerateArtifacts={generateArtifacts} artifactBusy={artBusy} dialogueLines={dialogueLines} onToggleDialogueLines={() => setDialogueLines((old) => { localStorage.setItem("director-dialogue-lines", old ? "off" : "on"); return !old; })} beat={beat} beatIndex={beatIndex} beatTotal={beatTotal} canAdvanceBeat={canAdvanceBeat} onAdvanceBeat={advanceBeat} />} {location.view === "branches" && <BranchView record={record!} snapshot={formal} activeDraft={!!activeDraft} busy={!!busy} onSwitch={(id) => navigate(scene.scene_id, "stage", id)} onFork={async (name) => { await act("正在复制分支", async () => { const next = await api.createBranch(scene.scene_id, branchId, name, formal.revision); navigate(scene.scene_id, "stage", next.branch_id); }); }} />} {location.view === "outputs" && <OutputView scene={scene} snapshot={formal} outputs={outputs} setOutputs={setOutputs} busy={!!busy} />} </section>{location.view === "stage" && <Inspector scene={displayScene!} snapshot={displaySnapshot} formal={replay.frame?.state ?? formal} selected={selected} selectedActor={selectedActor} branchId={branchId} activeDraft={replay.frame ? null : activeDraft} busy={!!busy || !!replay.frame || runPhase === "scheduled"} professional={professional && !replay.frame} onError={(reason) => { stopRun(false); setError(message(reason)); }} />}</main>{settings && <div className="modal-backdrop"><div className="setup-modal"><h2>编辑这场戏的设定</h2><SceneSetup initial={settings} onSave={saveSettings} onCancel={() => setSettings(null)} busy={!!busy} submitLabel="保存设定" existing /></div></div>}</div>;
}

function Alert({ error, notice }: { error: string; notice: string }) { return <div className="page-status">{error && <div className="alert error">⚠ {error}</div>}{!error && notice && <div className="notice">✦ {notice}</div>}</div>; }
function Brand({ onClick }: { onClick: () => void }) { return <button className="brand" onClick={onClick}><span className="brand-mark">场</span><span><strong>场戏</strong><small>AI 导演台</small></span></button>; }
function Landing(p: { premise: string; setPremise: (v: string) => void; expanded: SceneSpec | null; questions: string[]; busy: string; error: string; notice: string; professional: boolean; runtime: RuntimeInfo | null; openingSource: string; toggleMode: () => void; onExpand: () => void; onCreate: (spec: SceneSpec) => void; onCancel: () => void }) { return <div className="landing"><header className="landing-header"><Brand onClick={() => p.onCancel()} /><button className="ghost" onClick={p.toggleMode}>{p.professional ? "专业导演台" : "小白引导"} ⇄</button></header>{p.expanded ? <div className="setup-page"><div className="setup-intro"><span className="eyebrow">02 / 确认开场</span><h1>谁想要什么，谁有所隐瞒？</h1><p>这些建议可编辑，确认后才会建立共享世界。</p>{p.openingSource && <p className="muted">{p.openingSource} · 场景类型 {String((p.expanded.scene_manifest?.scene_key) ?? "generic")}</p>}<div className="question-tags">{p.questions.map((q) => <span key={q}>{q}</span>)}</div></div><Alert error={p.error} notice={p.notice} /><SceneSetup initial={p.expanded} onSave={p.onCreate} onCancel={p.onCancel} busy={!!p.busy} submitLabel="确认设定，进入沙盘" /></div> : <main className="hero"><div className="hero-kicker">一句话 / 一场戏 / 你的选择</div><h1>让角色先活起来，<br /><em>再决定故事往哪走。</em></h1><p className="hero-sub">多个角色在同一个虚拟世界中行动、交流、互相影响。<br />你观察、干预并确认剧情，再整理成剧本与分镜草稿。</p><div className="idea-box"><textarea rows={3} maxLength={1500} value={p.premise} onChange={(e) => p.setPremise(e.target.value)} placeholder="你脑中那一幕，发生了什么？" /><div className="idea-actions"><span>{p.premise.length} / 1500</span><button className="primary" disabled={!p.premise.trim() || !!p.busy} onClick={p.onExpand}>{p.busy || "拆解我的想法 →"}</button></div></div><div className="starter-row"><span>试试：</span>{starters.map((idea) => <button key={idea} onClick={() => p.setPremise(idea)}>{idea}</button>)}</div><Alert error={p.error} notice={p.notice} /><div className="promise-row"><span>◉ 角色只知道自己所见</span><span>◇ 候选由你确认</span><span>▤ 输出保留事件来源</span></div></main>}<footer className={`landing-footer mode-badge mode-${p.runtime?.mode ?? "unknown"}`} title={p.runtime?.detail ?? "正在读取运行模式"}>{p.runtime ? `${p.runtime.label} · ${p.runtime.detail}` : "正在读取运行模式…"}</footer></div>; }

function Sidebar({ scene, snapshot, selectedActor, onActor, view, onNavigate, onEdit, disabled }: { scene: SceneSpec; snapshot: WorldSnapshot; selectedActor: string | null; onActor: (id: string) => void; view: string; onNavigate: (view: string) => void; onEdit: () => void; disabled: boolean }) { return <aside className="left-rail"><div className="rail-section actors-section"><div className="section-label">场景角色 <span>{scene.actors.length}</span></div>{scene.actors.map((actor, index) => <button className={`actor-row ${selectedActor === actor.id ? "selected" : ""}`} key={actor.id} onClick={() => onActor(actor.id)}><span className="actor-avatar" style={{ background: actor.color ?? ["#806ee1", "#d38a59", "#39978d"][index % 3] }}>{actor.name.slice(0, 1)}</span><span className="actor-copy"><b>{actor.name}</b><small>{actor.role}</small></span></button>)}</div><div className="rail-section scene-section"><div className="section-label">这场戏</div><p className="scene-conflict">{scene.conflict}</p><div className="tag-row"><span className="tag purple">{scene.genre}</span><span className="tag">{scene.location}</span></div><button className="text-button" disabled={disabled} onClick={onEdit}>编辑设定</button></div><nav aria-label="创作视图" className="rail-section views-section"><div className="section-label">创作视图</div><button className={`tool-row ${view === "stage" ? "current" : ""}`} onClick={() => onNavigate("stage")}>◉ 剧情沙盘</button><button className={`tool-row ${view === "branches" ? "current" : ""}`} onClick={() => onNavigate("branches")}>⑂ 分支对比</button><button className={`tool-row ${view === "outputs" ? "current" : ""}`} onClick={() => onNavigate("outputs")}>▤ 剧本与分镜</button></nav><div className="rail-foot"><span className="online-dot" />正式 {snapshot.events.length} 个事件</div></aside>; }

function StageView(p: { replay: ReplayController; scene: SceneSpec; formal: WorldSnapshot; display: WorldSnapshot; events: SceneEvent[]; selectedActor: string | null; onActor: (id: string) => void; selectedEvent: string | null; onEvent: (id: string) => void; showFormal: boolean; setShowFormal: (v: boolean) => void; activeDraft: SceneDraft | null; candidateEvents: SceneEvent[]; setCandidateEvents: (v: SceneEvent[]) => void; dirty: boolean; busy: boolean; onStep: () => void; onSave: () => void; onPreview: () => void; onCommit: () => void; onDiscard: () => void; onToggleLock: (path: string, currentlyLocked: boolean) => void; continuous: boolean; runPhase: RunPhase; onStartSlow: () => void; onStop: () => void; professional: boolean; artifacts: SceneArtifact[]; onGenerateArtifacts: () => void; artifactBusy: string; dialogueLines: boolean; onToggleDialogueLines: () => void; beat?: DramaticBeat; beatIndex: number; beatTotal: number; canAdvanceBeat: boolean; onAdvanceBeat: () => void }) {
  const candidate = p.replay.frame ? null : p.activeDraft; const locked = (event: SceneEvent, field: string) => candidate?.locks.includes(`events.${event.id}.${field}`) ?? false; const change = (id: string, key: string, value: unknown) => p.setCandidateEvents(p.candidateEvents.map((e) => e.id === id ? { ...e, [key]: value } : e));
  return <><div className="stage-toolbar"><div className="state-switch"><button className={!candidate || p.showFormal ? "active" : ""} onClick={() => p.setShowFormal(true)}>正式 · r{p.formal.revision}</button><button className={candidate && !p.showFormal ? "active" : ""} disabled={!candidate} onClick={() => p.setShowFormal(false)}>候选 · {candidate?.status === "previewed" ? "已预览" : "待预览"}</button></div><span className="stage-mode">{p.scene.scene_manifest.scene_key ?? "generic"}</span><button className="ghost" aria-pressed={p.dialogueLines} onClick={p.onToggleDialogueLines} title="逐句显示：把长台词按句分段、按阅读速度逐段出现；整段显示则一次给完。可随时切换。">{p.dialogueLines ? "逐句显示" : "整段显示"} ⇄</button><button className="ghost" disabled={!!p.busy || !!p.artifactBusy} onClick={p.onGenerateArtifacts} title="用文生图生成场景背板与角色立绘；每张图的提示词、模型与生成时间都会记录。图只做视觉层，不改变剧情状态。">{p.artifactBusy || `生成美术素材${p.artifacts.length ? `（已有 ${p.artifacts.length} 件）` : ""}`}</button><span className="beat-chip" title={p.beat ? `这一段要解决：${p.beat.information_change ?? ""}｜完成信号：${p.beat.completion_signal ?? ""}｜分段来源：${p.scene.dramatic_source?.beats === "llm" ? "真实模型生成" : "内置模板（未调用模型）"}｜（剧情分段＝把一场戏分成 5 个阶段，每段解决一个戏剧问题；与分镜的"镜"无关）` : "尚无剧情分段"}>{p.beat ? `剧情第 ${p.beatIndex + 1} 段 / 共 ${p.beatTotal} 段 · ${p.beat.purpose}` : "尚无剧情分段"}</span><button className="ghost" disabled={!p.canAdvanceBeat} onClick={p.onAdvanceBeat} title="你确认这一段的任务已完成，进入下一段；系统不会自动推进。场次卡/剧本/分镜随时可以生成，不必等推进">进入下一段 →</button></div><WorldStage artifacts={p.artifacts} dialogueLines={p.dialogueLines} scene={p.scene} snapshot={p.display} events={p.replay.frame ? p.display.events : p.events} selectedActor={p.selectedActor} onActorSelect={p.onActor} activeEventId={p.selectedEvent} motion={p.replay.motion} /><ReplayControls replay={p.replay} onStart={p.onStop} disabled={p.busy && !p.replay.frame} /><div className="world-caption"><span className={candidate && !p.showFormal ? "candidate-dot" : "formal-dot"} />{p.replay.frame ? `只读回看 · 第 ${p.display.step} 步 · 历史 r${p.display.revision}` : candidate && !p.showFormal ? `候选投影 · 基于正式 r${candidate.base_revision}，尚未提交` : `正式世界 · 第 ${p.formal.step} 步`}</div><div className={`run-controls ${p.replay.frame ? "replay-hidden" : ""}`}><button className="primary" disabled={p.busy || !!candidate || p.continuous || p.runPhase === "cancelling"} onClick={p.onStep}>▷ 推进一步</button><button className="secondary" disabled={p.busy || !!candidate || p.continuous || p.runPhase === "cancelling"} onClick={p.onStartSlow}>慢速逐轮</button>{(p.continuous || p.runPhase === "generating" || p.runPhase === "cancelling") && <button className="stop-control" disabled={p.runPhase === "cancelling"} onClick={p.onStop}>{p.runPhase === "cancelling" ? "正在取消…" : p.runPhase === "generating" ? "取消本轮 / 停止" : "停止逐轮"}</button>}<span className="hint">始终手动预览、手动提交</span>{candidate && <><button className="ghost" disabled={p.busy} onClick={p.onDiscard}>丢弃候选</button><button className="secondary" disabled={p.busy} onClick={p.onPreview}>预览与检查</button><button className="primary" disabled={p.busy || p.dirty || candidate.status !== "previewed"} onClick={p.onCommit}>提交剧情 ✓</button></>}</div><div className={`run-status run-status-${p.runPhase} ${p.replay.frame ? "replay-hidden" : ""}`} role="status" aria-live="polite">{p.runPhase === "generating" ? "正在生成一轮候选，可随时取消。" : p.runPhase === "cancelling" ? "已停止本地推进，正在确认后端取消；迟到结果不会进入剧情。" : p.runPhase === "scheduled" ? "本轮已提交 · 2 秒后自动生成下一轮候选。" : candidate ? p.continuous ? "慢速逐轮 · 已暂停待审；手动预览并提交后，延时 2 秒再生成。" : "候选待审 · 你决定是否预览与提交。" : "单步模式 · 点击推进生成候选。"}</div><div className="timeline-panel"><div className="section-label">剧情时间线 <span>{p.formal.events.length} 正式 / {candidate?.candidate_events.length ?? 0} 候选</span></div><div className="event-strip">{p.events.length ? p.events.map((event) => <button className={`event-card ${p.formal.events.some((x) => x.id === event.id) ? "committed" : "candidate"} ${p.selectedEvent === event.id ? "selected" : ""}`} key={event.id} onClick={() => p.onEvent(event.id)}><span>第 {event.step} 步 · {p.formal.events.some((x) => x.id === event.id) ? "正式" : "候选"}{(() => { const index = (p.scene.beats ?? []).findIndex((beat) => beat.beat_id === event.beat_id); return index >= 0 ? ` · 第${index + 1}段` : ""; })()}</span><strong>{eventActorName(event, p.scene, p.formal)}</strong><b>{event.action}</b>{event.dialogue && <small>“{event.dialogue}”</small>}</button>) : <div className="empty-line">角色已就位。推进第一步，看看这场戏会如何开始。</div>}</div></div>{candidate && <div className="draft-editor"><div className="form-section-head"><div><h3>编辑候选动作与对白</h3><p className="hint">锁定字段必须先解锁；保存后必须重新预览。</p></div><button className="secondary" disabled={p.busy || !p.dirty} onClick={p.onSave}>保存候选编辑 *</button></div>{p.candidateEvents.map((event) => <article className="candidate-edit" key={event.id}><div className="candidate-title"><b>{eventActorName(event, p.scene, p.formal)}</b><span className="tag">候选 · 第 {event.step} 步</span></div>{(["action", "dialogue"] as const).map((field) => { const path = `events.${event.id}.${field}`; const isLocked = locked(event, field); return <label key={field}><span className="field-label">{field === "action" ? "动作" : "对白"}<button className="lock-control" type="button" disabled={p.busy} onClick={() => p.onToggleLock(path, isLocked)}>{isLocked ? "已锁定（需后端解锁）" : "字段可编辑"}</button></span><textarea rows={2} disabled={isLocked || p.busy} value={String(event[field] ?? "")} onChange={(e) => change(event.id, field, e.target.value)} /></label>; })}<label>移动到<select value={event.move_to ?? event.location ?? ""} disabled={p.busy} onChange={(e) => change(event.id, "move_to", e.target.value)}><option value="">原地</option>{p.formal.locations.map((location) => <option key={location}>{location}</option>)}</select></label><label>行动对象<select value={event.target_id ?? ""} disabled={p.busy} onChange={(e) => change(event.id, "target_id", e.target.value || null)}><option value="">无特定对象</option>{p.scene.actors.filter((actor) => actor.id !== event.actor_id).map((actor) => <option value={actor.id} key={actor.id}>{actor.name}</option>)}</select></label><label>转交道具<select value={event.transfer?.item_id ?? ""} disabled={p.busy} onChange={(e) => change(event.id, "transfer", e.target.value ? { item_id: e.target.value, to_actor_id: event.transfer?.to_actor_id ?? "" } : undefined)}><option value="">不转交</option>{Object.values(p.formal.items).filter((item) => item.holder === event.actor_id).map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>{event.transfer && <label>接收人<select value={event.transfer.to_actor_id} disabled={p.busy} onChange={(e) => change(event.id, "transfer", { ...event.transfer, to_actor_id: e.target.value })}><option value="">选择角色</option>{p.scene.actors.filter((actor) => actor.id !== event.actor_id).map((actor) => <option value={actor.id} key={actor.id}>{actor.name}</option>)}</select></label>}</article>)}</div>}</>;
}

function Inspector(p: { scene: SceneSpec; snapshot: WorldSnapshot; formal: WorldSnapshot; selected?: SceneEvent; selectedActor: string | null; branchId: string; activeDraft: SceneDraft | null; busy: boolean; professional: boolean; onError: (reason: unknown) => void }) {
  const [tab, setTab] = useState<"facts" | "directives">("facts"); const [text, setText] = useState(""); const [target, setTarget] = useState(""); const [context, setContext] = useState<unknown>(null);
  async function add() { if (!text.trim()) return; try { await api.addDirective(p.scene.scene_id, p.branchId, text.trim(), target || null, p.formal.step + 1); setText(""); window.location.reload(); } catch (reason) { p.onError(reason); } }
  async function cancel(id: string) { try { await api.cancelDirective(p.scene.scene_id, p.branchId, id); window.location.reload(); } catch (reason) { p.onError(reason); } }
  return <aside className="inspector"><div className="inspector-tabs"><button className={tab === "facts" ? "active" : ""} onClick={() => setTab("facts")}>世界与信息差</button><button className={tab === "directives" ? "active" : ""} onClick={() => setTab("directives")}>导演干预</button></div><div className="inspector-block segment-list"><div className="section-label">剧情分段 · 进度 <span className="hint">已完成 {(p.formal.beat_state?.completed_beats ?? []).length} / {(p.scene.beats ?? []).length || 5}</span></div>{((p.scene.beats ?? []).length ? p.scene.beats! : []).map((beat, index) => { const completed = (p.formal.beat_state?.completed_beats ?? []).includes(beat.beat_id); const current = index === (p.formal.beat_state?.index ?? 0) && !completed; return <div className={`segment-row ${completed ? "done" : current ? "current" : "todo"}`} key={beat.beat_id}><b>第 {index + 1} 段</b><span>{completed ? "已完成" : current ? "进行中" : "未开始"}</span><small>{beat.purpose}｜要解决：{beat.information_change ?? ""}</small></div>; })}{!(p.scene.beats ?? []).length && <p className="hint">这个场景建立时还没有剧情分段；推进一次后会按内置模板补上 5 段。</p>}</div>{p.activeDraft?.assessment && <div className="inspector-block drama-check"><div className="section-label">剧情检查（规则判断，不调模型）· 剧情第 {(p.activeDraft.assessment.beat_index ?? 0) + 1} 段 / 共 {p.activeDraft.assessment.beat_total ?? 5} 段 {p.activeDraft.assessment.beat?.purpose ?? ""}</div><div className="drama-score">{p.activeDraft.assessment.passed ?? 0} / {p.activeDraft.assessment.total ?? 0} 通过 · 张力 {p.activeDraft.assessment.tension ?? 0}</div>{(p.activeDraft.assessment.checks ?? []).map((check) => <div className={`drama-row ${check.status === "通过" ? "pass" : check.status === "偏弱" ? "weak" : "none"}`} key={check.item}><b>{check.item}</b><span>{check.status}</span><small>{check.detail}</small></div>)}{p.activeDraft.assessment.suggestion && <p className="hint">建议：{p.activeDraft.assessment.suggestion}</p>}</div>}{tab === "facts" ? <><div className="inspector-block"><div className="section-label">当前事件</div>{p.selected ? <><b className="inspector-name">{eventActorName(p.selected, p.scene, p.formal)}</b><p>{p.selected.action}</p>{p.selected.dialogue && <blockquote>{p.selected.dialogue}</blockquote>}<code className="source-id">{p.selected.id}</code></> : <p className="hint">还没有发生事件</p>}</div><div className="inspector-block"><div className="section-label">事实透镜 <span>{p.activeDraft ? "候选" : "正式"}</span></div>{p.snapshot.facts.length ? p.snapshot.facts.map((fact) => <FactRow key={fact.id} fact={fact} scene={p.scene} />) : <p className="hint">尚未设置事实</p>}</div><div className="inspector-block"><div className="section-label">道具归属</div>{Object.values(p.snapshot.items).map((item) => <div className="item-line" key={item.id}><b>{String(item.name)}</b><span>{String(item.holder ? p.snapshot.actors[item.holder]?.name ?? item.holder : item.location ?? "公共场景")}</span></div>)}</div>{p.professional && <div className="inspector-block"><div className="section-label">角色视角</div><button className="secondary full" disabled={!p.selectedActor || p.busy} onClick={async () => { try { if (p.selectedActor) setContext(await api.getContext(p.scene.scene_id, p.selectedActor, p.branchId)); } catch (reason) { p.onError(reason); } }}>读取角色所知信息</button>{!!context && <pre className="context-json">{String(JSON.stringify(context, null, 2))}</pre>}</div>}</> : <><div className="inspector-block"><div className="section-label">下一轮导演指令</div><label>作用对象<select value={target} onChange={(e) => setTarget(e.target.value)}><option value="">全场角色</option>{p.scene.actors.map((actor) => <option key={actor.id} value={actor.id}>{actor.name}</option>)}</select></label><label>告诉角色如何行动<textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="例如：先确认对方是否看见第三个名字" /></label><button className="primary full" disabled={p.busy || !!p.activeDraft || !text.trim()} onClick={add}>加入下一轮</button>{p.activeDraft && <p className="hint">本轮候选已生成，请提交或丢弃后再添加。</p>}</div><div className="inspector-block"><div className="section-label">指令记录</div>{p.formal.directives.length ? p.formal.directives.map((directive) => <article className="directive" key={directive.id}><span className="tag">{directive.status === "applied" ? "已应用" : "待执行"}</span><b>{String(directive.target_actor_id ? p.formal.actors[directive.target_actor_id]?.name ?? directive.target_actor_id : "全场")}</b><p>{directive.text}</p>{directive.status !== "applied" && <button className="danger-link" disabled={!!p.activeDraft || p.busy} onClick={() => cancel(directive.id)}>取消指令</button>}</article>) : <p className="hint">暂无导演指令</p>}</div></>}</aside>;
}

function FactRow({ fact, scene }: { fact: FactState; scene: SceneSpec }) { const known = fact.known_by ?? []; return <div className="fact-row"><span className={`fact-marker ${known.length ? "actor" : "author"}`} /><div><b>{fact.label}</b>{(fact.value || fact.text) && <p>{fact.value ?? fact.text}</p>}<small>{known.length ? known.map((id) => scene.actors.find((actor) => actor.id === id)?.name ?? id).join("、") : "仅导演知道"}</small></div></div>; }

function BranchView({ record, snapshot, activeDraft, busy, onSwitch, onFork }: { record: SceneRecord; snapshot: WorldSnapshot; activeDraft: boolean; busy: boolean; onSwitch: (id: string) => void; onFork: (name: string) => Promise<void> }) {
  const [name, setName] = useState(""); const [compare, setCompare] = useState<string[]>([]); const [states, setStates] = useState<WorldSnapshot[]>([]); const [error, setError] = useState("");
  async function compareBranches() { try { setStates(await Promise.all(compare.map((id) => api.getState(record.scene_id, id)))); } catch (reason) { setError(message(reason)); } }
  return <div className="content-view"><span className="eyebrow">真实正式状态</span><h2>分支试演</h2><p className="hint">分支从完整正式状态复制；候选草稿不会自动带入其他分支。</p><div className="create-branch"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="新分支名称" /><button className="primary" disabled={busy || activeDraft} onClick={() => onFork(name.trim() || `试演 ${record.branches.length}`)}>＋ 创建分支</button></div>{activeDraft && <p className="inline-note">提交或丢弃当前候选后再切换分支。</p>}<div className="branch-cards">{record.branches.map((branch: Branch) => <div className={`branch-card ${snapshot.branch_id === branch.branch_id ? "current" : ""}`} key={branch.branch_id}><input type="checkbox" checked={compare.includes(branch.branch_id)} disabled={!compare.includes(branch.branch_id) && compare.length >= 2} onChange={(e) => setCompare(e.target.checked ? [...compare, branch.branch_id] : compare.filter((id) => id !== branch.branch_id))} /><div><b>{branch.name}</b><small>{branch.parent_branch_id ? `来自 ${branch.parent_branch_id}` : "原始主线"}</small></div>{snapshot.branch_id === branch.branch_id ? <span className="branch-state">当前分支</span> : <button className="secondary" disabled={busy || activeDraft} onClick={() => onSwitch(branch.branch_id)}>切换</button>}</div>)}</div><button className="secondary" disabled={compare.length !== 2} onClick={compareBranches}>比较选中的两个分支</button>{error && <p className="alert error">{error}</p>}{states.length === 2 && <div className="compare-grid">{states.map((state) => <article key={state.branch_id}><h3>{record.branches.find((b) => b.branch_id === state.branch_id)?.name}</h3><p>正式 r{state.revision} · {state.events.length} 个事件</p>{actorsList(state).map((actor) => <div className="compare-line" key={actor.id}>{actor.name}<span>{actor.location}</span></div>)}<h4>最近事件</h4>{state.events.slice(-4).map((event) => <p className="hint" key={event.id}>{eventActorName(event, record.scene_spec, state)}：{event.action}</p>)}</article>)}</div>}</div>;
}

function OutputView({ scene, snapshot, outputs, setOutputs, busy }: { scene: SceneSpec; snapshot: WorldSnapshot; outputs: SceneOutput[]; setOutputs: (outputs: SceneOutput[]) => void; busy: boolean }) {
  const [type, setType] = useState<OutputType>("screenplay"); const [chosen, setChosen] = useState<string[]>(() => snapshot.events.map((event) => event.id)); const [edits, setEdits] = useState<Record<string, string>>({}); const events = snapshot.events;
  async function generate(polish = false) { try { const ids = chosen.length ? chosen : snapshot.events.map((event) => event.id); const output = await api.createOutput(scene.scene_id, snapshot.branch_id, type, ids, snapshot.revision, polish); setOutputs([...outputs, output]); if (polish) { const note = (output as unknown as { polished?: boolean; polish_reason?: string }); alert(note.polished ? "已用真实模型润色，来源标记全部保留。" : "润色未生效，已保留可复现草稿：".concat(note.polish_reason ?? "未说明原因")); } } catch (reason) { alert(message(reason)); } }
  async function save(output: SceneOutput, text: string) { try { const next = await api.saveOutput(output, text); setOutputs(outputs.map((item) => item.output_id === output.output_id ? next : item)); } catch (reason) { alert(message(reason)); } }
  function download(output: SceneOutput, text: string) { const url = URL.createObjectURL(new Blob([`${text}\n\n来源事件：${output.source_event_ids.join(", ")}\n版本：${output.revision}`], { type: "text/plain;charset=utf-8" })); const a = document.createElement("a"); a.href = url; a.download = `${scene.title}-${outputNames[output.type]}.txt`; a.click(); URL.revokeObjectURL(url); }
  const current = outputs.filter((output) => output.branch_id === snapshot.branch_id);
  return <div className="content-view"><span className="eyebrow">来源可追溯</span><h2>剧本与分镜草稿</h2><p className="hint">选择已提交事件后生成三种可编辑输出。保存由后端确认，下载包含来源事件。</p><div className="output-source"><details className="output-source-picker"><summary><b>选择来源事件</b><span>已选 {chosen.length} / {events.length}</span></summary><div className="output-source-tools"><span className="hint">只使用当前分支的正式事件</span><button className="text-button" onClick={() => setChosen(chosen.length === events.length ? [] : events.map((e) => e.id))}>全选 / 取消</button></div><div className="output-event-list">{events.map((event) => <label className="output-event" key={event.id}><input type="checkbox" checked={chosen.includes(event.id)} onChange={(e) => setChosen(e.target.checked ? [...chosen, event.id] : chosen.filter((id) => id !== event.id))} /><span>第 {event.step} 步 · {eventActorName(event, scene, snapshot)}：{event.action}<code>{event.id}</code></span></label>)}</div>{!events.length && <p className="hint">先在剧情沙盘中提交事件，再回来整理输出。</p>}</details><div className="output-actions"><select aria-label="输出类型" value={type} onChange={(e) => setType(e.target.value as OutputType)}>{Object.entries(outputNames).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select><button className="primary" disabled={busy || !events.length} onClick={() => generate()} title={events.length ? "用选中的正式事件生成输出；未勾选时默认全部" : "还没有正式事件，请先在舞台提交至少一轮"}>生成 {outputNames[type]}</button><button className="secondary" disabled={busy || !events.length} onClick={() => generate(true)} title="作者显式触发：用真实模型把场记草稿润色成剧本；来源标记必须全部保留，否则退回可复现草稿">润色剧本（真模型）</button></div></div><div className="output-grid">{current.map((output) => { const id = output.output_id ?? `${output.type}-${output.revision}`; const text = edits[id] ?? outputText(output.content); return <article className="output-card" key={id}><div className="output-title"><b>{outputNames[output.type]}</b><span>r{output.revision} · {output.source_event_ids.length} 来源</span></div><p className="hint">生成方式：{output.polished ? "真实模型润色（来源标记已校验）" : output.source === "deterministic_screenplay" || output.source === "deterministic_storyboard" ? "确定性渲染 · 未调用模型（可复现）" : output.source === "polished_screenplay" ? "真实模型润色" : "未标注"}</p><textarea aria-label={`${outputNames[output.type]}内容`} rows={12} value={text} onChange={(e) => setEdits({ ...edits, [id]: e.target.value })} /><details><summary>来源事件</summary>{output.source_event_ids.map((eventId) => <code className="source-id" key={eventId}>{eventId}</code>)}</details><div className="output-actions"><button className="secondary" onClick={() => download(output, text)}>下载</button><button className="primary" disabled={busy || text === outputText(output.content)} onClick={() => save(output, text)}>保存修改</button></div></article>; })}</div></div>;
}

function SceneSetup({ initial, onSave, onCancel, busy, submitLabel, existing = false }: { initial: SceneSpec; onSave: (spec: SceneSpec) => void; onCancel: () => void; busy: boolean; submitLabel: string; existing?: boolean }) {
  const [value, setValue] = useState<SceneSpec>(() => copy(initial));
  const set = <K extends keyof SceneSpec>(key: K, next: SceneSpec[K]) => setValue((current) => ({ ...current, [key]: next }));
  const setActor = (index: number, field: keyof ActorSpec, next: string) => set("actors", value.actors.map((actor, i) => i === index ? { ...actor, [field]: next } : actor));
  const valid = value.title.trim() && value.location.trim() && value.conflict.trim() && value.actors.length >= 2 && value.actors.every((actor) => actor.name.trim() && actor.goal?.trim());
  function submit() { const actors = value.actors.map((actor) => ({ ...actor, location: actor.location || value.location })); onSave({ ...value, actors, characters: actors, locations: [...new Set([value.location, ...value.locations.filter(Boolean), ...actors.map((actor) => actor.location ?? value.location)])] }); }
  return <div className="setup-form"><div className="setup-grid"><label>场次名称<input value={value.title} onChange={(e) => set("title", e.target.value)} /></label><label>类型<input value={value.genre} onChange={(e) => set("genre", e.target.value)} /></label><label>主要地点<input value={value.location} onChange={(e) => set("location", e.target.value)} /></label><label>场景样式<select value={value.scene_manifest.scene_key ?? "generic"} onChange={(e) => set("scene_manifest", { ...value.scene_manifest, scene_key: e.target.value })}>{sceneManifestOptions.map(option => <option key={option.key} value={option.key}>{option.label}</option>)}</select></label><label className="wide">核心冲突<textarea rows={2} value={value.conflict} onChange={(e) => set("conflict", e.target.value)} /></label><label className="wide">其他可移动区域（每行一个）<textarea rows={2} value={value.locations.filter((item) => item !== value.location).join("\n")} onChange={(e) => set("locations", e.target.value.split("\n").filter(Boolean))} /></label></div><div className="form-section-head"><h3>角色、目标与秘密</h3>{!existing && <button className="secondary" onClick={() => set("actors", [...value.actors, { id: `actor_${Date.now()}`, name: "", role: "", goal: "", secret: "", location: value.location }])}>＋ 添加角色</button>}</div><div className="actor-setup-grid">{value.actors.map((actor, index) => <article className="actor-setup" key={actor.id}><div className="actor-form-head"><span>角色 {index + 1}</span>{!existing && <button className="danger-link" onClick={() => set("actors", value.actors.filter((item) => item.id !== actor.id))}>移除</button>}</div><label>名字<input value={actor.name} onChange={(e) => setActor(index, "name", e.target.value)} /></label><label>身份<input value={actor.role} onChange={(e) => setActor(index, "role", e.target.value)} /></label><label>这一场想得到什么<input value={actor.goal ?? ""} onChange={(e) => setActor(index, "goal", e.target.value)} /></label><label>只让这个角色知道的秘密<textarea rows={2} value={actor.secret ?? ""} onChange={(e) => setActor(index, "secret", e.target.value)} /></label><label>初始位置<input value={actor.location ?? value.location} onChange={(e) => setActor(index, "location", e.target.value)} /></label></article>)}</div><div className="setup-grid"><label>人物关系（每行一条）<textarea rows={3} value={value.relationships.join("\n")} onChange={(e) => set("relationships", e.target.value.split("\n").filter(Boolean))} /></label><label>导演事实（每行一条）<textarea rows={3} value={value.author_facts.join("\n")} onChange={(e) => set("author_facts", e.target.value.split("\n").filter(Boolean))} /></label></div><div className="form-section-head"><h3>共享道具</h3><button className="text-button" onClick={() => set("items", [...value.items, { id: `item_${Date.now()}`, name: "", holder: null, location: value.location }])}>＋ 添加道具</button></div>{value.items.map((item, index) => <div className="item-editor" key={item.id}><input aria-label={`道具 ${index + 1}`} value={item.name} onChange={(e) => set("items", value.items.map((entry, i) => i === index ? { ...entry, name: e.target.value } : entry))} /><select value={item.holder ?? ""} onChange={(e) => set("items", value.items.map((entry, i) => i === index ? { ...entry, holder: e.target.value || null } : entry))}><option value="">在场景中</option>{value.actors.map((actor) => <option key={actor.id} value={actor.id}>{actor.name || actor.id}</option>)}</select><button className="danger-link" onClick={() => set("items", value.items.filter((entry) => entry.id !== item.id))}>移除</button></div>)}<div className="form-section-head"><h3>共享事实与知晓范围</h3><button className="text-button" onClick={() => set("facts", [...value.facts, { id: `fact_${Date.now()}`, label: "", known_by: [], source: "导演设定" }])}>＋ 添加事实</button></div>{value.facts.map((fact, index) => <div className="fact-editor" key={fact.id}><input aria-label={`事实 ${index + 1}`} value={fact.label} onChange={(e) => set("facts", value.facts.map((entry, i) => i === index ? { ...entry, label: e.target.value } : entry))} /><span className="knowers">谁知道：{value.actors.map((actor) => <label key={actor.id}><input type="checkbox" checked={fact.known_by?.includes(actor.id) ?? false} onChange={(e) => set("facts", value.facts.map((entry, i) => i === index ? { ...entry, known_by: e.target.checked ? [...(entry.known_by ?? []), actor.id] : (entry.known_by ?? []).filter((id) => id !== actor.id) } : entry))} />{actor.name || actor.id}</label>)}</span><button className="danger-link" onClick={() => set("facts", value.facts.filter((entry) => entry.id !== fact.id))}>移除</button></div>)}<div className="form-footer"><span className="hint">至少两名角色；每名角色需要名字和目标。</span><button className="ghost" disabled={busy} onClick={onCancel}>返回</button><button className="primary" disabled={busy || !valid} onClick={submit}>{busy ? "处理中…" : submitLabel}</button></div></div>;
}

