"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

/**
 * The face of a voice call: a soft, grainy gradient sphere. Idle, it drifts slowly. While the guest
 * talks it stirs a little. While the agent thinks it shimmers. While the agent speaks, waves travel
 * inward through it, in time with the real voice level read from the audio track.
 *
 * It is a single WebGL shader, redrawn every frame straight to the canvas (React never re-renders per
 * frame). Without WebGL it falls back to a pulsing CSS gradient circle.
 */

export type OrbState = "connecting" | "idle" | "listening" | "thinking" | "speaking";

const ORB_STATES: Record<string, OrbState> = { listening: "listening", thinking: "thinking", speaking: "speaking", idle: "idle" };

/** LiveKit's agent state ("connecting", "initializing", "speaking"...) as one of the orb's states. */
export function orbStateFor(agentState: string): OrbState {
  return ORB_STATES[agentState] ?? "connecting";
}

const VERTEX = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAGMENT = `
precision highp float;
uniform vec2 uRes;
uniform float uTime;
uniform float uFlow;     // how far the colour clouds have drifted (accumulated, so changing speed never makes it jump)
uniform float uGrain;    // how far the grain has flowed, in grain cells (barely moves at rest)
uniform float uGrainCell; // size of one grain, in device pixels
uniform float uEnergy;   // overall activity, ~0.1 idle to ~1.8 loud speech
uniform float uLevel;    // voice level while the agent speaks; drives the inward waves
uniform float uThink;    // 0..1 shimmer while thinking
uniform vec3 uAccent;    // the restaurant's colour, blended into the warm tones

float hash(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}
float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 3; i++) { v += a * noise(p); p = p * 1.9 + vec2(17.3, 9.1); a *= 0.45; }
  return v;
}

void main() {
  float size = min(uRes.x, uRes.y);
  vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / (0.5 * size);
  float R = 0.97;
  float aa = 2.0 / size;
  float alpha = 1.0 - smoothstep(R - aa * 2.0, R, length(uv));
  if (alpha <= 0.0) { gl_FragColor = vec4(0.0); return; }

  vec2 p = uv / R;                                   // the unit disc
  float z = sqrt(max(0.0, 1.0 - dot(p, p)));         // a sphere's height at this point
  vec3 n = vec3(p, z);

  // A slowly turning, domain-warped noise field: the soft colour clouds. More energy = faster, more warped.
  float t = uFlow;
  float warp = 1.5 + 0.3 * uEnergy;
  vec2 q = vec2(fbm(p * 0.9 + vec2(0.0, t)), fbm(p * 0.9 + vec2(5.2, 1.3) - t));
  vec2 w = vec2(fbm(p * 1.0 + warp * q + vec2(1.7, 9.2) + 0.6 * t), fbm(p * 1.0 + warp * q + vec2(8.3, 2.8) - 0.5 * t));
  float f = fbm(p * 0.95 + warp * 1.3 * w);

  // Waves that travel inward (the phase grows with time, so the crests move toward the centre).
  float radius = length(p + 0.28 * (w - 0.5));                       // wobble the rings so they aren't perfect circles
  float ring = sin(radius * 7.0 + uTime * 2.6 - f * 2.4);
  float field = f + uThink * 0.06 * sin(uTime * 2.2 + f * 6.0);

  vec3 dark  = vec3(0.19, 0.17, 0.18);
  vec3 brown = vec3(0.42, 0.27, 0.26);
  vec3 coral = mix(vec3(0.86, 0.50, 0.42), uAccent, 0.3);
  vec3 lilac = vec3(0.68, 0.66, 0.98);
  vec3 white = vec3(0.99, 0.92, 0.95);

  // Mostly a dark, mauve-brown body; coral glows where the cloud field peaks, more so toward the left.
  float a = 2.45 + 0.4 * sin(uTime * 0.12);   // the light drifts slowly
  vec2 lightDir = vec2(cos(a), sin(a));
  float g = dot(p, lightDir) * 0.5 + 0.5;
  // The waves ripple the brightness gently, instead of being amplified into hard colour bands.
  float s = clamp(0.7 * g + 1.6 * (field - 0.5) + 0.38 + ring * uLevel * 0.09, 0.0, 1.0);
  vec3 col = mix(dark, brown, smoothstep(0.12, 0.5, s));
  col = mix(col, coral, smoothstep(0.42, 0.82, s) * 0.95);
  float leftGlow = smoothstep(-0.1, 1.0, dot(p, normalize(vec2(-0.85, -0.3))) * 0.9 + 0.1);
  col = mix(col, coral, leftGlow * 0.5 * (0.55 + 0.9 * field));

  // A cool lilac fringe on the left and bottom edges, and a pale glow on the top-left limb.
  float limb = pow(1.0 - z, 1.7);
  float coolSide = smoothstep(-0.2, 0.9, -p.x * 0.65 - p.y * 0.45 + 0.25);
  col = mix(col, lilac, limb * coolSide * (0.85 + 0.25 * field));
  float glow = smoothstep(0.35, 1.0, dot(normalize(p + 1e-4), normalize(vec2(-0.62, 0.78)))) * pow(1.0 - z, 1.1);
  col = mix(col, white, glow * 0.85);
  col *= 0.92 + 0.08 * z;

  // Film grain: a fixed speckle texture that drifts. At rest it barely moves; while the agent speaks
  // it flows inward with the waves (each grain slides toward the centre).
  vec2 gc = gl_FragCoord.xy - 0.5 * uRes;
  vec2 gdir = gc / (length(gc) + 0.001);
  vec2 gp = gc / uGrainCell + gdir * uGrain + vec2(0.35, -0.2) * uGrain;
  col += (hash(floor(gp)) - 0.5) * 0.14;

  gl_FragColor = vec4(col * alpha, alpha);           // premultiplied alpha
}
`;

const FALLBACK_BACKGROUND =
  "radial-gradient(circle at 30% 28%, #fbeef0 0%, #e58a74 24%, #6a4440 58%, #2e2b2c 100%)";

function parseHex(color: string): [number, number, number] | null {
  const m = /^#([0-9a-f]{6})$/i.exec(color.trim());
  if (!m) return null;
  const v = parseInt(m[1], 16);
  return [((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255];
}

/** The loudness (0..1) of an audio track, read straight from a Web Audio analyser each time it is asked. */
class LevelMeter {
  private analyser: AnalyserNode;
  private buffer: Uint8Array<ArrayBuffer>;
  private source: MediaStreamAudioSourceNode;

  constructor(context: AudioContext, track: MediaStreamTrack) {
    this.source = context.createMediaStreamSource(new MediaStream([track]));
    this.analyser = context.createAnalyser();
    this.analyser.fftSize = 512;
    this.buffer = new Uint8Array(new ArrayBuffer(this.analyser.fftSize));
    this.source.connect(this.analyser); // not connected onward: it listens, it never plays
  }

  read(): number {
    this.analyser.getByteTimeDomainData(this.buffer);
    let sum = 0;
    for (let i = 0; i < this.buffer.length; i++) {
      const v = (this.buffer[i] - 128) / 128;
      sum += v * v;
    }
    return Math.min(1, Math.sqrt(sum / this.buffer.length) * 4);
  }

  close() {
    this.source.disconnect();
    this.analyser.disconnect();
  }
}

export function AgentOrb({
  state,
  agentTrack,
  userTrack,
  className,
}: {
  state: OrbState;
  /** The agent's voice, to move the waves with it. */
  agentTrack?: MediaStreamTrack | null;
  /** The guest's microphone, so the orb stirs a little while they talk. */
  userTrack?: MediaStreamTrack | null;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fallbackRef = useRef<HTMLDivElement>(null);
  // Read by the draw loop every frame; updating them never re-renders anything.
  const stateRef = useRef<OrbState>(state);
  const metersRef = useRef<{ agent: LevelMeter | null; user: LevelMeter | null }>({ agent: null, user: null });
  const contextRef = useRef<AudioContext | null>(null);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  // Listen to the two audio tracks.
  useEffect(() => {
    const meters = metersRef.current;
    if (!agentTrack && !userTrack) return;
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const context = contextRef.current ?? new Ctx();
    contextRef.current = context;
    void context.resume().catch(() => {});
    meters.agent = agentTrack ? new LevelMeter(context, agentTrack) : null;
    meters.user = userTrack ? new LevelMeter(context, userTrack) : null;
    return () => {
      meters.agent?.close();
      meters.user?.close();
      meters.agent = meters.user = null;
    };
  }, [agentTrack, userTrack]);

  useEffect(() => () => void contextRef.current?.close().catch(() => {}), []);

  // The draw loop.
  useEffect(() => {
    const canvas = canvasRef.current;
    const fallback = fallbackRef.current;
    if (!canvas || !fallback) return;

    const gl = canvas.getContext("webgl", { alpha: true, premultipliedAlpha: true, antialias: false });
    if (!gl) {
      canvas.style.display = "none";
      fallback.style.display = "block";
      return;
    }

    const compile = (type: number, source: string) => {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (gl.getShaderParameter(shader, gl.COMPILE_STATUS)) return shader;
      console.warn("AgentOrb: shader failed to compile, showing the fallback.", gl.getShaderInfoLog(shader));
      return null;
    };
    const vertex = compile(gl.VERTEX_SHADER, VERTEX);
    const fragment = compile(gl.FRAGMENT_SHADER, FRAGMENT);
    const program = gl.createProgram();
    if (!vertex || !fragment || !program) {
      canvas.style.display = "none";
      fallback.style.display = "block";
      return;
    }
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    gl.useProgram(program);

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, "aPos");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

    const uniform = (name: string) => gl.getUniformLocation(program, name);
    const uRes = uniform("uRes");
    const uTime = uniform("uTime");
    const uFlow = uniform("uFlow");
    const uGrain = uniform("uGrain");
    const uGrainCell = uniform("uGrainCell");
    const uEnergy = uniform("uEnergy");
    const uLevel = uniform("uLevel");
    const uThink = uniform("uThink");
    const uAccent = uniform("uAccent");

    // The restaurant's accent colour (set as --primary on its page) tints the warm tones.
    const accent = parseHex(getComputedStyle(canvas).getPropertyValue("--primary")) ?? [0.89, 0.52, 0.42];
    gl.uniform3f(uAccent, accent[0], accent[1], accent[2]);

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let energy = 0.15;
    let level = 0;
    let think = 0;
    let agentLevel = 0;
    let userLevel = 0;
    let speak = 0; // 0..1, how much the agent is speaking right now (smoothed)
    let flow = 0;
    let grain = 0;
    let frame = 0;
    let last = performance.now();
    let clock = Math.random() * 50; // different orbs don't start in the same pose

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, Math.round(canvas.clientWidth * dpr));
      const height = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      gl.viewport(0, 0, canvas.width, canvas.height);
    };

    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      resize();

      const meters = metersRef.current;
      const rawAgent = meters.agent ? meters.agent.read() : 0;
      const rawUser = meters.user ? meters.user.read() : 0;
      // Smoothed both ways, so the waves follow syllables without flickering.
      agentLevel += (rawAgent - agentLevel) * (rawAgent > agentLevel ? 0.22 : 0.07);
      userLevel += (rawUser - userLevel) * (rawUser > userLevel ? 0.18 : 0.06);

      const current = stateRef.current;
      let targetEnergy = 0.15;
      let targetLevel = 0;
      if (current === "connecting") targetEnergy = 0.2;
      if (current === "listening") targetEnergy = 0.2 + userLevel * 0.4;
      if (current === "thinking") targetEnergy = 0.55;
      if (current === "speaking") {
        targetEnergy = 0.4 + agentLevel * 0.8;
        targetLevel = Math.min(1, 0.3 + agentLevel * 1.2);
      }
      if (reduceMotion) {
        targetEnergy *= 0.3;
        targetLevel *= 0.3;
      }
      energy += (targetEnergy - energy) * Math.min(1, dt * 2.5);
      level += (targetLevel - level) * Math.min(1, dt * 4);
      think += ((current === "thinking" ? 1 : 0) - think) * Math.min(1, dt * 2);
      speak += ((current === "speaking" ? 1 : 0) - speak) * Math.min(1, dt * 3);
      const calm = reduceMotion ? 0.3 : 1;
      clock += dt * calm;
      // Motion is accumulated, so a change of speed only makes it faster or slower, never a jump.
      // At rest everything drifts very slowly; speaking adds flow, following the voice a little.
      flow += dt * calm * (0.04 + 0.05 * think + speak * (0.07 + 0.12 * agentLevel));
      grain += dt * calm * (0.12 + speak * (4 + 8 * agentLevel));

      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform1f(uTime, clock);
      gl.uniform1f(uFlow, flow);
      gl.uniform1f(uGrain, grain);
      gl.uniform1f(uGrainCell, Math.max(1, 1.5 * Math.min(window.devicePixelRatio || 1, 2)));
      gl.uniform1f(uEnergy, energy);
      gl.uniform1f(uLevel, level);
      gl.uniform1f(uThink, think);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(frame);
      // Release what this run created, but leave the context itself alone: React (in development) mounts
      // an effect twice on the same canvas, and a context that was force-lost can't be used again.
      gl.deleteProgram(program);
      gl.deleteShader(vertex);
      gl.deleteShader(fragment);
      gl.deleteBuffer(buffer);
    };
  }, []);

  return (
    <div className={cn("relative aspect-square", className)} role="img" aria-label={`Voice assistant, ${state}`}>
      <canvas ref={canvasRef} className="size-full" />
      <div
        ref={fallbackRef}
        className="absolute inset-0 hidden rounded-full"
        style={{ background: FALLBACK_BACKGROUND }}
      />
    </div>
  );
}
