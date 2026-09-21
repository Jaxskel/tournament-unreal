// TEST FIXTURE: models the converter's async wrapper, never real game execution.
Module.gameRuntimeReady = (async function(Module) {
  if (!(Module.wasmModule instanceof WebAssembly.Module)) throw Error('WASM was not compiled before script load');
  if (new TextDecoder().decode(Module.memoryInitializerRequest.response) !== 'FIXTURE MEMORY') throw Error('Legacy memory initializer missing');
  await new Promise(resolve => setTimeout(resolve, 400));
  const instance = await WebAssembly.instantiate(Module.wasmModule, {});
  fixture.converted = instance instanceof WebAssembly.Instance;
  // Closure-local UE_JSlib is intentional: launcher must not depend on this global.
  const UE_JSlib = { UE_GSystemResolution_ResX: () => 1 };
  Module.preInit.forEach(fn => fn());
  Module.preRun.forEach(fn => fn());
  await fixture.package;
  Module.onRuntimeInitialized();
  Module.postRun.forEach(fn => fn());
})(Module);
