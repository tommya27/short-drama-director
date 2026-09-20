import { Component, Suspense, lazy, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { WorldStageProps } from './types';
import { actorPositions, layoutFor } from './stage-manifest';
import { assetSrc } from './api';
import './stage.css';
const Stage3D = lazy(() => import('./Stage3D'));
/** 美术素材只做视觉层：背板铺底、立绘替换占位形象；几何与走位仍由 scene manifest 决定。 */
function backdropOf(props: WorldStageProps) { return props.artifacts?.find(item => item.kind === 'backdrop'); }
function portraitOf(props: WorldStageProps, actorId: string) { return props.artifacts?.find(item => item.kind === 'portrait' && item.actor_id === actorId); }
function supportsWebGL() {
 try {
  const canvas=document.createElement('canvas');
  const context=canvas.getContext('webgl2') ?? canvas.getContext('webgl');
  if (!context) return false;
  context.getExtension('WEBGL_lose_context')?.loseContext();
  return true;
 } catch { return false; }
}
class StageBoundary extends Component<{children:ReactNode; fallback:ReactNode}, {failed:boolean}> {
 state = {failed:false};
 static getDerivedStateFromError() { return {failed:true}; }
 render() { return this.state.failed ? this.props.fallback : this.props.children; }
}
function MapStage(props: WorldStageProps) {
 const layout = layoutFor(props.scene,props.snapshot);
 const positions = actorPositions(props.snapshot,layout);
 const backdrop = backdropOf(props);
 return <div className="world-map" role="img" aria-label={`${props.scene.location} 2.5D 状态地图`} style={backdrop ? {backgroundImage:`linear-gradient(#ffffffb8,#ffffffb8), url(${assetSrc(backdrop.url)})`, backgroundSize:'cover', backgroundPosition:'center'} : undefined}>
  {layout.zones.map(zone=><div className="map-zone" key={zone}><span>{zone}</span>
   {Object.values(props.snapshot.actors).filter(a=>(a.location ?? layout.zones[0])===zone).map(a=><button key={a.id} className={`map-person ${props.selectedActor===a.id?'chosen':''}`} onClick={()=>props.onActorSelect(a.id)}>
    {portraitOf(props,a.id) ? <img className="map-portrait" src={assetSrc(portraitOf(props,a.id)!.url)} alt={`${a.name} 立绘`} title={`立绘：${portraitOf(props,a.id)!.model} · ${portraitOf(props,a.id)!.created_at}`}/> : <i style={{background:a.color??layout.accent}}>●</i>}<b>{a.name}</b><small>{props.events.filter(e=>e.actor_id===a.id).at(-1)?.action??'尚未行动'}</small>
   </button>)}
  </div>)}
  <div className="map-items">{Object.values(props.snapshot.items??{}).map(i=><span key={i.id}>▤ {i.name} · {i.holder?props.snapshot.actors[i.holder]?.name:i.location??'场内'}</span>)}</div>
  <span className="stage-footnote">{Object.keys(positions).length} 位角色 · 点击查看其所见与目标</span>
 </div>;
}
/** 可拖动、可缩放的对白窗：位置与尺寸写入 localStorage，带重置。 */
type CaptionBox = { x: number; y: number; w: number; h: number };
const CAPTION_KEY = 'director-caption-box';
const CAPTION_DEFAULT: CaptionBox = { x: -1, y: -1, w: 430, h: 0 };

function FloatingCaption({ label, name, text, expanded, onToggle }: { label: string; name: string; text: string; expanded: boolean; onToggle: () => void }) {
 const ref = useRef<HTMLElement>(null);
 const boxRef = useRef<CaptionBox>(CAPTION_DEFAULT);
 const [box, setBox] = useState<CaptionBox>(() => {
  try { return { ...CAPTION_DEFAULT, ...JSON.parse(localStorage.getItem(CAPTION_KEY) ?? '{}') } as CaptionBox; }
  catch { return CAPTION_DEFAULT; }
 });
 boxRef.current = box;
 const save = (next: CaptionBox) => { setBox(next); try { localStorage.setItem(CAPTION_KEY, JSON.stringify(next)); } catch { /* 隐私模式忽略 */ } };
 const onPointerDown = (event: React.PointerEvent) => {
  if ((event.target as HTMLElement).closest('button')) return;
  const section = ref.current; const host = section?.parentElement;
  if (!section || !host) return;
  const rect = section.getBoundingClientRect();
  const grabX = event.clientX - rect.left; const grabY = event.clientY - rect.top;
  const move = (moveEvent: PointerEvent) => {
   const element = ref.current; const bounds = element?.parentElement?.getBoundingClientRect();
   if (!element || !bounds) return;
   const maxX = Math.max(4, bounds.width - element.offsetWidth - 4);
   const maxY = Math.max(4, bounds.height - element.offsetHeight - 4);
   save({
    ...boxRef.current,
    x: Math.round(Math.min(Math.max(4, moveEvent.clientX - bounds.left - grabX), maxX)),
    y: Math.round(Math.min(Math.max(4, moveEvent.clientY - bounds.top - grabY), maxY)),
   });
  };
  const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); };
  window.addEventListener('pointermove', move);
  window.addEventListener('pointerup', up);
  event.preventDefault();
 };
 useEffect(() => {
  const element = ref.current; if (!element) return;
  const observer = new ResizeObserver(() => {
   const w = Math.round(element.offsetWidth); const h = Math.round(element.offsetHeight);
   if (w !== boxRef.current.w || h !== boxRef.current.h) save({ ...boxRef.current, w, h });
  });
  observer.observe(element);
  return () => observer.disconnect();
 }, []);
 const docked = box.x < 0 || box.y < 0;
 const style = docked ? { width: box.w, height: box.h > 0 ? box.h : undefined } : { left: box.x, top: box.y, width: box.w, height: box.h > 0 ? box.h : undefined };
 return <section ref={ref} className={`stage-event-caption ${docked ? 'docked' : 'floating'} ${expanded ? 'expanded' : ''}`} style={style} aria-label="当前角色事件">
  <div className="stage-event-caption-heading" onPointerDown={onPointerDown} title="按住这里拖动窗口；右下角可缩放">
   <span className="caption-grip" aria-hidden="true">⣿</span>
   <span>{label}</span><b>{name}</b>
   <button onClick={onToggle} aria-expanded={expanded}>{expanded ? '收起' : '展开'}</button>
   {!docked && <button onClick={() => save(CAPTION_DEFAULT)} title="恢复到底部居中">重置</button>}
  </div>
  <p>{text}</p>
 </section>;
}

export function WorldStage(props: WorldStageProps) {
 const [mode,setMode]=useState<'3d'|'map'>('3d');
 const [preset,setPreset]=useState('wide');
 const [failed,setFailed]=useState(()=>!supportsWebGL());
 const [showObservers,setShowObservers]=useState(false);
 const [showLabels,setShowLabels]=useState(false);
 const [captionExpanded,setCaptionExpanded]=useState(false);
 const [showBubbles,setShowBubbles]=useState(()=>localStorage.getItem('director-speech-bubbles')!=='off');
 const layout=useMemo(()=>layoutFor(props.scene,props.snapshot),[props.scene,props.snapshot]);
 const selectedEvent=props.events.find(event=>event.id===props.activeEventId&&event.actor_id===props.selectedActor)??props.events.filter(event=>event.actor_id===props.selectedActor).at(-1);
 const selectedName=props.snapshot.actors[props.selectedActor??'']?.name;
 const showing3D=mode==='3d'&&layout.renderer!=='map'&&layout.renderer!=='2.5d'&&!failed;
 useEffect(()=>setCaptionExpanded(false),[selectedEvent?.id]);
 useEffect(()=>{ if (!layout.cameras.some(camera=>camera.id===preset)) setPreset(layout.cameras[0].id); },[layout.cameras,preset]);
 const fallback=<div className="stage-fallback"><p>当前设备的 3D 不可用，已显示可操作的状态地图。</p><MapStage {...props}/></div>;
 return <section className="world-stage">
  <div className="world-stage-bar"><div><span className="stage-green-dot"/> {layout.name}<small> · 世界状态显现</small></div>
   <div className="world-stage-actions"><button className={showObservers?'chosen':''} aria-pressed={showObservers} onClick={()=>setShowObservers(!showObservers)}>观察关系</button>{showing3D&&<><button className={showLabels?'chosen':''} aria-pressed={showLabels} title="拥挤时优先保留选中对象，其他名称可在侧栏查看" onClick={()=>setShowLabels(!showLabels)}>{showLabels?'收起全部标注':'显示全部标注'}</button><button className={showBubbles?'chosen':''} aria-pressed={showBubbles} title="说话气泡：只显示当前说话角色的台词，可随时关闭" onClick={()=>setShowBubbles((old)=>{localStorage.setItem('director-speech-bubbles', old?'off':'on'); return !old;})}>{showBubbles?'气泡开':'气泡关'}</button></>}<select aria-label="舞台镜头" value={preset} onChange={e=>setPreset(e.target.value)}>{layout.cameras.map(camera=><option key={camera.id} value={camera.id}>{camera.label}</option>)}</select><button onClick={()=>setMode(mode==='3d'?'map':'3d')}>{mode==='3d'?'切换 2.5D':'切换 3D'}</button></div>
  </div>
  <div className="world-canvas">
  {mode==='map'||layout.renderer==='map'||layout.renderer==='2.5d'?<MapStage {...props}/>:failed?fallback:<StageBoundary fallback={fallback}><Suspense fallback={<div className="stage-loading">正在搭建 3D 舞台…</div>}><Stage3D {...props} showBubbles={showBubbles} preset={preset} showObservers={showObservers} showLabels={showLabels} onFailure={()=>setFailed(true)}/></Suspense></StageBoundary>}
  {showing3D&&selectedEvent&&<FloatingCaption label={selectedEvent.committed_change?'已确认事件':'候选动作'} name={selectedName??''} text={selectedEvent.dialogue||selectedEvent.action} expanded={captionExpanded} onToggle={()=>setCaptionExpanded(!captionExpanded)}/>}
  </div>
  {props.artifacts?.length ? <div className="stage-artifacts" aria-label="美术素材与来源">{props.artifacts.map(item=><figure key={item.asset_id} title={`${item.label}｜提示词：${item.prompt}\n模型：${item.model}\n生成时间：${item.created_at}`}><img src={assetSrc(item.url)} alt={item.label}/><figcaption>{item.label}</figcaption></figure>)}</div> : null}
  <div className="world-stage-note"><span>拖动旋转 · 滚轮缩放 · 点击角色</span><span>{props.artifacts?.length?`美术素材 ${props.artifacts.length} 件 · 文生图（悬停可看提示词与模型）`:'尚未生成美术素材'}</span><span>候选动作仅供试演，确认后才写入剧情</span></div>
 </section>;
}
export default WorldStage;
