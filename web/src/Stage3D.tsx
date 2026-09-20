import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Html, Line, OrbitControls, useTexture } from '@react-three/drei';
import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Group, Vector3, MathUtils } from 'three';
import type { WorldStageProps, StageMotion } from './types';
import { StageLabels, type StageLabel } from './StageLabels';
import { WALK_SPEED, walkingPath } from './walking';
import { actorPositions, layoutFor, type Vec3, type StageLayout } from './stage-manifest';
import { assetSrc } from './api';
import { planDialogue } from './dialogue';

/** 美术素材加载失败时只丢素材层，不影响 3D 舞台与操作。 */
class ArtBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
 state = { failed: false };
 static getDerivedStateFromError() { return { failed: true }; }
 render() { return this.state.failed ? null : this.props.children; }
}
function SpeechBubble({ name, action, dialogue, chosen, lines }: { name: string; action?: string; dialogue?: string; chosen: boolean; lines: boolean }) {
 const plan = useMemo(() => planDialogue(dialogue ?? ""), [dialogue]);
 const [index, setIndex] = useState(0);
 useEffect(() => { setIndex(0); }, [dialogue]);
 useEffect(() => {
  if (!lines || plan.length <= 1 || index >= plan.length - 1) return;
  const timer = setTimeout(() => setIndex(current => Math.min(current + 1, plan.length - 1)), plan[index].durationMs);
  return () => clearTimeout(timer);
 }, [index, plan, lines]);
 const stepped = lines && plan.length > 1;
 const plain = dialogue ? (dialogue.length > 30 ? `${dialogue.slice(0, 30)}…` : dialogue) : '';
 return <div className={`speech-bubble ${chosen ? 'chosen' : ''}`}>
  <b>{name}</b>
  {dialogue
   ? <em>“{stepped ? plan[index].text : plain}”</em>
   : action && <em className="speech-action">{action.length > 24 ? `${action.slice(0, 24)}…` : action}</em>}
  {stepped && <i className="speech-progress">{index + 1} / {plan.length}</i>}
 </div>;
}
function Backdrop({ url }: { url: string }) {
 const texture = useTexture(url);
 return <mesh position={[0, 1.9, -3.9]}><planeGeometry args={[9.9, 3.6]}/><meshBasicMaterial map={texture} toneMapped={false}/></mesh>;
}
function PortraitSprite({ url, position }: { url: string; position: Vec3 }) {
 const texture = useTexture(url);
 return <sprite position={position} scale={[0.9, 1.2, 1]}><spriteMaterial map={texture} transparent depthWrite={false}/></sprite>;
}
type Props=WorldStageProps & {preset:string;showObservers:boolean;showLabels:boolean;onFailure:()=>void;showBubbles?:boolean};
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
function Sofa({position,rotation=0,color="#6d7a72",accent="#98a49b"}:{position:Vec3;rotation?:number;color?:string;accent?:string}) {return <group position={position} rotation={[0,rotation,0]}><Box position={[0,.35,0]} size={[2.2,.4,.9]} color={color}/><Box position={[0,.7,-.36]} size={[2.2,.6,.18]} color={accent}/>{[-1.02,1.02].map(x=><Box key={x} position={[x,.5,0]} size={[.16,.44,.9]} color={accent}/>)}<Box position={[0,.62,.34]} size={[2.2,.16,.18]} color={accent}/></group>;}
function Shelf({position,rotation=0,color="#7a6a55",accent="#c8bda6"}:{position:Vec3;rotation?:number;color?:string;accent?:string}) {return <group position={position} rotation={[0,rotation,0]}>{[0,1,2].map(i=><Box key={i} position={[0,.5+i*.7,0]} size={[1.8,.06,.5]} color={accent}/>)}<Box position={[-.88,1.1,0]} size={[.08,2.2,.5]} color={color}/><Box position={[.88,1.1,0]} size={[.08,2.2,.5]} color={color}/><Box position={[0,2.2,0]} size={[1.84,.08,.52]} color={color}/>{[.7,1.4].map((y,i)=><Box key={i} position={[i?.5:-.5,y+.2,0]} size={[.5,.3,.36]} color={i?"#9d8f78":"#8a9d92"}/>)}</group>;}
function Crate({position,rotation=0,size=1,color="#8a7048"}:{position:Vec3;rotation?:number;size?:number;color?:string}) {const s=size;return <group position={position} rotation={[0,rotation,0]}><Box position={[0,.45*s,0]} size={[1*s,.9*s,1*s]} color={color}/>{[-.36,.36].map(x=><Box key={x} position={[x*s,.45*s,.51*s]} size={[.1*s,.9*s,.04]} color="#6d5738"/>)}</group>;}
function Barrel({position,color="#5f6b62",accent="#8e6f42"}:{position:Vec3;color?:string;accent?:string}) {return <group position={position}><mesh position={[0,.5,0]} castShadow><cylinderGeometry args={[.38,.38,1,12]}/><meshStandardMaterial color={color} roughness={.8}/></mesh>{[.3,.7].map(y=><mesh key={y} position={[0,y,0]}><torusGeometry args={[.39,.035,8,16]}/><meshStandardMaterial color={accent}/></mesh>)}</group>;}
function Gate({position,rotation=0,width=4,color="#59616a"}:{position:Vec3;rotation?:number;width?:number;color?:string}) {const bars=[];for(let x=-width/2+.3;x<width/2;x+=.42)bars.push(x);return <group position={position} rotation={[0,rotation,0]}>{bars.map(x=><Box key={x} position={[x,1.2,0]} size={[.07,2.4,.07]} color={color}/>)}<Box position={[0,2.3,0]} size={[width,.1,.1]} color={color}/><Box position={[0,.35,0]} size={[width,.1,.1]} color={color}/>{[-width/2,width/2].map(x=><Box key={x} position={[x,1.25,0]} size={[.16,2.5,.16]} color="#454c53"/>)}</group>;}
function Door({position,rotation=0,color="#6b5a44",accent="#c9c2b0"}:{position:Vec3;rotation?:number;color?:string;accent?:string}) {return <group position={position} rotation={[0,rotation,0]}><Box position={[0,1.05,0]} size={[1.1,2.1,.1]} color={color}/><Box position={[0,1.05,-.05]} size={[.9,1.9,.06]} color={accent}/><mesh position={[.38,1,0]}><sphereGeometry args={[.06,8,8]}/><meshStandardMaterial color="#b9a15f" metalness={.6} roughness={.4}/></mesh></group>;}
function Car({position,rotation=0,color="#3f5566",glass="#8fb2c0"}:{position:Vec3;rotation?:number;color?:string;glass?:string}) {return <group position={position} rotation={[0,rotation,0]}><Box position={[0,.6,0]} size={[1.9,.55,4.2]} color={color}/><Box position={[0,1.05,-.15]} size={[1.7,.5,2.1]} color={glass}/>{[[-.95,1.4],[.95,1.4],[-.95,-1.4],[.95,-1.4]].map(([x,z],i)=><mesh key={i} position={[x,.28,z]} rotation={[0,0,Math.PI/2]}><cylinderGeometry args={[.28,.28,.16,12]}/><meshStandardMaterial color="#2b2f33"/></mesh>)}<Box position={[0,.42,2.12]} size={[1.5,.16,.1]} color="#e8e3cf"/><Box position={[0,.42,-2.12]} size={[1.5,.16,.1]} color="#8c3b3b"/></group>;}
function Podium({position,rotation=0,color="#6b5a44",accent="#d8cdb6"}:{position:Vec3;rotation?:number;color?:string;accent?:string}) {return <group position={position} rotation={[0,rotation,0]}><Box position={[0,.6,0]} size={[1,.08,.6]} color={accent}/><Box position={[0,.3,0]} size={[.7,.6,.45]} color={color}/><Box position={[-.2,1.0,0]} size={[.05,.7,.05]} color="#4a4f52"/><mesh position={[-.2,1.35,0]}><sphereGeometry args={[.09,8,8]}/><meshStandardMaterial color="#3d4245"/></mesh></group>;}
function Bench({position,rotation=0,length=3.4,color="#4d5a63",accent="#8fb0b6"}:{position:Vec3;rotation?:number;length?:number;color?:string;accent?:string}) {return <group position={position} rotation={[0,rotation,0]}><Box position={[0,.45,0]} size={[length,.14,.5]} color={color}/><Box position={[0,.72,-.22]} size={[length,.5,.1]} color={accent}/>{[-length/2+.25,length/2-.25].map(x=><Box key={x} position={[x,.22,0]} size={[.12,.44,.42]} color={color}/>)}</group>;}
function Pole({positions,color="#c9ced0"}:{positions:Vec3[];color?:string}) {return <>{positions.map((p,i)=><group key={i} position={p}><mesh position={[0,1.15,0]} castShadow><cylinderGeometry args={[.05,.05,2.3,8]}/><meshStandardMaterial color={color} metalness={.5} roughness={.4}/></mesh><mesh position={[0,2.3,0]}><sphereGeometry args={[.07,8,8]}/><meshStandardMaterial color={color}/></mesh></group>)}</>;}
function Counter({position,rotation=0,length=4.2,color="#6b5a44",accent="#d8cdb6"}:{position:Vec3;rotation?:number;length?:number;color?:string;accent?:string}) {return <group position={position} rotation={[0,rotation,0]}><Box position={[0,.55,0]} size={[length,1.1,.7]} color={color}/><Box position={[0,1.13,0]} size={[length+.2,.08,.86]} color={accent}/>{[-length/3,0,length/3].map(x=><Box key={x} position={[x,1.32,0]} size={[.16,.3,.16]} color={accent}/>)}</group>;}
function Lamp({positions,color="#5c6660",light="#ffe9b0"}:{positions:Vec3[];color?:string;light?:string}) {return <>{positions.map((p,i)=><group key={i} position={p}><mesh position={[0,1.6,0]} castShadow><cylinderGeometry args={[.05,.05,3.2,8]}/><meshStandardMaterial color={color}/></mesh><mesh position={[0,3.2,0]}><sphereGeometry args={[.18,10,10]}/><meshStandardMaterial color={light} emissive={light} emissiveIntensity={.5}/></mesh></group>)}</>;}
function Desk({positions,color="#6b5a44",accent="#c9c2b0"}:{positions:Vec3[];color?:string;accent?:string}) {return <>{positions.map((p,i)=><group key={i} position={p}><Box position={[0,.72,0]} size={[1.2,.08,.6]} color={accent}/><Box position={[0,.36,0]} size={[1.1,.7,.5]} color={color}/></group>)}</>;}
function Bed({position,color="#dfe3e0",accent="#9fb3bb"}:{position:Vec3;color?:string;accent?:string}) {return <group position={position}><Box position={[0,.3,0]} size={[1.1,.3,2.1]} color={color}/><Box position={[0,.48,-.85]} size={[1,.14,.34]} color={accent}/><Box position={[0,.62,0]} size={[1.06,.06,1.9]} color={accent}/></group>;}

function VehicleInterior({layout}:{layout:StageLayout}) {
 const color=layout.wood, accent=layout.accent;
 return <group>
  <Box position={[0,2.55,0]} size={[9.6,.16,4.2]} color="#dfe2e2"/>
  <group visible={layout.assets.includes("window_strip")}><Box position={[0,1.75,-2.05]} size={[9.4,1.05,.06]} color="#2c3a42"/>{[-3.4,-1.1,1.1,3.4].map(x=><Box key={x} position={[x,1.75,-2.0]} size={[.08,1.05,.05]} color="#7c8b91"/>)}</group>
  <group visible={layout.assets.includes("bench")}><Bench position={[-2.6,0,1.35]} rotation={0} length={3.6} color={color} accent={accent}/><Bench position={[2.6,0,1.35]} rotation={0} length={3.6} color={color} accent={accent}/><Bench position={[-2.6,0,-1.35]} rotation={Math.PI} length={3.6} color={color} accent={accent}/><Bench position={[2.6,0,-1.35]} rotation={Math.PI} length={3.6} color={color} accent={accent}/></group>
  <group visible={layout.assets.includes("pole")}><Pole positions={[[-1.3,0,.2],[0,0,-.2],[1.3,0,.2],[-2.2,0,-.2],[2.2,0,-.2]]}/></group>
  {layout.assets.includes("console")&&<Console position={[0,0,-1.9]} color={color} accent={accent}/>}
  <group visible={layout.assets.includes("table")}><Box position={[0,.6,0]} size={[2.6,.1,1.4]} color={layout.wood}/><Box position={[0,.3,0]} size={[.2,.6,1.1]} color="#4c5459"/></group>
 </group>;
}
function Timber({position,rotation=0,height=2.2,width=1.9,color="#6b5238"}:{position:Vec3;rotation?:number;height?:number;width?:number;color?:string}) {return <group position={position} rotation={[0,rotation,0]}><Box position={[-width/2,height/2,0]} size={[.18,height,.18]} color={color}/><Box position={[width/2,height/2,0]} size={[.18,height,.18]} color={color}/><Box position={[0,height,0]} size={[width+.34,.2,.22]} color={color}/>{[-width/4,width/4].map(x=><Box key={x} position={[x,height*.55,0]} size={[.1,height*.7,.1]} color="#5b462f"/>)}</group>;}
function Track({position,length=12,rotation=0,color="#5d5347"}:{position:Vec3;length?:number;rotation?:number;color?:string}) {const sleepers=[];for(let x=-length/2;x<=length/2;x+=.8)sleepers.push(x);return <group position={position} rotation={[0,rotation,0]}>{[-.34,.34].map(x=><Box key={x} position={[x,.06,0]} size={[.09,.09,length]} color={color}/>)}{sleepers.map(x=><Box key={x} position={[0,.02,x]} size={[.9,.06,.16]} color="#6f6353"/>)}</group>;}
function MineCart({position,color="#4e5a60",ore="#8d7f6a"}:{position:Vec3;color?:string;ore?:string}) {return <group position={position}><Box position={[0,.62,0]} size={[1.3,.8,1.02]} color={color}/><Box position={[0,1.0,0]} size={[1.42,.08,1.14]} color="#5c686e"/>{[[-.42,-.3],[.42,-.3],[-.42,.3],[.42,.3]].map(([x,z],i)=><mesh key={i} position={[x,.24,z]} rotation={[Math.PI/2,0,0]}><cylinderGeometry args={[.22,.22,.1,12]}/><meshStandardMaterial color="#3a4247" metalness={.4} roughness={.6}/></mesh>)}<mesh position={[0,.92,0]} castShadow><dodecahedronGeometry args={[.3,0]}/><meshStandardMaterial color={ore} roughness={1}/></mesh></group>;}
function Lantern({position,light="#ffd88a"}:{position:Vec3;light?:string}) {return <group position={position}><mesh position={[0,.9,0]} castShadow><cylinderGeometry args={[.12,.12,.28,10]}/><meshStandardMaterial color="#54463a"/></mesh><mesh position={[0,.9,0]}><sphereGeometry args={[.14,10,10]}/><meshStandardMaterial color={light} emissive={light} emissiveIntensity={1.4}/></mesh><pointLight position={[0,.9,0]} intensity={6} distance={8} color={light}/><Box position={[0,2.05,0]} size={[.06,.5,.06]} color="#4a3f33"/></group>;}
function CaveInterior({layout}:{layout:StageLayout}) {
 const rock=layout.wall, ground=layout.floor, timber=layout.wood, accent=layout.accent;
 const dark="#3b3833";
 return <group>
  <Box position={[0,-.1,0]} size={[14,.3,13]} color={ground}/>
  <Box position={[0,2.9,0]} size={[14,.4,13]} color={dark}/>
  {[-7,7].map(x=><group key={`side${x}`}>{[-5,-2,1,4].map(z=><Rock key={z} position={[x,.45,z]} size={2.4} color={rock}/>)}</group>)}
  {[-4,0,4].map(x=><Rock key={`back${x}`} position={[x,.5,-6.4]} size={2.6} color={rock}/>)}
  {[-3,3].map(x=><Rock key={`front${x}`} position={[x,.4,6.4]} size={2.2} color={rock}/>)}
  {layout.assets.includes("tunnel")&&<group>{[-3.2,3.2].map(x=><Timber key={x} position={[x,0,-3.4]} height={2.6} width={2.2} color={timber}/>)}{[-1.6,1.6].map(x=><Rock key={x} position={[x,1.9,-4.2]} size={1.6} color={rock}/>)}</group>}
  {layout.assets.includes("timber")&&!layout.assets.includes("tunnel")&&<Timber position={[0,0,-2.6]} height={2.4} width={2.6} color={timber}/>}
  {layout.assets.includes("track")&&<Track position={[0,0,0]} length={13} color={accent}/>}
  {layout.assets.includes("minecart")&&<MineCart position={[-1.9,0,1.4]} color={timber} ore={rock}/>}
  {layout.assets.includes("lantern")&&<Lantern position={[2.6,0,-3.0]}/>}
  {!layout.assets.includes("lantern")&&<Lantern position={[2.4,0,-3.0]}/>}
  {layout.assets.includes("debris")&&[[-3.4,.15,2.2],[3.6,.12,1.6],[.8,.1,4.2]].map((p,i)=><Rock key={i} position={p as Vec3} size={.8} color={rock}/>)}
 </group>;
}
function StreetScene({layout}:{layout:StageLayout}) {
 return <group>
  <Box position={[0,.02,0]} size={[19,.06,15]} color={layout.wood}/>
  <Lamp positions={[[-5,0,-2],[5,0,-2],[-5,0,3],[5,0,3]]} color={layout.wall}/>
  {[-6,6].map(x=><Box key={x} position={[x,1.3,-4.4]} size={[3,.12,2.2]} color={layout.wall}/>)}
  <Rail position={[0,0,4.6]} length={11} color={layout.accent}/>
  {layout.assets.includes("pillars")&&[-3.6,3.6].map(x=><Box key={x} position={[x,1.8,-3.4]} size={[.6,3.6,.6]} color={layout.wall}/>)}
 </group>;
}
function Room({layout}:{layout:StageLayout}) {
 const historic=layout.key==='inn'||layout.key==='mansion';
 const form=layout.form;
 const outdoor=form==='outdoor';
 return <group>
  <Box position={[0,-.18,0]} size={form==='interior'?[10,.36,8]:[19,.36,15]} color={layout.floor}/>
  <group visible={form==='interior'}>
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
  {form==='vehicle'&&<VehicleInterior layout={layout}/>}
  {form==='street'&&<StreetScene layout={layout}/>}
  {form==='cave'&&<CaveInterior layout={layout}/>}
  {layout.assets.includes("counter")&&form!=='outdoor'&&<Counter position={[0,0,-2.6]} color={layout.wood} accent={layout.accent}/>}
  {layout.assets.includes("desk")&&form==='interior'&&<Desk positions={[[-3,0,-1],[0,0,-1],[3,0,-1]]} color={layout.wood} accent={layout.accent}/>}
  {layout.assets.includes("bed")&&form==='interior'&&<Bed position={[-3.4,0,1.6]} color="#e6e9e6" accent={layout.accent}/>}
  {layout.assets.includes("sofa")&&<Sofa position={[3.6,0,1.2]} rotation={-Math.PI/2} color={layout.accent} accent={layout.wood}/>}
  {layout.assets.includes("shelf")&&<Shelf position={[-4.2,0,-1.6]} rotation={Math.PI/2} color={layout.wood} accent="#c8bda6"/>}
  {layout.assets.includes("crate")&&<><Crate position={[3.9,0,-2.4]}/><Crate position={[3.2,0,-2.9]} size={.7} rotation={.5}/></>}
  {layout.assets.includes("barrel")&&<Barrel position={[-3.9,0,2.6]} color={layout.wood}/>}
  {layout.assets.includes("gate")&&<Gate position={[0,0,form==='interior'?-4.6:5.4]} rotation={form==='interior'?0:Math.PI} width={4.4} color={layout.wall}/>}
  {layout.assets.includes("door")&&form==='interior'&&<Door position={[4.2,0,-3.9]} color={layout.wood}/>}
  {layout.assets.includes("car")&&<Car position={[4.6,0,3.2]} rotation={Math.PI*.75} color={layout.accent}/>}
  {layout.assets.includes("podium")&&<Podium position={[0,0,2.4]} rotation={Math.PI} color={layout.wood} accent={layout.accent}/>}
  {layout.zones.slice(1).map((zone,i)=><group key={zone} position={layout.anchors[zone]}><Box position={[0,-.12,0]} size={[3.4,.2,3]} color={layout.floor}/><Box position={[0,.025,0]} size={[3.1,.02,2.7]} color={i%2?'#aeb6b9':'#b8b29f'}/></group>)}
 </group>;
}
function Avatar({id,color,position,target,selected,addressed,onSelect,onHover,motion}:{id:string;color:string;position:Vec3;target:Vec3;selected:boolean;addressed?:boolean;onSelect:()=>void;onHover:(hovered:boolean)=>void;motion?:StageMotion}) {
 const group=useRef<Group>(null); const legs=useRef<Group>(null); const initialPosition=useRef(position); const destination=useMemo(()=>new Vector3(...position),[position[0],position[2]]);
 const path=useRef<Vector3[]>([]); const gait=useRef(0); const previousSeek=useRef(motion?.seek);
 useEffect(()=>{if(!group.current)return;const p=group.current.position;if(previousSeek.current!==motion?.seek){p.copy(destination);path.current=[];previousSeek.current=motion?.seek;}else path.current=walkingPath([p.x,p.y,p.z],position).map(point=>new Vector3(...point));},[destination,motion?.seek]);
 const moving=useRef(false);
 useFrame((_,delta)=>{if(!group.current||motion?.paused)return;const p=group.current.position;let budget=Math.min(delta,.08)*WALK_SPEED*(motion?.speed??1);moving.current=path.current.length>0;const goal=path.current[0];const facing=goal?Math.atan2(goal.x-p.x,goal.z-p.z):Math.atan2(target[0]-p.x,target[2]-p.z);const angle=Math.atan2(Math.sin(facing-group.current.rotation.y),Math.cos(facing-group.current.rotation.y));group.current.rotation.y+=angle*Math.min(delta*10,1);while(budget>0&&path.current.length){const next=path.current[0],distance=p.distanceTo(next);if(distance<=budget){p.copy(next);path.current.shift();budget-=distance;}else{p.addScaledVector(next.clone().sub(p).normalize(),budget);budget=0;}}gait.current+=delta*9*(motion?.speed??1);legs.current?.children.forEach((leg,index)=>{leg.rotation.x=moving.current?Math.sin(gait.current+index*Math.PI)*.5:0;});});
 return <>
 <group name={`actor:${id}`} ref={group} position={initialPosition.current} onClick={e=>{e.stopPropagation();onSelect();}} onPointerOver={e=>{e.stopPropagation();onHover(true);}} onPointerOut={()=>onHover(false)}>
  <mesh rotation={[-Math.PI/2,0,0]} position={[0,.025,0]}><ringGeometry args={[.44,.49,40]}/><meshBasicMaterial color={selected?'#e1ab54':color} transparent opacity={selected?1:.5}/></mesh>
  {addressed&&<mesh rotation={[-Math.PI/2,0,0]} position={[0,.03,0]}><ringGeometry args={[.62,.7,44]}/><meshBasicMaterial color="#6fb3bd" transparent opacity={.95}/></mesh>}
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
  {actors.map((actor,index)=>{const event=props.events.filter(e=>e.actor_id===actor.id).at(-1); return <Avatar key={actor.id} id={actor.id} color={colorFor(index)} position={positions[actor.id]} target={positions[String(event?.target_id)]??[0,0,0]} selected={props.selectedActor===actor.id} addressed={!!lastEvent?.target_id&&String(lastEvent.target_id)===actor.id} motion={props.motion} onSelect={()=>props.onActorSelect(actor.id)} onHover={value=>setHovered(value?`actor:${actor.id}`:null)}/>;})}
  {(() => {
   if (props.showBubbles === false) return null;   // 导演可一键关闭气泡
   // 同一时刻只显示一个说话气泡，彻底避免多人气泡互相遮挡
   const newest = props.events.at(-1)?.actor_id;
   const activeId = (props.selectedActor && positions[props.selectedActor]) ? props.selectedActor : newest;
   if (!activeId) return null;
   const speaker = actors.find(actor => actor.id === activeId);
   const latest = props.events.filter(event => event.actor_id === activeId).at(-1);
   const anchor = positions[activeId];
   if (!speaker || !latest || !anchor) return null;
   return <Html key={`say:${activeId}`} position={[anchor[0], 2.24, anchor[2]]} center zIndexRange={[20, 0]} style={{pointerEvents:'none'}}><SpeechBubble name={speaker.name} action={latest.action} dialogue={latest.dialogue} chosen={props.selectedActor === activeId} lines={!!props.dialogueLines}/></Html>;
  })()}
  {actors.map(actor=>{const latest=props.events.filter(e=>e.actor_id===actor.id).at(-1);const target=latest?.target_id?positions[latest.target_id]:undefined;const from=positions[actor.id];if(!target||!from)return null;
   return <Line key={`talk:${actor.id}`} points={[new Vector3(from[0],1.05,from[2]),new Vector3(target[0],1.05,target[2])]} color="#c79353" lineWidth={1.2} dashed dashSize={.22} gapSize={.16}/>;})}
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
