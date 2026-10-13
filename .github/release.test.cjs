const {test} = require('node:test');
const assert = require('node:assert/strict');
const {mkdtemp, mkdir, writeFile, readFile, access, rm} = require('node:fs/promises');
const {tmpdir} = require('node:os');
const {join} = require('node:path');
const {stagePlugin, prepare} = require('./release.cjs');

test('prepare fails closed when the validated distribution is missing', async () => {
  const cwd = await mkdtemp(join(tmpdir(), 'release-missing-artifact-'));
  try {
    await mkdir(join(cwd, 'plugins/app-store-creative'), {recursive: true});
    await assert.rejects(prepare({}, {cwd, nextRelease: {version: '0.2.0'}}), {code: 'ENOENT'});
    await assert.rejects(access(join(cwd, '.build/release/app-store-creative.zip')));
  } finally {
    await rm(cwd, {recursive: true, force: true});
  }
});

test('semantic-release loads only the intended lifecycle plugins', async () => {
  const {default: getConfig} = await import('../node_modules/semantic-release/lib/get-config.js');
  const logger = {log() {}, success() {}, scope() {return this;}};
  const {options, plugins} = await getConfig({
    cwd: process.cwd(), env: process.env, logger, stdout: process.stdout, stderr: process.stderr,
  }, {});
  assert.deepEqual(options.branches, ['main']);
  assert.equal(options.tagFormat, 'v${version}');
  assert.equal(typeof plugins.prepare, 'function');
  assert.equal(options.plugins.some(plugin => plugin === '@semantic-release/npm'), false);
  const github = options.plugins.find(plugin => Array.isArray(plugin))[1];
  assert.equal(github.successComment, false);
  assert.equal(github.failTitle, false);
});

test('commit analysis follows the documented release policy', async () => {
  const {analyzeCommits} = await import('@semantic-release/commit-analyzer');
  const logger = {log() {}};
  for (const [message, expected] of [
    ['fix: repair packaging', 'patch'],
    ['feat: add a workflow', 'minor'],
    ['feat: replace contracts\n\nBREAKING CHANGE: old contracts are removed', 'major'],
    ['docs: update release instructions', null],
  ]) {
    assert.equal(await analyzeCommits({}, {cwd: process.cwd(), commits: [{message}], logger}), expected);
  }
});

test('release staging stamps both manifests and preserves source and runtime', async () => {
  const root = await mkdtemp(join(tmpdir(), 'release-test-'));
  try {
    const source = join(root, 'source');
    for (const path of ['.agents', '.codex-plugin', 'node_modules']) {
      await mkdir(join(source, path), {recursive: true});
    }
    const original = '{\n\t"metadata": {"version": "unchanged"},\n\t"name": "app-store-creative",\n\t"version"  :  "0.3.0"\n}\n\n';
    for (const path of ['.agents/.plugin.json', '.codex-plugin/plugin.json']) {
      await writeFile(join(source, path), original);
    }
    await writeFile(join(source, 'runtime.py'), 'print("runtime")\n');
    await writeFile(join(source, 'node_modules/unwanted'), 'dependency');
    const destination = join(root, 'staged');
    await stagePlugin(source, destination, '1.2.3');
    for (const path of ['.agents/.plugin.json', '.codex-plugin/plugin.json']) {
      assert.equal(JSON.parse(await readFile(join(destination, path))).version, '1.2.3');
      assert.equal(await readFile(join(destination, path), 'utf8'), original.replace('"0.3.0"', '"1.2.3"'));
      assert.equal(await readFile(join(source, path), 'utf8'), original);
    }
    assert.deepEqual(await readFile(join(destination, 'runtime.py')), await readFile(join(source, 'runtime.py')));
    await assert.rejects(access(join(destination, 'node_modules')));
    await assert.rejects(stagePlugin(source, join(root, 'invalid'), '../invalid'));
  } finally {
    await rm(root, {recursive: true, force: true});
  }
});
