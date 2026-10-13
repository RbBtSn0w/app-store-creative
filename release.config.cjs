module.exports = {
  branches: ['main'],
  tagFormat: 'v${version}',
  plugins: [
    '@semantic-release/commit-analyzer',
    '@semantic-release/release-notes-generator',
    './.github/release.cjs',
    ['@semantic-release/github', {
      assets: [{path: '.build/release/app-store-creative.zip', label: 'Complete plugin distribution'}],
      successComment: false,
      failComment: false,
      failTitle: false,
      releasedLabels: false,
    }],
  ],
};
