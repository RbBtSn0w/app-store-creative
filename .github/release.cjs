const {cp, mkdir, readFile, writeFile, mkdtemp, rm} = require('node:fs/promises');
const {join} = require('node:path');
const {tmpdir} = require('node:os');
const {execFileSync} = require('node:child_process');

const manifests = ['.codex-plugin/plugin.json', '.agents/.plugin.json'];

async function stagePlugin(source, destination, version) {
  if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('Expected a stable release version');
  await cp(source, destination, {
    recursive: true,
    filter: (path) => !/(^|[/\\])(node_modules|__pycache__|\.DS_Store)([/\\]|$)|\.pyc$/.test(path),
  });
  for (const manifest of manifests) {
    const path = join(destination, manifest);
    const data = JSON.parse(await readFile(path, 'utf8'));
    data.version = version;
    await writeFile(path, `${JSON.stringify(data, null, 2)}\n`);
  }
}

async function prepare(_config, {cwd, nextRelease}) {
  const scratch = await mkdtemp(join(tmpdir(), 'creative-release-'));
  try {
    const plugin = join(scratch, 'plugin');
    await stagePlugin(join(cwd, '.build/validated/app-store-creative'), plugin, nextRelease.version);
    const output = join(cwd, '.build/release');
    await mkdir(output, {recursive: true});
    execFileSync('python3', [join(cwd, '.github/package_plugin.py'), '--plugin-root', plugin,
      '--output', join(output, 'app-store-creative.zip')], {cwd, stdio: 'inherit'});
  } finally {
    await rm(scratch, {recursive: true, force: true});
  }
}

module.exports = {prepare, stagePlugin};
