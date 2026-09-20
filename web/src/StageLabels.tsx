import { Html } from '@react-three/drei';
import { useFrame, useThree } from '@react-three/fiber';
import { useRef } from 'react';
import { Vector3 } from 'three';
import type { Vec3 } from './stage-manifest';

export type StageLabel = { id: string; text: string; position: Vec3; objectName?: string; kind: 'actor' | 'item' | 'zone'; color?: string; priority: number; active?: boolean; onSelect?: () => void };
type Rect = { x: number; y: number; w: number; h: number };
const overlaps = (a: Rect, b: Rect) => a.x < b.x + b.w + 4 && a.x + a.w + 4 > b.x && a.y < b.y + b.h + 4 && a.y + a.h + 4 > b.y;

// Screen-space labels stay small when zooming. Try free slots around each
// object; hide a lower-priority label when none is clear of actors and text.
export function StageLabels({ labels, actorIds }: { labels: StageLabel[]; actorIds: string[] }) {
  const { size } = useThree();
  const elements = useRef<Record<string, HTMLButtonElement | null>>({});
  const lines = useRef<Record<string, SVGLineElement | null>>({});
  const point = useRef(new Vector3());
  useFrame(({ camera, scene }) => {
    const project = (x: number, y: number, z: number) => {
      const p = point.current.set(x, y, z).project(camera);
      return { x: (p.x + 1) * size.width / 2, y: (1 - p.y) * size.height / 2, z: p.z };
    };
    const bodies: Rect[] = actorIds.flatMap(id => {
      const object = scene.getObjectByName(`actor:${id}`);
      if (!object) return [];
      const p = object.position;
      const corners = [-.48, .48].flatMap(x => [0, 1.58].flatMap(y => [-.4, .4].map(z => project(p.x + x, p.y + y, p.z + z))));
      const xs = corners.map(v => v.x), ys = corners.map(v => v.y);
      return [{ x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) }];
    });
    const occupied = [...bodies];
    for (const label of [...labels].sort((a, b) => b.priority - a.priority)) {
      const element = elements.current[label.id], line = lines.current[label.id];
      if (!element || !line) continue;
      const object = label.objectName ? scene.getObjectByName(label.objectName) : undefined;
      const base = object?.position;
      const p = project((base?.x ?? 0) + label.position[0], (base?.y ?? 0) + label.position[1], (base?.z ?? 0) + label.position[2]);
      element.style.visibility = 'hidden'; line.style.visibility = 'hidden';
      if (p.z < -1 || p.z > 1 || p.x < 0 || p.x > size.width || p.y < 0 || p.y > size.height) continue;
      const w = element.offsetWidth, h = element.offsetHeight;
      const slots = [
        { x: p.x - w / 2, y: p.y - h - 14 },
        { x: p.x + 24, y: p.y - h - 6 },
        { x: p.x - w - 24, y: p.y - h - 6 },
        { x: p.x - w / 2, y: p.y - h - 44 },
        { x: p.x + 44, y: p.y - h - 30 },
        { x: p.x - w - 44, y: p.y - h - 30 },
      ].map(slot => ({ ...slot, w, h }));
      // The bottom band is reserved for the event caption inside the stage.
      const slot = slots.find(r => r.x >= 8 && r.y >= 8 && r.x + w <= size.width - 8 && r.y + h <= size.height - 116 && !occupied.some(other => overlaps(r, other)));
      if (!slot) continue;
      occupied.push(slot);
      element.style.transform = `translate(${slot.x}px, ${slot.y}px)`;
      element.style.visibility = 'visible';
      line.setAttribute('x1', String(p.x)); line.setAttribute('y1', String(p.y));
      line.setAttribute('x2', String(Math.max(slot.x, Math.min(p.x, slot.x + w))));
      line.setAttribute('y2', String(slot.y + h));
      line.style.visibility = 'visible';
    }
  });
  return <Html calculatePosition={() => [0, 0]} zIndexRange={[40, 40]} style={{ pointerEvents: 'none', width: size.width, height: size.height }}>
    <div className="stage-label-layer">
      <svg aria-hidden="true" width={size.width} height={size.height}>{labels.map(label => <line key={label.id} ref={node => { lines.current[label.id] = node; }} stroke={label.color ?? '#64776b'} strokeWidth="1" opacity=".55" />)}</svg>
      {labels.map(label => <button key={label.id} ref={node => { elements.current[label.id] = node; }} className={`stage-small-label ${label.kind} ${label.active ? 'active' : ''}`} title={label.text} aria-label={`${label.kind === 'actor' ? '角色' : label.kind === 'item' ? '道具' : '区域'}：${label.text}`} onClick={label.onSelect} style={{ borderColor: label.color }}><i style={{ background: label.color ?? '#718578' }} /><span>{label.text}</span></button>)}
    </div>
  </Html>;
}
