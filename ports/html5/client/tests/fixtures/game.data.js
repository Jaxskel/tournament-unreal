// Models the legacy packager's locateFile + XHR + preRun sequence. NOT GAMEPLAY.
fixture.order.push('data-script');
fixture.package = new Promise(function(resolve, reject) {
  var request = new XMLHttpRequest();
  request.open('GET', Module.locateFile('fixture.data'));
  request.responseType = 'arraybuffer';
  request.onload = function() {
    if (request.response.byteLength !== 131072) return reject(Error('Fixture package was truncated'));
    fixture.packageBytes = request.response.byteLength;
    resolve();
  };
  request.onerror = reject;
  request.send();
});
Module.preRun.push(function() { fixture.order.push('data-prerun'); });
