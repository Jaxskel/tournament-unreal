// Fixed C ABI only. No console commands or manifest-selected arbitrary functions.
export const BINDINGS = Object.freeze({
  TournamentBrowserReady: [],
  // double(void): positive integer generation of the ready local controller;
  // 0 means unavailable. Native TWeakObjectPtr identity must detect controller
  // replacement even with address reuse or a complete travel between polls.
  // List this export in runtime.json bindings to enable live settings.
  TournamentBrowserSessionEpoch: [],
  TournamentBrowserSetResolution: ['number', 'number'],
  TournamentBrowserWidth: [],
  TournamentBrowserHeight: [],
  TournamentBrowserSetSensitivity: ['number'],
  TournamentBrowserSetVolume: ['number'],
  TournamentBrowserReleaseInput: [],
  TournamentBrowserFrame: [],
  // Optional standalone menu controls; older nine-export builds keep working.
  TournamentBrowserSetMenuPaused: ['number', 'number'],
  TournamentBrowserMenuPauseStatus: ['number']
});
export const REQUIRED_BINDINGS = Object.freeze(Object.keys(BINDINGS).filter(name =>
  name !== 'TournamentBrowserSetMenuPaused' && name !== 'TournamentBrowserMenuPauseStatus'));

export class EngineBindings {
  constructor(module, names) {
    this.module = module; this.names = names; this.functions = {}; this.applied = {};
    this.disabled = new Set(); this.pendingRelease = false; this.ready = false;
    this.epoch = null;
    this.pause = { available:false, state:'unavailable', pending:false };
    this.practice = false; this.inMenu = false; this.pausedFrame = null;
  }
  discover() {
    if (typeof this.module?.cwrap !== 'function') return;
    for (const name of this.names) {
      // Old cwrap can abort on a missing export. Never probe it speculatively.
      if (!this.functions[name] && !this.disabled.has(name) && typeof this.module['_' + name] === 'function') {
        try { this.functions[name] = this.module.cwrap(name, 'number', BINDINGS[name]); }
        catch { this.disabled.add(name); }
      }
    }
  }
  call(name, ...args) {
    try { return this.functions[name]?.(...args); }
    catch { delete this.functions[name]; this.disabled.add(name); return undefined; }
  }
  release() {
    this.pendingRelease = true;
    if (this.ready && this.call('TournamentBrowserReleaseInput') === 1) this.pendingRelease = false;
  }
  dispose() {
    this.module = null;
    this.names = [];
    this.functions = {};
    this.applied = {};
    this.disabled.clear();
    this.pendingRelease = false;
    this.ready = false;
    this.epoch = null;
    this.practice = false; this.inMenu = false; this.pausedFrame = null;
    this.pause = { available:false, state:'unavailable', pending:false };
  }
  syncPause(inMenu, practice) {
    this.inMenu = inMenu; this.practice = practice;
    const available = !!this.epoch && !!this.functions.TournamentBrowserSetMenuPaused
      && !!this.functions.TournamentBrowserMenuPauseStatus && !!this.functions.TournamentBrowserFrame;
    let status = -1;
    // Even the getter is excluded in multiplayer. Native independently checks
    // the actual world's net mode and pending connection on every request.
    if (practice && available) {
      status = this.call('TournamentBrowserMenuPauseStatus', this.epoch);
      if (inMenu && status === 0) {
        this.release();
        this.call('TournamentBrowserSetMenuPaused', 1, this.epoch);
        status = this.call('TournamentBrowserMenuPauseStatus', this.epoch);
      }
    }
    const pending = practice && !inMenu && (status === 1 || status === 3);
    if (!pending) this.pausedFrame = null;
    const state = !practice ? 'live' : !this.ready ? 'waiting'
      : status === 1 ? (inMenu ? 'paused' : 'resuming')
      : status === 3 ? (inMenu ? 'pausing' : 'resuming')
      : status === 2 ? 'external' : status === 0 && !inMenu ? 'running' : 'unavailable';
    this.pause = { available:practice && available && status >= 0, state, pending };
  }
  pauseFrame() {
    if (!this.practice || this.inMenu || !this.pause.pending ||
        this.call('TournamentBrowserReady') !== 1) return null;
    const epoch = this.call('TournamentBrowserSessionEpoch');
    if (epoch !== this.epoch || !Number.isSafeInteger(epoch) || epoch <= 0 ||
        this.call('TournamentBrowserMenuPauseStatus', epoch) !== 1) return null;
    const frame = this.call('TournamentBrowserFrame');
    return Number.isSafeInteger(frame) && frame >= 0 ? { epoch, frame } : null;
  }
  beforeFrame() {
    // Observe an effective pause BEFORE this engine callback. A post-hook alone
    // cannot prove the callback consumed a long background delta while paused.
    this.pausedFrame = this.pauseFrame();
  }
  afterFrame() {
    const before = this.pausedFrame;
    this.pausedFrame = null;
    if (!before) return false;
    const after = this.pauseFrame();
    if (!after || after.epoch !== before.epoch || after.frame <= before.frame) return false;
    this.release();
    this.call('TournamentBrowserSetMenuPaused', 0, after.epoch);
    this.syncPause(this.inMenu, this.practice);
    return true;
  }
  poll(settings, inMenu = false, practice = false) {
    this.discover();
    this.ready = this.call('TournamentBrowserReady') === 1;
    const epoch = this.ready ? this.call('TournamentBrowserSessionEpoch') : null;
    const validEpoch = Number.isSafeInteger(epoch) && epoch > 0;
    if (!validEpoch || epoch !== this.epoch) {
      this.applied = {};
      this.pausedFrame = null;
      if (validEpoch && inMenu) this.pendingRelease = true;
    }
    this.epoch = validEpoch ? epoch : null;
    const available = {
      resolution: validEpoch && !!this.functions.TournamentBrowserSetResolution && !!this.functions.TournamentBrowserWidth && !!this.functions.TournamentBrowserHeight,
      sensitivity: validEpoch && !!this.functions.TournamentBrowserSetSensitivity,
      volume: validEpoch && !!this.functions.TournamentBrowserSetVolume
    };
    let actual = null, nativeFrame = null;
    if (this.ready) {
      const apply = (key, name, args) => {
        if (available[key] && settings[key] != null && this.applied[key] !== settings[key] && this.call(name, ...args) === 1) this.applied[key] = settings[key];
      };
      const dimensions = settings.resolution === '1440p' ? [2560,1440] : [1920,1080];
      apply('resolution', 'TournamentBrowserSetResolution', dimensions);
      apply('sensitivity', 'TournamentBrowserSetSensitivity', [settings.sensitivity]);
      apply('volume', 'TournamentBrowserSetVolume', [settings.volume]);
      if (this.pendingRelease) this.release();
      const width = this.call('TournamentBrowserWidth'), height = this.call('TournamentBrowserHeight');
      if (Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0) actual = [width,height];
      const frame = this.call('TournamentBrowserFrame');
      if (Number.isFinite(frame) && frame >= 0) nativeFrame = frame;
    }
    this.syncPause(inMenu, practice);
    return { ready:this.ready, epoch:this.epoch, available, applied:{ ...this.applied }, actual, nativeFrame,
      pause:{ ...this.pause }, unavailable:[...this.disabled] };
  }
}
