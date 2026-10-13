const {cp, mkdir, readFile, writeFile, mkdtemp, rm} = require('node:fs/promises');
const {join} = require('node:path');
const {tmpdir} = require('node:os');
const {execFileSync} = require('node:child_process');

const manifests = ['.codex-plugin/plugin.json', '.agents/.plugin.json'];

function stampVersion(text, version) {
  if (typeof JSON.parse(text).version !== 'string') throw new Error('Missing manifest version');
  // Token offsets preserve formatting while excluding nested version properties.
  const tokens = [...text.matchAll(/"(?:\\.|[^"\\])*"|[{}\[\]:,]/g)];
  let depth = 0;
  const values = [];
  for (let index = 0; index < tokens.length; index++) {
    const token = tokens[index][0];
    if (token === '{' || token === '[') depth++;
    else if (token === '}' || token === ']') depth--;
    else if (depth === 1 && token.startsWith('"') && JSON.parse(token) === 'version' &&
             tokens[index + 1]?.[0] === ':') values.push(tokens[index + 2]);
  }
  if (values.length !== 1) throw new Error('Expected exactly one top-level manifest version');
  const value = values[0];
  return text.slice(0, value.index) + JSON.stringify(version) + text.slice(value.index + value[0].length);
}

async function stagePlugin(source, destination, version) {
  if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('Expected a stable release version');
  await cp(source, destination, {
    recursive: true,
    filter: (path) => !/(^|[/\\])(node_modules|__pycache__|\.DS_Store)([/\\]|$)|\.pyc$/.test(path),
  });
  for (const manifest of manifests) {
    const path = join(destination, manifest);
    await writeFile(path, stampVersion(await readFile(path, 'utf8'), version));
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
