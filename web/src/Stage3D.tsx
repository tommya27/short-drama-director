import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Line, OrbitControls, useTexture } from '@react-three/drei';
import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Group, Vector3, MathUtils } from 'three';
import type { WorldStageProps, StageMotion } from './types';
import { StageLabels, type StageLabel } from './StageLabels';
import { WALK_SPEED, walkingPath } from './walking';
import { actorPositions, layoutFor, type Vec3, type StageLayout } from './stage-manifest';
import { assetSrc } from './api';

/** 美术素材加载失败时只丢素材层，不影响 3D 舞台与操作。 */
class ArtBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
 state = { failed: false };
 static getDerivedStateFromError() { return { failed: true }; }
 render() { return this.state.failed ? null : this.props.children; }
}
function Backdrop({ url }: { url: string }) {
 const texture = useTexture(url);
 return <mesh position={[0, 1.9, -3.9]}><planeGeometry args={[9.9, 3.6]}/><meshBasicMaterial map={texture} toneMapped={false}/></mesh>;
}
function PortraitSprite({ url, position }: { url: string; position: Vec3 }) {
 const texture = useTexture(url);
 return <sprite position={position} scale={[0.9, 1.2, 1]}><spriteMaterial map={texture} transparent depthWrite={false}/></sprite>;
}
type Props=WorldStageProps & {preset:string;showObservers:boolean;showLabels:boolean;onFailure:()=>void};
function Box({position,size,color,rotation=0}:{position:Vec3;size:Vec3;color:string;rotation?:number}) {return <mesh position={position} rotation={[0,rotation,0]} castShadow receiveShadow><boxGeometry args={size}/><meshStandardMaterial color={color} roughness={.75}/></mesh>;}
function Plant({position}:{position:Vec3}) {return <group position={position}><mesh position={[0,.3,0]} castShadow><cylinderGeometry args={[.3,.22,.6,8]}/><meshStandardMaterial color="#a66f51"/></mesh>{[0,1,2,3,4].map(i=><mesh key={i} position={[Math.sin(i*2)*.22,.85+i*.09,Math.cos(i*2)*.22]} rotation={[0,i,Math.sin(i)*.6]} castShadow><icosahedronGeometry args={[.4,0]}/><meshStandardMaterial color={i%2?'#627e5d':'#8ba572'}/></mesh>)}</group>;}
function Rock({position,size=1,color="#8b8f86"}:{position:Vec3;size?:number;color?:string}) {return <mesh position={position} castShadow receiveShadow><dodecahedronGeometry args={[.5*size,0]}/><meshStandardMaterial color={color} roughness={.95}/></mesh>;}
function Pine({position,scale=1,color="#4f6b52"}:{position:Vec3;scale?:number;color?:string}) {return <group position={position} scale={scale}><mesh position={[0,.5,0]} castShadow><cylinderGeometry args={[.09,.13,1,6]}/><meshStandardMaterial color="#6b5a44"/></mesh>{[0,1,2].map(i=><mesh key={i} position={[0,1+i*.42,0]} castShadow><coneGeometry args={[.62-i*.15,.66,8]}/><meshStandardMaterial color={color}/></mesh>)}</group>;}
function Rail({position,length=6,rotation=0,color="#6f6a5f"}:{position:Vec3;length?:number;rotation?:number;color?:string}) {return <group position={position} rotation={[0,rotation,0]}>{[-length/2,-length/6,length/6,length/2].map(x=><Box key={x} position={[x,.5,0]} size={[.08,1,.08]} color={color}/>)}<Box position={[0,.98,0]} size={[length,.09,.1]} color={color}/><Box position={[0,.55,0]} size={[length,.06,.08]} color={color}/></group>;}
function Console({position,color="#39474f",accent="#7fb0b8"}:{position:Vec3;color?:string;accent?:string}) {return <group position={position}><Box position={[0,.45,0]} size={[3.2,.9,1.1]} color={color}/><Box position={[0,.95,-.25]} size={[3.2,.1,.5]} color={accent}/><Box position={[0,1.05,-.32]} size={[1.2,.6,.06]} color="#2b3339"/>{[-1.1,-.55,.55,1.1].map(x=><Box key={x} position={[x,.95,.12]} size={[.22,.06,.16]} color={accent}/>)}</group>;}
function Outdoor({layout}:{layout:StageLayout}) {
 const accent=layout.accent, wood=layout.wood;
 return <group>
  <Rock position={[-4.6,0.2,-2.4]} size={1.7} color={layout.wall}/>
  <Rock position={[4.4,0.15,-1.6]} size={1.3} color={layout.wall}/>
  <Rock position={[2.2,0.12,3.4]} size={1.0} color={layout.wall}/>
  <Pine position={[-5.6,0,-3.9]} scale={1.5} color={accent}/>
  <Pine position={[5.4,0,-3.2]} scale={1.1} color={accent}/>
  <Pine position={[-3.2,0,4.2]} scale={.9} color={accent}/>
  <Rail position={[0,0,4.6]} length={11} color={wood}/>
  {layout.assets.includes("console")&&<Console position={[0,0,-2.6]} color={layout.wood} accent={accent}/>}
  {layout.assets.includes("pillars")&&[-3.4,3.4].map(x=><Box key={x} position={[x,1.6,-3.6]} size={[.5,3.2,.5]} color={layout.wall}/>)}
 </group>;
}
function Room({layout}:{layout:StageLayout}) {
 const historic=layout.key==='inn'||layout.key==='mansion';
 const outdoor=layout.assets.includes('outdoor');
 return <group>
  <Box position={[0,-.18,0]} size={outdoor?[19,.36,15]:[10,.36,8]} color={layout.floor}/>
  <group visible={!outdoor}>
  <Box position={[0,1.7,-4]} size={[10,3.5,.14]} color={layout.wall}/>
  <Box position={[-5,1.3,0]} size={[.14,2.7,8]} color={layout.wall}/>
  <Box position={[0,.015,0]} size={[7,.035,5.5]} color={historic?'#998b73':'#c8cdc2'}/>
  <Box position={[1.5,2.2,-3.9]} size={[5,1.65,.08]} color="#455f68"/>
  <Box position={[1.5,2.2,-3.83]} size={[4.8,1.46,.035]} color={historic?'#a5b6ac':'#a9c3c5'}/>
  {[-.15,1.5,3.15].map(x=><Box key={x} position={[x,2.2,-3.77]} size={[.055,1.5,.07]} color={layout.wood}/>)}
  <group visible={layout.assets.includes("screen")}>{historic?<><Box position={[-3.3,1.25,-3.75]} size={[1.5,2.2,.15]} color="#e4d4b2"/><Box position={[-3.3,1.25,-3.62]} size={[.55,1.35,.04]} color="#686658"/></>:<Box position={[-3.25,1.9,-3.75]} size={[1.95,1.25,.1]} color="#303e46"/>}</group>
  <group visible={layout.assets.includes("table")}>{historic?<mesh position={[0,1,0]} castShadow receiveShadow><cylinderGeometry args={[1.8,1.8,.18,32]}/><meshStandardMaterial color={layout.wood}/></mesh>:<Box position={[0,1,0]} size={[3.5,.18,2.1]} color={layout.wood}/>}
  {[-1.2,1.2].map(x=><Box key={x} position={[x,.48,0]} size={[.18,.94,1.4]} color="#535b54"/>)}
  </group><group visible={layout.assets.includes("chairs")}>{[[-2.4,0,.3],[2.4,0,.3],[0,0,-2.2],[0,0,2.2]].map((p,i)=><group key={i} position={p as Vec3} rotation={[0,i===0?Math.PI/2:i===1?-Math.PI/2:i===2?0:Math.PI,0]}><Box position={[0,.46,0]} size={[.64,.14,.64]} color={layout.accent}/><Box position={[0,.87,-.3]} size={[.64,.85,.12]} color={layout.accent}/>{[-.23,.23].map(x=><Box key={x} position={[x,.22,0]} size={[.07,.45,.46]} color="#535854"/>)}</group>)}
  </group><group visible={layout.assets.includes("plants")}><Plant position={[-4.25,0,-2.9]}/><Plant position={[4.2,0,-3]}/></group>
  <group visible={layout.assets.includes("cabinet")}><Box position={[-4.45,.65,.25]} size={[.85,1.3,2.6]} color={layout.wood}/>
  <Box position={[-4.45,1.35,.25]} size={[.94,.12,2.7]} color="#e6dfcf"/>
  {layout.key==='inn'&&[0,1,2].map(i=><mesh key={i} position={[-4.4,1.65,i*.65-.4]} castShadow><sphereGeometry args={[.21,8,8]}/><meshStandardMaterial color="#9c674a"/></mesh>)}
  </group>
  </group>
  {outdoor&&<Outdoor layout={layout}/>}
  {layout.zones.slice(1).map((zone,i)=><group key={zone} position={layout.anchors[zone]}><Box position={[0,-.12,0]} size={[3.4,.2,3]} color={layout.floor}/><Box position={[0,.025,0]} size={[3.1,.02,2.7]} color={i%2?'#aeb6b9':'#b8b29f'}/></group>)}
 </group>;
}
function Avatar({id,color,position,target,selected,onSelect,onHover,motion}:{id:string;color:string;position:Vec3;target:Vec3;selected:boolean;onSelect:()=>void;onHover:(hovered:boolean)=>void;motion?:StageMotion}) {
 const group=useRef<Group>(null); const legs=useRef<Group>(null); const initialPosition=useRef(position); const destination=useMemo(()=>new Vector3(...position),[position[0],position[2]]);
 const path=useRef<Vector3[]>([]); const gait=useRef(0); const previousSeek=useRef(motion?.seek);
 useEffect(()=>{if(!group.current)return;const p=group.current.position;if(previousSeek.current!==motion?.seek){p.copy(destination);path.current=[];previousSeek.current=motion?.seek;}else path.current=walkingPath([p.x,p.y,p.z],position).map(point=>new Vector3(...point));},[destination,motion?.seek]);
 const moving=useRef(false);
 useFrame((_,delta)=>{if(!group.current||motion?.paused)return;const p=group.current.position;let budget=Math.min(delta,.08)*WALK_SPEED*(motion?.speed??1);moving.current=path.current.length>0;const goal=path.current[0];const facing=goal?Math.atan2(goal.x-p.x,goal.z-p.z):Math.atan2(target[0]-p.x,target[2]-p.z);const angle=Math.atan2(Math.sin(facing-group.current.rotation.y),Math.cos(facing-group.current.rotation.y));group.current.rotation.y+=angle*Math.min(delta*10,1);while(budget>0&&path.current.length){const next=path.current[0],distance=p.distanceTo(next);if(distance<=budget){p.copy(next);path.current.shift();budget-=distance;}else{p.addScaledVector(next.clone().sub(p).normalize(),budget);budget=0;}}gait.current+=delta*9*(motion?.speed??1);legs.current?.children.forEach((leg,index)=>{leg.rotation.x=moving.current?Math.sin(gait.current+index*Math.PI)*.5:0;});});
 return <>
 <group name={`actor:${id}`} ref={group} position={initialPosition.current} onClick={e=>{e.stopPropagation();onSelect();}} onPointerOver={e=>{e.stopPropagation();onHover(true);}} onPointerOut={()=>onHover(false)}>
  <mesh rotation={[-Math.PI/2,0,0]} position={[0,.025,0]}><ringGeometry args={[.44,.49,40]}/><meshBasicMaterial color={selected?'#e1ab54':color} transparent opacity={selected?1:.5}/></mesh>
  <group ref={legs}>{[-.13,.13].map(x=><group key={x} position={[x,.46,0]}><Box position={[0,-.22,0]} size={[.17,.46,.2]} color="#303d48"/><Box position={[0,-.38,.06]} size={[.19,.12,.3]} color="#30363c"/></group>)}</group>
  <mesh position={[0,.7,0]} castShadow><capsuleGeometry args={[.23,.36,4,8]}/><meshStandardMaterial color={color}/></mesh>
  {[-.3,.3].map(x=><mesh key={x} position={[x,.65,.035]} rotation={[.05,0,x<0?-.12:.12]} castShadow><capsuleGeometry args={[.075,.31,4,6]}/><meshStandardMaterial color={color}/></mesh>)}
  <Box position={[0,.77,.235]} size={[.1,.27,.018]} color="#e7e5d9"/>
  <mesh position={[0,1.22,0]} castShadow><sphereGeometry args={[.32,16,12]}/><meshStandardMaterial color="#dcad89"/></mesh>
  <mesh position={[0,1.32,-.055]} castShadow><sphereGeometry args={[.32,12,8,0,Math.PI*2,0,Math.PI*.68]}/><meshStandardMaterial color="#3e3636"/></mesh>
  {[-.11,.11].map(x=><mesh key={x} position={[x,1.23,.294]}><sphereGeometry args={[.024,8,6]}/><meshStandardMaterial color="#353237"/></mesh>)}
 </group>
 </>;
}
function Item({id,position,index,selected,onSelect,onHover,holder,motion}:{id:string;position:Vec3;index:number;selected:boolean;onSelect:()=>void;onHover:(hovered:boolean)=>void;holder?:string|null;motion?:StageMotion}) {const ref=useRef<Group>(null);const initial=useRef(position);const target=useMemo(()=>new Vector3(...position),[...position]);const previousSeek=useRef(motion?.seek);useEffect(()=>{if(previousSeek.current!==motion?.seek){ref.current?.position.copy(target);previousSeek.current=motion?.seek;}},[motion?.seek,target]);useFrame(({scene},d)=>{if(motion?.paused)return;const actor=holder?scene.getObjectByName(`actor:${holder}`):undefined;const next=actor?actor.position.clone().add(new Vector3(.45,.7,.15)):target;ref.current?.position.lerp(next,1-Math.exp(-Math.min(d,.08)*10*(motion?.speed??1)));});return <group name={`item:${id}`} ref={ref} position={initial.current} onClick={e=>{e.stopPropagation();onSelect();}} onPointerOver={e=>{e.stopPropagation();onHover(true);}} onPointerOut={()=>onHover(false)}><Box position={[0,0,0]} size={[.36,.04,.46]} color={selected?'#d8ac61':index%2?'#445664':'#ece8d7'}/><Box position={[0,.026,0]} size={[.23,.009,.03]} color="#949886"/><mesh><sphereGeometry args={[.32,8,6]}/><meshBasicMaterial transparent opacity={0} depthWrite={false}/></mesh></group>;}
function Camera({preset,focus,onFailure,layout,compact}:{preset:string;focus:Vec3;onFailure:()=>void;layout:StageLayout;compact:boolean}) {
 const {camera,gl,size}=useThree(); const controls=useRef<any>(null);
 useEffect(()=>{const handler=(event:Event)=>{event.preventDefault();onFailure();};gl.domElement.addEventListener('webglcontextlost',handler);return()=>gl.domElement.removeEventListener('webglcontextlost',handler);},[gl,onFailure]);
 useEffect(()=>{
  const configured=layout.cameras.find(c=>c.id===preset); const close=['focus','speaker_focus'].includes(preset);
  const target=configured?.target?new Vector3(...configured.target):close?new Vector3(focus[0],.9,focus[2]):new Vector3(0,.3,0);
  const anchors=Object.values(layout.anchors); const halfWidth=Math.max(5,...anchors.map(a=>Math.abs(a[0])+1.7)); const halfDepth=Math.max(4,...anchors.map(a=>Math.abs(a[2])+1.7));
  let position:Vec3;
  if (configured?.position) position=configured.position;
  else if (preset==='top') position=[.1,Math.max(14,Math.max(halfWidth,halfDepth)*2.8),.1];
  else if (close) position=compact?[focus[0]+4.2,4.6,focus[2]+5.1]:[focus[0]+5,5,focus[2]+6];
  else {
   // Mobile viewports are nearly square. Fit the whole stage using the
   // horizontal FOV, then move the camera in so characters remain legible.
   const fov=compact?56:39; const aspect=Math.max(size.width/Math.max(size.height,1),.55); const hfov=2*Math.atan(Math.tan((fov*Math.PI/180)/2)*aspect); const radius=Math.max(halfWidth,halfDepth)+.55; const distance=radius/Math.tan(Math.min(fov*Math.PI/180,hfov)/2); const dir=new Vector3(.55,.5,.65).normalize(); const p=target.clone().addScaledVector(dir,distance); position=[p.x,p.y,p.z];
   (camera as any).fov=fov; (camera as any).updateProjectionMatrix();
  }
  camera.position.set(...position); camera.lookAt(target); controls.current?.target.copy(target); controls.current?.update();
 },[preset,focus[0],focus[2],camera,compact,size.width,size.height,JSON.stringify(layout.cameras),JSON.stringify(layout.anchors)]);
 return <OrbitControls ref={controls} makeDefault minDistance={compact?2:3} maxDistance={25} maxPolarAngle={Math.PI/2.08} enableDamping/>;
}

function SceneContent(props: Props) {
 const {size}=useThree(); const compact=size.width<560; const layout=layoutFor(props.scene,props.snapshot); const positions=actorPositions(props.snapshot,layout); const actors=Object.values(props.snapshot.actors); const lastEvent=props.events.find(event=>event.id===props.activeEventId)??props.events.at(-1); const focus=positions[props.selectedActor??'']??[0,0,0];
 const [hovered,setHovered]=useState<string|null>(null);
 const [selectedItem,setSelectedItem]=useState<string|null>(null);
 const [arrival,setArrival]=useState<string|null>(null);
 const previousEvent=useRef(lastEvent?.id);
 useEffect(()=>{if(previousEvent.current===lastEvent?.id)return;previousEvent.current=lastEvent?.id;setArrival(lastEvent?.move_to??null);const timer=setTimeout(()=>setArrival(null),4000);return()=>clearTimeout(timer);},[lastEvent?.id]);
 useEffect(()=>setSelectedItem(null),[props.selectedActor]);
 const colorFor=(index:number)=>actors[index].color??layout.characterColors[index%layout.characterColors.length]??['#587773','#be795d','#7c799a','#718c9b'][index%4];
 const labels:StageLabel[]=actors.flatMap((actor,index)=>{
  const selected=props.selectedActor===actor.id; const visible=props.showLabels||selected||hovered===`actor:${actor.id}`||(lastEvent?.actor_id===actor.id&&!!lastEvent.dialogue);
  return visible?[{id:`actor:${actor.id}`,objectName:`actor:${actor.id}`,text:actor.name,position:[0,1.65,0],kind:'actor',color:colorFor(index),priority:selected?100:80,active:selected,onSelect:()=>props.onActorSelect(actor.id)}]:[];
 });
 for(const item of Object.values(props.snapshot.items??{}))if(props.showLabels||selectedItem===item.id||hovered===`item:${item.id}`)labels.push({id:`item:${item.id}`,objectName:`item:${item.id}`,text:item.name,position:[0,.15,0],kind:'item',priority:selectedItem===item.id?90:40,active:selectedItem===item.id,onSelect:()=>setSelectedItem(selectedItem===item.id?null:item.id)});
 for(const zone of layout.zones)if(props.showLabels||arrival===zone){const p=layout.anchors[zone];if(p)labels.push({id:`zone:${zone}`,text:zone,position:[p[0],.1,p[2]+1.3],kind:'zone',priority:10});}
 if(props.showLabels)for(const point of layout.points)if(!point.item_id)labels.push({id:`point:${point.id}`,text:point.label,position:point.position,kind:'zone',priority:20});
 return <>
  <ambientLight intensity={1.3}/><hemisphereLight args={['#fff4da','#86979e',1.7]}/><directionalLight position={[3,10,5]} intensity={2.3} castShadow shadow-mapSize={[1024,1024]} shadow-camera-left={-12} shadow-camera-right={12} shadow-camera-top={10} shadow-camera-bottom={-10} shadow-bias={-.0005}/>
  <Room layout={layout}/>
  <ArtBoundary>{props.artifacts?.filter(item=>item.kind==='backdrop').slice(0,1).map(item=><Backdrop key={item.asset_id} url={assetSrc(item.url)}/>)}{(props.artifacts??[]).filter(item=>item.kind==='portrait'&&item.actor_id&&positions[String(item.actor_id)]).map(item=>{const anchor=positions[String(item.actor_id)];return <PortraitSprite key={item.asset_id} url={assetSrc(item.url)} position={[anchor[0],2.35,anchor[2]]}/>;})}</ArtBoundary>
  {layout.points.map(point=><group key={point.id} position={point.position}><mesh rotation={[-Math.PI/2,0,0]}><ringGeometry args={[.18,.22,24]}/><meshBasicMaterial color={layout.accent} transparent opacity={.5}/></mesh></group>)}
  {actors.map((actor,index)=>{const event=props.events.filter(e=>e.actor_id===actor.id).at(-1); return <Avatar key={actor.id} id={actor.id} color={colorFor(index)} position={positions[actor.id]} target={positions[String(event?.target_id)]??[0,0,0]} selected={props.selectedActor===actor.id} motion={props.motion} onSelect={()=>props.onActorSelect(actor.id)} onHover={value=>setHovered(value?`actor:${actor.id}`:null)}/>;})}
  {Object.values(props.snapshot.items??{}).map((item,index)=>{const p=item.holder?positions[item.holder]:undefined;const zone=layout.anchors[item.location??'']??[0,0,0];const point=layout.points.find(point=>point.item_id===item.id);return <Item key={item.id} id={item.id} index={index} holder={item.holder} motion={props.motion} selected={selectedItem===item.id} onSelect={()=>setSelectedItem(selectedItem===item.id?null:item.id)} onHover={value=>setHovered(value?`item:${item.id}`:null)} position={p?[p[0]+.45,.7,p[2]+.15]:point?.position??[zone[0]+(index%3)*.45-.5,zone[0]===0&&layout.assets.includes("table")?1.12:.15,zone[2]+.1]}/>;})}
  <StageLabels labels={labels} actorIds={actors.map(actor=>actor.id)}/>
  {props.showObservers&&lastEvent&&positions[lastEvent.actor_id]&&(lastEvent.observed_by??[]).filter(id=>id!==lastEvent.actor_id&&positions[id]).map(id=><Line key={id} points={[new Vector3(...positions[lastEvent.actor_id]).add(new Vector3(0,1,0)),new Vector3(...positions[id]).add(new Vector3(0,1,0))]} color="#508e80" dashed dashSize={.12} gapSize={.08} lineWidth={1.5}/>)}
  <Camera preset={props.preset} focus={focus} onFailure={props.onFailure} layout={layout} compact={compact}/>
 </>;
}
export default function Stage3D(props:Props) {
 return <Canvas shadows dpr={[1,1.5]} camera={{position:[11,10,13],fov:39}} gl={{antialias:true,alpha:false}} onCreated={({gl})=>{gl.setClearColor('#dddcd7');}} fallback={<p>此设备不支持 WebGL，请切换 2.5D。</p>}>
  <SceneContent {...props}/>
 </Canvas>;
}
