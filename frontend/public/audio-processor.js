/**
 * AudioWorklet processor — runs in a dedicated audio thread.
 *
 * Receives raw Float32 PCM from the microphone, converts each frame to
 * Int16 (what faster-whisper expects), and posts the buffer to the main
 * thread via the port so it can be sent over the WebSocket.
 *
 * Registered as: 'audio-processor'
 */
class AudioProcessor extends AudioWorkletProcessor {
  /**
   * Called by the browser for every audio render quantum (128 frames by default).
   *
   * @param {Float32Array[][]} inputs  - [[channel0_samples], ...]
   * @returns {boolean} true = keep processor alive
   */
  process(inputs) {
    // inputs[0] = first input, [0] = first (mono) channel
    const channelData = inputs[0]?.[0];
    if (!channelData || channelData.length === 0) return true;

    // Convert Float32 [-1.0, 1.0] → Int16 [-32768, 32767]
    const int16 = new Int16Array(channelData.length);
    for (let i = 0; i < channelData.length; i++) {
      const clamped = Math.max(-1, Math.min(1, channelData[i]));
      int16[i] = clamped < 0 ? clamped * 32768 : clamped * 32767;
    }

    // Transfer ownership of the underlying ArrayBuffer (zero-copy)
    this.port.postMessage(int16.buffer, [int16.buffer]);
    return true;
  }
}

registerProcessor('audio-processor', AudioProcessor);
