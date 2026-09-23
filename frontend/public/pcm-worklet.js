class PCMProcessor extends AudioWorkletProcessor {
  constructor(){super();this.pending=[];this.position=0;this.output=[];this.ratio=sampleRate/24000;}
  process(inputs){
    const input=inputs[0]?.[0];if(!input)return true;
    for(const value of input)this.pending.push(value);
    while(this.position+1<this.pending.length){
      const i=Math.floor(this.position),f=this.position-i;
      this.output.push(this.pending[i]*(1-f)+this.pending[i+1]*f);this.position+=this.ratio;
    }
    const used=Math.floor(this.position);this.pending.splice(0,used);this.position-=used;
    while(this.output.length>=1200){
      const frame=this.output.splice(0,1200),pcm=new Int16Array(1200);let sum=0;
      frame.forEach((x,i)=>{x=Math.max(-1,Math.min(1,x));pcm[i]=x<0?x*32768:x*32767;sum+=x*x;});
      this.port.postMessage({buffer:pcm.buffer,rms:Math.sqrt(sum/1200)},[pcm.buffer]);
    }
    return true;
  }
}
registerProcessor('pcm-capture',PCMProcessor);
