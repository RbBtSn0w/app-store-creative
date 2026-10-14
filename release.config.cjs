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
    ['@semantic-release/git', {
      assets: [
        'plugins/app-store-creative/.codex-plugin/plugin.json',
        'plugins/app-store-creative/.agents/.plugin.json',
      ],
      message: 'chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}',
    }],
  ],
};
