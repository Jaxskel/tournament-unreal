// C-ABI TEST DOUBLE ONLY. The actual TournamentBridge implementation is external.
fixture.nativeReady = false;
fixture.nativeEpoch = 1;
fixture.nativeCalls = [];
fixture.nativeDimensions = [1920,1080];
Module._TournamentBrowserReady = () => fixture.nativeReady ? 1 : 0;
Module._TournamentBrowserSessionEpoch = () => fixture.nativeReady ? fixture.nativeEpoch : 0;
Module._TournamentBrowserSetResolution = (width,height) => { fixture.nativeCalls.push(['resolution',width,height]); fixture.nativeDimensions=[width,height]; return 1; };
Module._TournamentBrowserWidth = () => fixture.nativeDimensions[0];
Module._TournamentBrowserHeight = () => fixture.nativeDimensions[1];
Module._TournamentBrowserSetSensitivity = value => { fixture.nativeCalls.push(['sensitivity',value]); return 1; };
Module._TournamentBrowserSetVolume = value => { fixture.nativeCalls.push(['volume',value]); return 1; };
Module._TournamentBrowserReleaseInput = () => { fixture.nativeCalls.push(['release']); return 1; };
Module._TournamentBrowserFrame = () => 123;
Module.cwrap = (name,result,args) => {
  if (result !== 'number' || !args.every(type => type === 'number')) throw Error('Wrong fixture C signature');
  return Module['_'+name];
};
