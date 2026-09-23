class PCMProcessor extends AudioWorkletProcessor {
  constructor(){super();this.frames=[];this.length=0;}
  process(inputs){
    const channel=inputs[0]?.[0];if(!channel)return true;
    const copy=new Float32Array(channel);this.frames.push(copy);this.length+=copy.length;
    if(this.length>=2400){
      const pcm=new Int16Array(this.length);let offset=0,sum=0;
      for(const frame of this.frames)for(const x of frame){const sample=Math.max(-1,Math.min(1,x));pcm[offset++]=sample<0?sample*32768:sample*32767;sum+=x*x;}
      this.port.postMessage({buffer:pcm.buffer,rms:Math.sqrt(sum/pcm.length)},[pcm.buffer]);this.frames=[];this.length=0;
    }
    return true;
  }
}
registerProcessor('pcm-capture',PCMProcessor);
