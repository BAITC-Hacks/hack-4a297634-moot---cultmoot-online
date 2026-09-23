export class VoiceConnection{
  private socket?:WebSocket;private stream?:MediaStream;private context?:AudioContext;private source?:MediaStreamAudioSourceNode;private node?:AudioWorkletNode;
  private stopped=false;
  private cancelConnect?:()=>void;
  async start(onEvent:(event:any)=>void,onLevel:(level:number)=>void,language='auto',pause='auto'){
    try{
      if(!navigator.mediaDevices?.getUserMedia)throw new Error('Микрофон доступен через HTTPS или localhost.');
      this.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
      if(this.stopped){this.stream.getTracks().forEach(t=>t.stop());return;}
      this.context=new AudioContext();
      await this.context.resume();
      if(this.stopped)return;
      await this.context.audioWorklet.addModule('/pcm-worklet.js');
      if(this.stopped)return;
      this.socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/voice?language=${encodeURIComponent(language)}&pause=${encodeURIComponent(pause)}`);this.socket.binaryType='arraybuffer';
      await new Promise<void>((resolve,reject)=>{
        const timeout=window.setTimeout(()=>reject(new Error('Voice connection timed out')),20000);
        this.cancelConnect=()=>{window.clearTimeout(timeout);reject(new Error('Connection cancelled'));};
        this.socket!.onmessage=e=>{try{const event=JSON.parse(e.data);onEvent(event);if(event.type==='ready'){window.clearTimeout(timeout);resolve();}if(event.type==='error'){window.clearTimeout(timeout);reject(new Error(event.message));}}catch{window.clearTimeout(timeout);reject(new Error('Invalid voice event'));}};
        this.socket!.onclose=()=>{window.clearTimeout(timeout);reject(new Error('Голосовое соединение закрыто. Попробуйте снова.'));};
        this.socket!.onerror=()=>{window.clearTimeout(timeout);reject(new Error('Voice connection failed'));};
      });
      this.cancelConnect=undefined;
      if(this.stopped)return;
      this.socket.onmessage=e=>{try{onEvent(JSON.parse(e.data));}catch{onEvent({type:'error',message:'Invalid voice event'});}};
      this.socket.onclose=()=>{this.stop();onEvent({type:'closed'});};
      this.socket.onerror=()=>{this.stop();onEvent({type:'error',message:'Голосовая связь потеряна. Подключите микрофон снова.'});onEvent({type:'closed'});};
      this.stream.getAudioTracks().forEach(track=>{track.onended=()=>{this.stop();onEvent({type:'closed'});};});
      this.source=this.context.createMediaStreamSource(this.stream);
      this.node=new AudioWorkletNode(this.context,'pcm-capture');
      this.node.port.onmessage=({data})=>{
        onLevel(Math.min(1,data.rms*12));
        // Server VAD controls interruption; local volume spikes must not cut off speech.
        if(this.socket?.readyState===WebSocket.OPEN){
          if(this.socket.bufferedAmount>240000){this.stop();onEvent({type:'error',message:'Соединение слишком медленное для голоса. Используйте текст или подключите микрофон снова.'});onEvent({type:'closed'});return;}
          this.socket.send(data.buffer);
        }
      };
      this.source.connect(this.node);
      // A zero-gain sink keeps the worklet running without playing microphone audio back.
      const mute=this.context.createGain();mute.gain.value=0;this.node.connect(mute);mute.connect(this.context.destination);
      await this.context.resume();
    }catch(error){this.stop();if(error instanceof DOMException&&error.name==='NotAllowedError')throw new Error('Разрешите доступ к микрофону в настройках браузера.');if(error instanceof DOMException&&error.name==='NotFoundError')throw new Error('Микрофон не найден. Подключите его или напишите вопрос.');throw error;}
  }
  stop(){
    this.stopped=true;
    this.cancelConnect?.();this.cancelConnect=undefined;
    if(this.socket){this.socket.onclose=null;this.socket.onmessage=null;this.socket.onerror=null;this.socket.close();this.socket=undefined;}
    if(this.node)this.node.port.onmessage=null;
    this.node?.disconnect();this.source?.disconnect();this.stream?.getTracks().forEach(t=>t.stop());
    this.context?.close();this.context=undefined;
  }
}
