import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import { actorPositions, layoutFor } from './stage-manifest';
import { walkingSeconds } from './walking';
import type { ReplayFrame, ReplayHistory } from './types';

function duration(previous: ReplayFrame | undefined, frame: ReplayFrame) {
  if (!previous) return 1500;
  const from = actorPositions(previous.state, layoutFor(previous.scene_spec, previous.state));
  const to = actorPositions(frame.state, layoutFor(frame.scene_spec, frame.state));
  const seconds = Math.max(0, ...Object.keys(to).map(id => from[id] ? walkingSeconds(from[id], to[id]) : 0));
  const newEvents = frame.state.events.filter(e => !previous.state.events.some(old => old.id === e.id));
  const reading = Math.min(9, Math.max(4, newEvents.reduce((sum, e) => sum + (e.dialogue || e.action).length, 0) / 18));
  return Math.max(seconds + 1, reading) * 1000;
}

export function useReplay(sceneId: string, branchId: string, revision: number, view: string) {
  const key = `${sceneId}:${branchId}:${revision}:${view}`;
  const activeKey = useRef(key); activeKey.current = key;
  const epoch = useRef(0);
  const [history, setHistory] = useState<ReplayHistory | null>(null);
  const [cursor, setCursor] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [seek, setSeek] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [eventId, setEventId] = useState<string | null>(null);
  const remaining = useRef(0);
  const valid = history?.scene_id === sceneId && history.branch_id === branchId && history.revision === revision && view === 'stage';
  const frame = valid && cursor !== null ? history.frames[cursor] : undefined;
  useEffect(() => { epoch.current++; setHistory(null); setCursor(null); setPlaying(false); setLoading(false); setError(''); setEventId(null); remaining.current = 0; }, [key]);
  useEffect(() => () => { epoch.current++; }, []);
  useEffect(() => {
    if (!playing || !frame || cursor === null || !history) return;
    const time = remaining.current || duration(history.frames[cursor - 1], frame);
    remaining.current = time;
    const started = performance.now();
    const timer = setTimeout(() => {
      remaining.current = 0;
      if (cursor >= history.frames.length - 1) setPlaying(false);
      else { setCursor(cursor + 1); setEventId(null); }
    }, time / speed);
    return () => { clearTimeout(timer); if (remaining.current) remaining.current = Math.max(1, time - (performance.now() - started) * speed); };
  }, [playing, cursor, speed, history, frame]);
  function exit() { epoch.current++; setCursor(null); setPlaying(false); setLoading(false); setEventId(null); remaining.current = 0; setSeek(value => value + 1); }
  async function open(play: boolean, targetEvent?: string) {
    const token = ++epoch.current, requestKey = key;
    setLoading(true); setError('');
    try {
      const result = valid ? history! : await api.getReplay(sceneId, branchId, revision);
      if (epoch.current !== token || activeKey.current !== requestKey) return;
      if (!result.frames.length) throw new Error('这场戏还没有可回看的正式记录。');
      const index = targetEvent ? result.frames.findIndex(f => f.state.events.some(e => e.id === targetEvent)) : 0;
      if (index < 0) throw new Error('找不到该事件的历史快照。');
      setHistory(result); setCursor(index); setEventId(targetEvent ?? null); setPlaying(play); setSeek(value => value + 1); remaining.current = 0;
    } catch (reason) { if (epoch.current === token && activeKey.current === requestKey) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (epoch.current === token && activeKey.current === requestKey) setLoading(false); }
  }
  function jump(index: number) { if (!valid || !history) return; setPlaying(false); setCursor(Math.max(0, Math.min(history.frames.length - 1, index))); setEventId(null); remaining.current = 0; setSeek(value => value + 1); }
  function toggle() {
    if (!frame || !history || cursor === history.frames.length - 1 && !playing) { void open(true); return; }
    setPlaying(value => !value);
  }
  return { history: valid ? history : null, frame, cursor, playing, speed, setSpeed, loading, error, eventId, open, exit, jump, toggle, motion: { paused: !!frame && !playing, speed: frame ? speed : 1, seek } };
}
export type ReplayController = ReturnType<typeof useReplay>;
