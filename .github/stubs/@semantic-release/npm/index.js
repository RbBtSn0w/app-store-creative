// In-tree stub module for @semantic-release/npm.
// app-store-creative is private and publishes via GitHub Releases assets,
// not via npm. This stub prevents installing the bundled npm CLI dependencies.
function failLoudly() {
  throw new Error(
    '@semantic-release/npm should never be executed: app-store-creative is private and does not publish to npm registry.'
  );
}

module.exports = {
  verifyConditions: failLoudly,
  generateNotes: failLoudly,
  prepare: failLoudly,
  publish: failLoudly,
  addChannel: failLoudly,
  success: failLoudly,
  fail: failLoudly,
};
