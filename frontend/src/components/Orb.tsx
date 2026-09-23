import {useEffect,useRef} from 'react';
export function Orb({level,active}:{level:number;active:boolean}){
 const canvas=useRef<HTMLCanvasElement>(null);const signal=useRef({level,active});signal.current={level,active};
 useEffect(()=>{const c=canvas.current!;const ctx=c.getContext('2d')!;let frame=0;let last=0;let rotation=0;
  const points=Array.from({length:260},(_,i)=>{const y=1-2*(i+.5)/260;const r=Math.sqrt(1-y*y);const a=i*2.399963;return [Math.cos(a)*r,y,Math.sin(a)*r];});
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const draw=(time:number)=>{const dt=Math.min(40,time-last);last=time;if(!reduced)rotation+=dt*.00006;
   const width=c.clientWidth,height=c.clientHeight,dpr=Math.min(devicePixelRatio,2);if(c.width!==width*dpr){c.width=width*dpr;c.height=height*dpr;}ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,width,height);
   const cx=width/2,cy=height/2,r=Math.min(width*.33,145)*(1+signal.current.level*.04);
   const glow=ctx.createRadialGradient(cx,cy,r*.1,cx,cy,r*1.6);glow.addColorStop(0,'rgba(32,196,143,.16)');glow.addColorStop(.65,'rgba(63,221,164,.1)');glow.addColorStop(1,'rgba(63,221,164,0)');ctx.fillStyle=glow;ctx.fillRect(0,0,width,height);
   const projected=points.map(([x,y,z])=>{const rx=x*Math.cos(rotation)-z*Math.sin(rotation),rz=x*Math.sin(rotation)+z*Math.cos(rotation);return {x:cx+rx*r,y:cy+y*r,z:rz};});
   for(let i=0;i<projected.length;i++){const p=projected[i];for(let j=i+1;j<projected.length;j++){const q=projected[j];const d=Math.hypot(points[i][0]-points[j][0],points[i][1]-points[j][1],points[i][2]-points[j][2]);if(d<.29){ctx.strokeStyle=`rgba(10,160,112,${.04+(p.z+1)*.09})`;ctx.lineWidth=.6;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();}}
    ctx.beginPath();ctx.arc(p.x,p.y,1+(p.z+1)*.5,0,Math.PI*2);ctx.fillStyle=`rgba(0,154,109,${.15+(p.z+1)*.35})`;ctx.fill();}
   const amplitude=signal.current.active?signal.current.level:0;
   for(const sign of [-1,1])for(let i=0;i<12;i++){const x=cx+sign*(r+20+i*6),h=3+amplitude*32*Math.abs(Math.sin(i*.6+rotation*8));ctx.strokeStyle=`rgba(17,167,117,${.45-i*.025})`;ctx.lineWidth=2;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(x,cy-h);ctx.lineTo(x,cy+h);ctx.stroke();}
   frame=requestAnimationFrame(draw);
  };frame=requestAnimationFrame(draw);return()=>cancelAnimationFrame(frame);
 },[]);
 return <canvas ref={canvas} className="orb" aria-hidden="true"/>;
}
