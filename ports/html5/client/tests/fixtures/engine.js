// Deliberately a lifecycle test double, never a UT4 implementation or benchmark.
fixture.order.push('engine');
fixture.moduleAtStart = { arguments: Module.arguments.slice(), totalMemory: Module.TOTAL_MEMORY,
  initialMemory: Module.INITIAL_MEMORY, websocket: Module.websocket, noImageDecoding: Module.noImageDecoding,
  noAudioDecoding: Module.noAudioDecoding };
if (Module.wasmBinary) {
  if (!WebAssembly.validate(Module.wasmBinary)) throw Error('Invalid fixture WASM');
  fixture.wasm = true;
} else if (new TextDecoder().decode(Module.memoryInitializerRequest.response) !== 'FIXTURE MEMORY') {
  throw Error('Fixture memory initializer missing');
}
window.UE_JSlib = {
  UE_GSystemResolution_ResX: function() { return Number(Module.arguments.find(a => a.startsWith('-ResX=')).split('=')[1]); },
  UE_GSystemResolution_ResY: function() { return Number(Module.arguments.find(a => a.startsWith('-ResY=')).split('=')[1]); }
};
Module.pauseMainLoop = function() { fixture.paused = true; };
Module.resumeMainLoop = function() { fixture.paused = false; };
Module.preInit.forEach(function(fn) { fn(); });
Module.preRun.forEach(function(fn) { fn(); });
Module.monitorRunDependencies(1);
fixture.package.then(function() {
  Module.monitorRunDependencies(0);
  Module.onRuntimeInitialized();
  Module.postRun.forEach(function(fn) { fn(); });
  var ctx = Module.canvas.getContext('2d');
  ctx.fillStyle = '#21190f'; ctx.fillRect(0, 0, Module.canvas.width, Module.canvas.height);
  ctx.fillStyle = '#e4b766'; ctx.font = '36px sans-serif';
  ctx.fillText('TEST FIXTURE — NOT UT4 GAMEPLAY', 80, 120);
});
// No animation loop: the browser tests invoke preMainLoop/postMainLoop explicitly.
