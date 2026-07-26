import { onUnmounted, ref, watch } from "vue";

export type TradingSound = "click" | "accepted" | "filled" | "cancelled" | "rejected" | "offline";

const ENABLED_KEY = "pxy.orderflow.sound.enabled";
const VOLUME_KEY = "pxy.orderflow.sound.volume";

function readBoolean(key: string, fallback: boolean): boolean {
  try {
    const value = window.localStorage.getItem(key);
    return value === null ? fallback : value === "true";
  } catch {
    return fallback;
  }
}

function readVolume(): number {
  try {
    const value = Number(window.localStorage.getItem(VOLUME_KEY));
    return Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0.35;
  } catch {
    return 0.35;
  }
}

export function useTradingSounds() {
  const enabled = ref(readBoolean(ENABLED_KEY, false));
  const volume = ref(readVolume());
  const unlocked = ref(false);
  let context: AudioContext | null = null;

  function getContext(): AudioContext | null {
    if (typeof window === "undefined") return null;
    const AudioCtor = window.AudioContext || (window as Window & {
      webkitAudioContext?: typeof AudioContext;
    }).webkitAudioContext;
    if (!AudioCtor) return null;
    context ||= new AudioCtor();
    return context;
  }

  async function unlock(): Promise<boolean> {
    const audio = getContext();
    if (!audio) return false;
    try {
      if (audio.state !== "running") await audio.resume();
      unlocked.value = audio.state === "running";
      return unlocked.value;
    } catch {
      unlocked.value = false;
      return false;
    }
  }

  function tone(audio: AudioContext, at: number, frequency: number, duration: number, gain: number, type: OscillatorType = "sine"): void {
    const oscillator = audio.createOscillator();
    const envelope = audio.createGain();
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(frequency, at);
    envelope.gain.setValueAtTime(0.0001, at);
    envelope.gain.exponentialRampToValueAtTime(Math.max(0.0001, gain), at + 0.008);
    envelope.gain.exponentialRampToValueAtTime(0.0001, at + duration);
    oscillator.connect(envelope).connect(audio.destination);
    oscillator.start(at);
    oscillator.stop(at + duration + 0.02);
  }

  function play(sound: TradingSound): void {
    if (!enabled.value || !unlocked.value) return;
    const audio = getContext();
    if (!audio || audio.state !== "running") return;
    const at = audio.currentTime + 0.012;
    const gain = Math.max(0.0001, volume.value * 0.085);
    if (sound === "click") {
      tone(audio, at, 620, 0.045, gain * 0.55, "square");
    } else if (sound === "accepted") {
      tone(audio, at, 520, 0.07, gain, "triangle");
      tone(audio, at + 0.075, 780, 0.09, gain * 0.85, "triangle");
    } else if (sound === "filled") {
      tone(audio, at, 660, 0.06, gain, "sine");
      tone(audio, at + 0.065, 880, 0.075, gain, "sine");
      tone(audio, at + 0.145, 1180, 0.11, gain * 0.8, "sine");
    } else if (sound === "cancelled") {
      tone(audio, at, 470, 0.07, gain * 0.85, "triangle");
      tone(audio, at + 0.075, 320, 0.09, gain * 0.7, "triangle");
    } else if (sound === "rejected") {
      tone(audio, at, 220, 0.11, gain, "sawtooth");
      tone(audio, at + 0.1, 165, 0.14, gain * 0.75, "sawtooth");
    } else {
      tone(audio, at, 280, 0.14, gain * 0.75, "square");
      tone(audio, at + 0.18, 220, 0.18, gain * 0.55, "square");
    }
  }

  watch(enabled, (value) => {
    try { window.localStorage.setItem(ENABLED_KEY, String(value)); } catch { /* storage is optional */ }
  });
  watch(volume, (value) => {
    try { window.localStorage.setItem(VOLUME_KEY, String(value)); } catch { /* storage is optional */ }
  });
  onUnmounted(() => { void context?.close(); context = null; });

  return { enabled, volume, unlocked, unlock, play };
}
