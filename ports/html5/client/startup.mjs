// Legacy data scripts start their package XHR immediately, then defer mounting
// until Module.preRun. Overlap that transfer with compilation, but never execute
// engine glue until both compilation and its ordered prerequisite scripts finish.
export async function prepareEngine({ compile, loadScript, supportScripts, dataScripts, engine, stopped }) {
  if (stopped()) return false;
  const prerequisites = async () => {
    for (const name of [...supportScripts, ...dataScripts]) {
      if (stopped()) return;
      await loadScript(name);
    }
  };
  await Promise.all([Promise.resolve().then(compile), prerequisites()]);
  if (stopped()) return false;
  await loadScript(engine);
  return !stopped();
}
