import type { ReplayController } from './useReplay';
export function ReplayControls({ replay, onStart, disabled }: { replay: ReplayController; onStart: () => void; disabled: boolean }) {
  return <section className="replay-controls" aria-label="剧情回放">
    <div className="replay-actions"><b>剧情回放</b><button className="secondary" disabled={disabled || replay.loading} onClick={() => { onStart(); replay.toggle(); }}>{replay.loading ? '读取历史…' : replay.playing ? '暂停回放' : replay.frame ? '继续播放' : '播放已确认剧情'}</button>
      <button className="ghost" disabled={disabled || replay.loading} onClick={() => { onStart(); void replay.open(false); }}>回到开场</button>
      {replay.frame && <><button className="ghost" disabled={replay.cursor === 0} onClick={() => replay.jump((replay.cursor ?? 0) - 1)}>上一刻</button><button className="ghost" disabled={replay.cursor === (replay.history?.frames.length ?? 0) - 1} onClick={() => replay.jump((replay.cursor ?? 0) + 1)}>下一刻</button><button className="text-button" onClick={replay.exit}>返回创作</button></>}
      <select aria-label="回放速度" value={replay.speed} onChange={e => replay.setSpeed(Number(e.target.value))}><option value={.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option></select></div>
    {replay.frame && <label className="replay-seek">开场<input aria-label="回放进度" type="range" min={0} max={(replay.history?.frames.length ?? 1) - 1} value={replay.cursor ?? 0} onChange={e => replay.jump(Number(e.target.value))} /><span>第 {replay.frame.state.step} 步 · r{replay.frame.revision}</span></label>}
    <small>只读回看 · 不调用模型 · 不提交剧情{replay.frame ? ' · 拖动进度可定位，播放时角色行走' : ''}</small>{replay.error && <p role="alert" className="hint">{replay.error}</p>}
  </section>;
}
