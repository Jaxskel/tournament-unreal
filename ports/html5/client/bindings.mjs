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
  TournamentBrowserFrame: []
});

export class EngineBindings {
  constructor(module, names) {
    this.module = module; this.names = names; this.functions = {}; this.applied = {};
    this.disabled = new Set(); this.pendingRelease = false; this.ready = false;
    this.epoch = null;
  }
  discover() {
    if (typeof this.module.cwrap !== 'function') return;
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
  poll(settings, inMenu = false) {
    this.discover();
    this.ready = this.call('TournamentBrowserReady') === 1;
    const epoch = this.ready ? this.call('TournamentBrowserSessionEpoch') : null;
    const validEpoch = Number.isSafeInteger(epoch) && epoch > 0;
    if (!validEpoch || epoch !== this.epoch) {
      this.applied = {};
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
    return { ready:this.ready, epoch:this.epoch, available, applied:{ ...this.applied }, actual, nativeFrame, unavailable:[...this.disabled] };
  }
}
