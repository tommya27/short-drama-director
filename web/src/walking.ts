import type { Vec3 } from './stage-manifest';
export const WALK_SPEED = 1.8;
const distance = (a: Vec3, b: Vec3) => Math.hypot(a[0] - b[0], a[2] - b[2]);
const inside = (p: Vec3) => Math.abs(p[0]) < 4.8 && Math.abs(p[2]) < 4;

// Route through the open front of the procedural room, around the table and
// side wall. This is presentation geometry, never a new narrative action.
export function walkingPath(from: Vec3, to: Vec3): Vec3[] {
  if (distance(from, to) < .02) return [];
  if (!inside(from) && !inside(to) && Math.sign(from[0]) === Math.sign(to[0])) return [to];
  const exitX = inside(from) ? (from[0] < 0 ? -3.4 : 3.4) : from[0];
  const entryX = inside(to) ? (to[0] < 0 ? -3.4 : 3.4) : to[0];
  const points: Vec3[] = [[exitX, 0, from[2]], [exitX, 0, 4.8], [entryX, 0, 4.8], [entryX, 0, to[2]], to];
  let previous = from;
  return points.filter(point => { if (distance(previous, point) < .02) return false; previous = point; return true; });
}
export function walkingSeconds(from: Vec3, to: Vec3) {
  let previous = from, length = 0;
  for (const point of walkingPath(from, to)) { length += distance(previous, point); previous = point; }
  return length / WALK_SPEED;
}
