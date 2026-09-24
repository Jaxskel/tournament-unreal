// Lifecycle fixture only: no audio playback or UT4. The converter suite tests
// the emitted closure helper; this fixture checks direct browser gesture wiring.
fixture.audioCalls = [];
fixture.audioBehavior = 'suspended';
Module.resumeBrowserAudio = function() {
  fixture.audioCalls.push(['audio', navigator.userActivation.isActive]);
  switch (fixture.audioBehavior) {
    case 'throw': throw Error('fixture audio throw');
    case 'reject': return Promise.reject(Error('fixture audio rejection'));
    case 'pending': return new Promise(resolve => { fixture.finishAudio = resolve; });
    default: return Promise.resolve(fixture.audioBehavior);
  }
};
Module.canvas.requestPointerLock = function() {
  fixture.audioCalls.push(['pointer', navigator.userActivation.isActive]);
  return Promise.resolve();
};
