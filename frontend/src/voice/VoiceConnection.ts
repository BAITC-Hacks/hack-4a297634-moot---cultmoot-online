export class VoiceConnection{
  private socket?:WebSocket;private stream?:MediaStream;private context?:AudioContext;private source?:MediaStreamAudioSourceNode;private node?:AudioWorkletNode;
  private stopped=false;
  async start(onEvent:(event:any)=>void,onLevel:(level:number)=>void,onBarge:()=>void,language='auto',pause='auto'){
    try{
      this.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
      if(this.stopped){this.stream.getTracks().forEach(t=>t.stop());return;}
      this.context=new AudioContext();
      await this.context.resume();
      await this.context.audioWorklet.addModule('/pcm-worklet.js');
      this.socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/voice?language=${encodeURIComponent(language)}&pause=${encodeURIComponent(pause)}`);this.socket.binaryType='arraybuffer';
      await new Promise<void>((resolve,reject)=>{
        const timeout=window.setTimeout(()=>reject(new Error('Voice connection timed out')),20000);
        this.socket!.onmessage=e=>{const event=JSON.parse(e.data);onEvent(event);if(event.type==='ready'){window.clearTimeout(timeout);resolve();}if(event.type==='error'){window.clearTimeout(timeout);reject(new Error(event.message));}};
        this.socket!.onclose=()=>{window.clearTimeout(timeout);reject(new Error('Голосовое соединение закрыто. Попробуйте снова.'));};
        this.socket!.onerror=()=>{window.clearTimeout(timeout);reject(new Error('Voice connection failed'));};
      });
      this.socket.onmessage=e=>{try{onEvent(JSON.parse(e.data));}catch{onEvent({type:'error',message:'Invalid voice event'});}};
      this.socket.onclose=()=>{this.stop();onEvent({type:'closed'});};
      this.source=this.context.createMediaStreamSource(this.stream);
      this.node=new AudioWorkletNode(this.context,'pcm-capture');
      this.node.port.onmessage=({data})=>{
        onLevel(Math.min(1,data.rms*12));
        // Server VAD controls interruption; local volume spikes must not cut off speech.
        if(this.socket?.readyState===WebSocket.OPEN){
          if(this.socket.bufferedAmount>240000){this.stop();onEvent({type:'error',message:'Network cannot keep up with audio'});return;}
          this.socket.send(data.buffer);
        }
      };
      this.source.connect(this.node);
      // A zero-gain sink keeps the worklet running without playing microphone audio back.
      const mute=this.context.createGain();mute.gain.value=0;this.node.connect(mute);mute.connect(this.context.destination);
      await this.context.resume();
    }catch(error){this.stop();throw error;}
  }
  stop(){
    this.stopped=true;
    if(this.socket){this.socket.onclose=null;this.socket.close();this.socket=undefined;}
    this.node?.disconnect();this.source?.disconnect();this.stream?.getTracks().forEach(t=>t.stop());
    this.context?.close();this.context=undefined;
  }
}
