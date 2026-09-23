import React from 'react';
import {createRoot} from 'react-dom/client';
import Platform from './Platform';
class Boundary extends React.Component<{children:React.ReactNode},{failed:boolean}>{
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true};}
 render(){return this.state.failed?<div className="startup"><h1>Halyk Voice</h1><p>Не удалось отобразить страницу. Обновите её и повторите.</p><button className="primary" onClick={()=>location.reload()}>Обновить</button></div>:this.props.children;}
}
createRoot(document.getElementById('root')!).render(<Boundary><Platform/></Boundary>);
