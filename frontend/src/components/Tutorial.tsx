import React,{useEffect,useRef} from 'react';
import {Tutorial as Guide} from '../api/client';

export function Tutorial({guide,onStep,onClose,busy}:{guide:Guide;onStep:(n:number)=>void;onClose:()=>void;busy:boolean}){
 const ref=useRef<HTMLDialogElement>(null),step=guide.steps[guide.index];
 const en=guide.language==='en',kk=guide.language==='kk';
 const label=(ru:string,kz:string,english:string)=>en?english:kk?kz:ru;
 useEffect(()=>{const dialog=ref.current;dialog?.showModal();return()=>dialog?.close();},[]);
 return <dialog className="tutorial" ref={ref} onCancel={e=>{e.preventDefault();if(!busy)onClose();}} aria-labelledby="tutorial-title">
  <div className="tutorial-head"><div><span className="eyebrow">{label('ПОШАГОВАЯ ПОМОЩЬ','ҚАДАМДЫҚ КӨМЕК','STEP-BY-STEP GUIDE')}</span><h2 id="tutorial-title">{guide.title}</h2></div><button disabled={busy} onClick={onClose} aria-label={label('Закрыть','Жабу','Close')}>×</button></div>
  <div className="tutorial-content"><div className="phone-preview" aria-label={label('Схема интерфейса','Интерфейс үлгісі','Illustrative interface')}><div className="phone-notch"/><b>Halyk Voice</b><small>{label('Схема приложения','Қосымша үлгісі','App illustration')}</small><div className="demo-card">{label('Навигация','Навигация','Navigation')}<small>{label('Выберите нужный раздел','Қажетті бөлімді таңдаңыз','Choose a section')}</small></div><div className="phone-rows">{guide.steps.map((s,i)=><button key={i} disabled={busy} className={i===guide.index?'highlight':''} onClick={()=>onStep(i)}><span>{i===guide.index?'☞':'○'}</span>{s.target}</button>)}</div></div>
  <div className="tutorial-copy" key={guide.index}><span className="step-counter">{guide.index+1} / {guide.steps.length}</span><h3>{step.title}</h3><p>{step.text}</p><button className="text-button" disabled={busy} onClick={()=>onStep(guide.index)}>♫ {label('Повторить озвучивание','Қайта тыңдау','Play again')}</button><p className="auth-note">{label('Это схема, а не экран вашего банка. Названия и расположение кнопок могут отличаться.','Бұл банк экраны емес, үлгі. Түймелердің атауы мен орналасуы өзгеше болуы мүмкін.','This is an illustration, not your banking screen. Labels and positions may differ.')}</p>{guide.source&&<a href={guide.source} target="_blank" rel="noreferrer">{label('Инструкция Halyk','Halyk нұсқаулығы','Halyk instructions')} ↗</a>}</div></div>
  <div className="tutorial-controls"><button disabled={busy||guide.index===0} onClick={()=>onStep(guide.index-1)}>← {label('Назад','Артқа','Back')}</button><div className="dots">{guide.steps.map((_,i)=><button key={i} className={i===guide.index?'active':''} aria-label={`${label('Шаг','Қадам','Step')} ${i+1}`} disabled={busy} onClick={()=>onStep(i)}/>)}</div><button className="primary" disabled={busy} onClick={()=>guide.index===guide.steps.length-1?onClose():onStep(guide.index+1)}>{guide.index===guide.steps.length-1?label('Готово','Дайын','Done'):label('Далее →','Келесі →','Next →')}</button></div>
 </dialog>;
}
