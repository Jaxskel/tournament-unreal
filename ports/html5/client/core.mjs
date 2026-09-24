import { BINDINGS } from './bindings.mjs';

export const DEFAULT_ARGUMENTS = ['/Game/RestrictedAssets/Maps/WIP/DM-DeckTest?Game=/Script/TournamentBridge.TournamentDeathmatch?Mutator=TournamentBridge.TournamentBridgeMutator?BotFill=7?MaxPlayers=7?LAN=1?RequireReady=0?MaxPlayerWait=3?Difficulty=3'];
export const RESOLUTIONS = Object.freeze({ '1080p': [1920, 1080], '1440p': [2560, 1440] });
export const STORAGE_KEY = 'tournament.local-ut4.resolution';
export const MODE_STORAGE_KEY = 'tournament.local-ut4.mode';
export const resolutionKey = value => Object.hasOwn(RESOLUTIONS, value) ? value : '1080p';
export function readMode(storage) {
  try { return storage.getItem(MODE_STORAGE_KEY) === 'multiplayer' ? 'multiplayer' : 'practice'; }
  catch { return 'practice'; }
}
export function argumentsForMode(manifest, mode) {
  if (mode === 'practice') return manifest.arguments;
  if (mode !== 'multiplayer') throw new Error('Unknown launch mode.');
  if (!manifest.multiplayerArguments?.length) throw new Error('Multiplayer unavailable: the operator has not configured multiplayerArguments in runtime.json. Stop to choose Practice.');
  return manifest.multiplayerArguments;
}

export function readResolution(storage) {
  try { return resolutionKey(storage.getItem(STORAGE_KEY)); } catch { return '1080p'; }
}

export function engineArguments(base, resolution) {
  const [width, height] = RESOLUTIONS[resolutionKey(resolution)];
  // Exactly one resolution request. No automatic window/devicePixelRatio sizing.
  return [...base.filter(arg => !/^-?(?:ResX|ResY|ForceRes|Windowed|Fullscreen)(?:=|$)/i.test(arg)),
    '-ResX=' + width, '-ResY=' + height, '-ForceRes', '-Windowed'];
}

export function fit16by9(width, height) {
  const w = Math.max(0, Math.min(width, height * 16 / 9));
  return { width: w, height: w * 9 / 16 };
}

export function validateGraphicsLimits({ fragment, vertex, combined }) {
  if (![fragment, vertex, combined].every(Number.isFinite) || fragment < 16 || vertex < 8 || combined < 24) {
    throw new Error(`Unsupported GPU/WebGL limits: ${fragment} fragment, ${vertex} vertex, ${combined} combined texture slots. This experimental UT4 build requires at least 16 fragment, 8 vertex and 24 combined slots. Try a browser/GPU exposing these limits.`);
  }
  return { fragment, vertex, combined };
}

export function validateManifest(raw, manifestURL) {
  const fail = message => { throw new Error('runtime.json: ' + message); };
  const origin = new URL(manifestURL).origin;
  if (!raw || raw.version !== 1) fail('version must be 1.');
  if (!['asmjs', 'wasm'].includes(raw.format)) fail('format must be asmjs or wasm.');
  if (!raw.files || Array.isArray(raw.files) || typeof raw.files !== 'object') fail('files must be a name-to-URL object.');
  const files = Object.create(null);
  for (const [name, path] of Object.entries(raw.files)) {
    if (!name || typeof path !== 'string' || !path) fail('file names and URLs must be nonempty strings.');
    const url = new URL(path, manifestURL);
    if (!['http:', 'https:'].includes(url.protocol) || url.origin !== origin || url.username || url.password || url.hash) {
      fail('all files must use the manifest origin, without credentials or fragments.');
    }
    files[name] = url.href;
  }
  const requireFile = key => {
    if (typeof key !== 'string' || !Object.hasOwn(files, key)) fail('missing file entry: ' + String(key));
    return key;
  };
  const scriptList = value => {
    if (!Array.isArray(value)) fail('script lists must be arrays.');
    return value.map(requireFile);
  };
  const engine = requireFile(raw.engine);
  const supportScripts = scriptList(raw.supportScripts ?? []);
  const dataScripts = scriptList(raw.dataScripts ?? []);
  const scripts = [...supportScripts, ...dataScripts, engine];
  if (new Set(scripts).size !== scripts.length) fail('scripts must not repeat.');
  const memoryInitializer = raw.memoryInitializer == null ? null : requireFile(raw.memoryInitializer);
  const wasmBinary = raw.wasmBinary == null ? null : requireFile(raw.wasmBinary);
  const wasmModule = raw.wasmModule == null ? null : requireFile(raw.wasmModule);
  if (raw.format === 'wasm' && !wasmBinary && !wasmModule) fail('wasm requires wasmModule (converted legacy) or wasmBinary.');
  if (wasmBinary && wasmModule) fail('choose either wasmModule or wasmBinary.');
  if (raw.format === 'asmjs' && (wasmBinary || wasmModule)) fail('asmjs must not specify WASM assets.');
  const packageFiles = raw.packageFiles === undefined ? [] : raw.packageFiles;
  if (!Array.isArray(packageFiles) || new Set(packageFiles).size !== packageFiles.length) fail('packageFiles must be an array of unique file names.');
  const bootstrapURLs = new Set([...scripts, memoryInitializer, wasmBinary, wasmModule].filter(Boolean).map(name => files[name]));
  for (const name of packageFiles) {
    requireFile(name);
    if (bootstrapURLs.has(files[name])) fail('packageFiles cannot name scripts, memory initializers or WASM assets (including URL aliases).');
  }
  if (packageFiles.length && !dataScripts.length) fail('packageFiles requires a data script to consume the package.');
  if (new Set(packageFiles.map(name => files[name])).size !== packageFiles.length) fail('packageFiles URLs must be unique.');
  const argumentList = (value, name) => {
    if (!Array.isArray(value) || !value.every(arg => typeof arg === 'string' && !arg.includes('\0'))) fail(name + ' must be an array of strings without NUL characters.');
    return [...value];
  };
  const args = argumentList(raw.arguments ?? DEFAULT_ARGUMENTS, 'arguments');
  const multiplayerArguments = raw.multiplayerArguments === undefined ? null : argumentList(raw.multiplayerArguments, 'multiplayerArguments');
  const totalMemory = raw.totalMemory;
  if (totalMemory != null && (!Number.isSafeInteger(totalMemory) || totalMemory < 16777216 || totalMemory % 65536)) {
    fail('totalMemory must be at least 16 MiB and a multiple of 65536.');
  }
  let websocket;
  try { websocket = new URL(raw.websocketUrl); } catch { fail('websocketUrl must be an absolute ws:// or wss:// URL.'); }
  if (!['ws:', 'wss:'].includes(websocket.protocol) || websocket.username || websocket.password || websocket.hash || websocket.search) fail('invalid game-packet WebSocket URL.');
  if (new URL(manifestURL).protocol === 'https:' && websocket.protocol !== 'wss:') fail('HTTPS requires wss://.');
  const initializationTimeoutMs = raw.initializationTimeoutMs ?? 180000;
  if (!Number.isInteger(initializationTimeoutMs) || initializationTimeoutMs < 1000 || initializationTimeoutMs > 900000) fail('initializationTimeoutMs must be 1000–900000.');
  const bindings = raw.bindings ?? [];
  if (!Array.isArray(bindings) || !bindings.every(name => Object.hasOwn(BINDINGS, name)) || new Set(bindings).size !== bindings.length) fail('bindings must contain unique, supported TournamentBrowser export names.');
  return { files, engine, supportScripts, dataScripts, packageFiles:[...packageFiles], memoryInitializer, wasmBinary, wasmModule,
    format: raw.format, arguments: args, multiplayerArguments, totalMemory, websocketUrl: websocket.href, initializationTimeoutMs, bindings };
}

// Called ONLY by Module.preMainLoop/postMainLoop. Polling this object never adds frames.
export class FrameMetrics {
  constructor() { this.reset(); }
  reset() { this.samples = []; this.total = 0; this.last = null; this.start = null; }
  begin(now) { this.start = now; }
  end(now) {
    if (this.start === null) return;
    const interval = this.last === null ? null : now - this.last;
    this.samples.push({ time: now, interval, cpu: now - this.start });
    this.last = now; this.start = null; this.total++;
    this.samples = this.samples.filter(sample => now - sample.time <= 2000).slice(-1000);
  }
  snapshot(now) {
    if (!this.total) return { state: 'uninitialized', frames: 0 };
    if (now - this.last > 1500) return { state: 'stalled', frames: this.total };
    const samples = this.samples.filter(sample => now - sample.time <= 2000);
    const intervals = samples.map(s => s.interval).filter(n => n > 0 && n < 1500);
    if (intervals.length < 2) return { state: 'warming', frames: this.total };
    const mean = list => list.reduce((a, b) => a + b, 0) / list.length;
    const sorted = [...intervals].sort((a, b) => a - b);
    return { state: 'measuring', frames: this.total, fps: 1000 / mean(intervals),
      frameMs: mean(intervals), p95Ms: sorted[Math.ceil(sorted.length * .95) - 1], cpuMs: mean(samples.map(s => s.cpu)) };
  }
}
