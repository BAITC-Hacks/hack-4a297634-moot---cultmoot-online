/** Streams 24 kHz PCM with a short jitter buffer. No MP3 download/decoding wait. */
export class SpeechPlayer {
  private context?: AudioContext;
  private controller?: AbortController;
  private sources = new Set<AudioBufferSourceNode>();
  private version = 0;

  // Call directly in a click handler to unlock audio on mobile browsers.
  async unlock() {
    this.context ??= new AudioContext({ latencyHint: 'interactive' });
    if (this.context.state === 'suspended') await this.context.resume();
  }

  stop() {
    this.version++;
    this.controller?.abort();
    this.controller = undefined;
    for (const node of this.sources) { node.onended = null; node.stop(); node.disconnect(); }
    this.sources.clear();
  }

  close() { this.stop(); void this.context?.close(); this.context = undefined; }

  async play(url: string, onStart: () => void, onEnd: () => void, onError: () => void) {
    this.stop();
    const version = this.version;
    const controller = new AbortController();
    this.controller = controller;
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    let finished = false;
    let started = false;
    const current = () => this.version === version;
    const ended = () => { if (current() && finished && !this.sources.size) onEnd(); };
    try {
      await this.unlock();
      if (!current()) return;
      const ctx = this.context!;
      if (ctx.state !== 'running') throw new Error('Audio permission required');
      const response = await fetch(`${url}?format=pcm`, {credentials: 'same-origin', signal: controller.signal});
      if (!response.ok || !response.body || !response.headers.get('content-type')?.startsWith('audio/pcm')) throw new Error('Speech unavailable');
      reader = response.body.getReader();
      let nextTime = ctx.currentTime + 0.12;
      let pending: Uint8Array = new Uint8Array(0);
      const schedule = (bytes: Uint8Array) => {
        const count = bytes.length / 2;
        if (!count || !current()) return;
        const buffer = ctx.createBuffer(1, count, 24000);
        const channel = buffer.getChannelData(0);
        const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        for (let i = 0; i < count; i++) channel[i] = view.getInt16(i * 2, true) / 32768;
        const node = ctx.createBufferSource();
        node.buffer = buffer; node.connect(ctx.destination); this.sources.add(node);
        node.onended = () => { node.disconnect(); this.sources.delete(node); ended(); };
        nextTime = Math.max(nextTime, ctx.currentTime + 0.04);
        node.start(nextTime); nextTime += buffer.duration;
        if (!started) { started = true; onStart(); }
      };
      while (current()) {
        while (nextTime > ctx.currentTime + 1.5 && current()) await new Promise(r => setTimeout(r, 25));
        if (!current()) return;
        const {value, done} = await reader.read();
        if (!current()) return;
        if (done) break;
        const combined = new Uint8Array(pending.length + value.length);
        combined.set(pending); combined.set(value, pending.length);
        const available = combined.length - combined.length % 2;
        if (available >= 5760) { schedule(combined.subarray(0, available)); pending = combined.slice(available); }
        else pending = combined;
      }
      if (!current()) return;
      if (pending.length % 2) throw new Error('Truncated PCM stream');
      schedule(pending);
      if (!started) throw new Error('Empty speech stream');
      finished = true; ended();
    } catch {
      if (current()) { this.stop(); onError(); }
    } finally {
      try { await reader?.cancel(); } catch { /* Connection already closed. */ }
    }
  }
}
