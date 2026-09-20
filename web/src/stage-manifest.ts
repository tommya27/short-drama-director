import type { SceneSpec, WorldSnapshot } from './types';
export type Vec3 = [number, number, number];
export type CameraPreset = { id: string; label: string; position?: Vec3; target?: Vec3 };
export type InteractionPoint = { id: string; label: string; position: Vec3; item_id?: string };
export type StageForm = "interior" | "outdoor" | "vehicle" | "street" | "cave";
export type StageLayout = { key: string; name: string; floor: string; wall: string; wood: string; accent: string; zones: string[]; anchors: Record<string, Vec3>; cameras: CameraPreset[]; assets: string[]; renderer: string; characterColors: string[]; points: InteractionPoint[]; form: StageForm };
/** 形态判定：显式 asset 标记优先，其次按场景类型关键词兜底（模型只给 scene_key 时也能换形态）。 */
const formPatterns: Array<[StageForm, RegExp]> = [
 ["cave", /矿|矿井|矿洞|洞窟|洞穴|地道|隧道|地窖|墓道|窑|坑道|cave|mine|tunnel|shaft|cellar|catacomb/],
 ["vehicle", /subway|metro|train|tram|car|bus|plane|aircraft|cockpit|bridge|ship|boat|ferry|yacht|cabin|车厢|地铁|高铁|列车|船|机舱|驾驶/],
 ["street", /street|plaza|square|pier|dock|market|alley|街头|广场|码头|集市|巷/],
 ["outdoor", /mountain|peak|forest|wood|beach|sea|ocean|park|desert|field|garden|camp|cliff|山|峰|林|海|滩|野|草原|营地|崖/],
];
export function stageForm(key: string, name: string, assets: string[]): StageForm {
 if (assets.includes("cave")) return "cave";
 if (assets.includes("outdoor") && !assets.includes("vehicle")) return "outdoor";
 if (assets.includes("vehicle")) return "vehicle";
 if (assets.includes("street")) return "street";
 const probe = `${key} ${name}`.toLowerCase();
 for (const [form, pattern] of formPatterns) if (pattern.test(probe)) return form;
 return "interior";
}
// One manifest per file; adding a scene never changes the story engine.
const files = import.meta.glob('../../scene_manifests/*.json', { eager: true, import: 'default' }) as Record<string, Record<string, unknown>>;
const manifests = Object.fromEntries(Object.values(files).map(value => [String(value.scene_key), value]));
export const sceneManifestOptions = Object.values(manifests).map(value=>({key:String(value.scene_key),label:String(value.name ?? value.scene_key)}));
const vector = (value: unknown): Vec3 | undefined => Array.isArray(value) && value.length === 3 && value.every(n => typeof n === 'number' && Number.isFinite(n)) ? value as Vec3 : undefined;
const cameraLabels: Record<string, string> = { wide: '全景', top: '俯视', focus: '角色近景', table_focus: '会议桌', speaker_focus: '角色近景' };
const palettes: Record<string, string[]> = {
 boardroom: ['#e1ddd1','#c8cabe','#a18464','#52746c'],
 inn: ['#bda58a','#d4c09c','#674a32','#bb6844'],
 mansion: ['#b4b9b3','#d8d0bd','#5c625d','#737098'],
 office: ['#d5dce0','#e0e5e3','#b6a284','#56889d'],
 generic: ['#d6d5dc','#d8d5e2','#a192b0','#8676a9'],
};
export function layoutFor(scene: SceneSpec, snapshot: WorldSnapshot): StageLayout {
 const requested = scene.scene_manifest?.scene_key ?? 'generic';
 const key = ['ancient_mansion','manor'].includes(requested) ? 'mansion' : requested === 'inn_mystery' ? 'inn' : requested;
 const manifest: Record<string, unknown> = { ...(manifests[key] ?? manifests.generic ?? {}), ...scene.scene_manifest };
 const palette = manifest.palette as Record<string,string> | undefined;
 const p = palettes[key] ?? palettes.generic;
 const zones = [...new Set(snapshot.locations?.length ? snapshot.locations : [scene.location])];
 const anchors: Record<string, Vec3> = {};
 zones.forEach((name,index) => { anchors[name] = index === 0 ? [0,0,0] : [index % 2 ? -6 : 6,0,Math.floor((index-1)/2)*4]; });
 const manifestZones = manifest.zones;
 if (Array.isArray(manifestZones)) for (const z of manifestZones) {
   if (z && typeof z === 'object' && 'id' in z && 'position' in z && vector(z.position)) anchors[String(z.id)] = vector(z.position)!;
 }
 const rawCameras = Array.isArray(manifest.camera_presets) ? manifest.camera_presets : ['wide','top','focus'];
 const cameras: CameraPreset[] = rawCameras.flatMap(raw => typeof raw === 'string' ? [{id:raw,label:cameraLabels[raw] ?? raw}] : raw && typeof raw === 'object' && 'id' in raw ? [{id:String(raw.id),label:String(raw.label ?? raw.id),position:vector(raw.position),target:vector(raw.target)}] : []);
 const assets = Array.isArray(manifest.asset_set) ? manifest.asset_set.filter((v): v is string => typeof v === 'string') : ['table','screen','chairs','plants','cabinet'];
 const characterColors = Array.isArray(manifest.character_colors) ? manifest.character_colors.filter((v): v is string => typeof v === 'string') : [];
 const points: InteractionPoint[] = Array.isArray(manifest.interaction_points) ? manifest.interaction_points.flatMap(raw => raw && typeof raw === 'object' && 'id' in raw && vector(raw.position) ? [{id:String(raw.id),label:String(raw.label ?? raw.id),position:vector(raw.position)!,item_id:typeof raw.item_id==='string'?raw.item_id:undefined}] : []) : [];
 const form = stageForm(key, String(manifest.name ?? scene.location ?? ''), assets);
 return { key, name:scene.location, floor:palette?.floor ?? p[0], wall:palette?.wall ?? p[1], wood:palette?.wood ?? p[2], accent:palette?.accent ?? p[3], zones, anchors, cameras:cameras.length ? cameras : [{id:'wide',label:'全景'}], assets, renderer:String(manifest.renderer_type ?? 'generic3d'), characterColors, points, form };
}
export function actorPositions(snapshot: WorldSnapshot, layout: StageLayout): Record<string, Vec3> {
 const positions: Record<string, Vec3> = {};
 const actors = Object.values(snapshot.actors ?? {});
 const seats: Vec3[] = [[-2.45,0,.5],[0,0,-2.3],[2.45,0,.5],[0,0,2.25],[-2,0,-1.6],[2,0,-1.6]];
 actors.forEach((actor,index) => {
   const anchor = layout.anchors[actor.location ?? layout.zones[0]] ?? [0,0,0];
   // Stable slots prevent stationary actors moving when someone else leaves.
   const seat = anchor[0] === 0 && anchor[2] === 0 ? seats[index % seats.length] : [Math.cos(index*2.4)*.9,0,Math.sin(index*2.4)*.9];
   positions[actor.id] = [anchor[0]+seat[0],0,anchor[2]+seat[2]+(index>5?Math.floor(index/6)*1.2:0)];
 });
 return positions;
}
