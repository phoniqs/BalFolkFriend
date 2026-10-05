// No-op stand-in for the unavailable "midi" package used by abcjs 5.x.
// It can be called, constructed, or read like an object, and does nothing.
const target = function () {};
const stub = new Proxy(target, {
  get(_, prop) {
    if (prop === '__esModule') return false;
    if (prop === 'then' || typeof prop === 'symbol') return undefined;
    return stub;
  },
  apply() { return stub; },
  construct() { return stub; },
});
module.exports = stub;
