/**
 * Local preview bundler (development aid; not part of the product build).
 *
 * The shell sandbox cannot spawn esbuild's helper process, so `vite build` fails
 * before it reads its own config, and the registry is unreachable for extra
 * Rollup plugins. Rollup and TypeScript both run in-process, so this config
 * reimplements the small amount of glue needed (TS/JSX transpile, node
 * resolution, CommonJS interop, CSS collection) to emit the same ESM bundle.
 * `npm run build:web` stays the authoritative build for shipped artifacts.
 */
import { readFile, writeFile } from 'node:fs/promises';
import { existsSync, statSync } from 'node:fs';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const web = fileURLToPath(new URL('../apps/web/', import.meta.url));
const modules = [
  fileURLToPath(new URL('../node_modules/', import.meta.url)),
  fileURLToPath(new URL('../apps/web/node_modules/', import.meta.url)),
];
const compilerOptions = {
  target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.ESNext,
  jsx: ts.JsxEmit.ReactJSX,
  jsxImportSource: 'react',
  esModuleInterop: true,
  isolatedModules: true,
  sourceMap: false,
};

const styles = [];

function entry(file, candidates) {
  if (!file || !existsSync(file)) return null;
  if (statSync(file).isFile()) return file;
  for (const candidate of candidates) if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  return null;
}

/** Vite keeps the browser field ahead of module/main for these packages; mirror that order. */
async function bare(id) {
  for (const root of modules) {
    const base = join(root, id);
    // `withExtensions` also resolves `react` -> `react/index.js`; never hand Rollup a directory.
    const direct = withExtensions(base);
    if (direct) return direct;
    if (!existsSync(base)) continue;
    const manifest = entry(join(base, 'package.json'), []);
    if (manifest) {
      const pkg = JSON.parse(await readFile(manifest, 'utf8'));
      const browser = typeof pkg.browser === 'string' ? pkg.browser : null;
      const picked = entry(pkg.browser && typeof pkg.browser === 'object' ? join(base, pkg.browser[id] ?? '') : null, [])
        ?? entry(browser ? join(base, browser) : null, [])
        ?? entry(pkg.module ? join(base, pkg.module) : null, [])
        ?? entry(pkg.main ? join(base, pkg.main) : null, []);
      if (picked) return picked;
    }
  }
  return null;
}

const RESOLVE_EXT = ['.tsx', '.ts', '.jsx', '.js', '.mjs', '.cjs'];
function withExtensions(file) {
  if (/\.(js|mjs|cjs|ts|tsx|jsx|json|css|svg)$/.test(file)) return existsSync(file) ? file : null;
  for (const ext of RESOLVE_EXT) if (existsSync(`${file}${ext}`)) return `${file}${ext}`;
  return entry(join(file, 'index.js'), []) ?? null;
}

function nodeGlue() {
  return {
    name: 'preview-resolve',
    async resolveId(source, importer) {
      if (source.startsWith('\0')) return null;
      if (source.startsWith('.')) {
        if (!importer) return null;
        const base = resolve(dirname(importer.replace(/\?.*$/, '')), source);
        // Source files import with the emitted `.js` specifier; the file on disk is `.ts`/`.tsx`.
        const stripped = base.replace(/\.js$/, '');
        return withExtensions(base) ?? (stripped === base ? null : withExtensions(stripped));
      }
      const found = await bare(source);
      if (found) return { id: found };
      // Vite's `?raw` asset imports: resolve the packaged file and keep the query for the loader.
      const raw = /^(.*)\?raw$/.exec(source);
      if (raw) {
        const asset = await bare(raw[1]);
        if (asset) return { id: `${asset}?raw` };
      }
      return null;
    },
    async load(id) {
      const [path, query] = id.split('?');
      if (query === 'raw') return `export default ${JSON.stringify(await readFile(path, 'utf8'))};`;
      if (extname(path) === '.css') {
        const name = path.replace(/\\/g, '/').split('/apps/web/src/')[1] ?? path;
        styles.push(`/* ${name} */\n${await readFile(path, 'utf8')}`);
        return '';
      }
      if (extname(path) === '.json') return `export default ${await readFile(path, 'utf8')};`;
      if (extname(path) === '.ts' || extname(path) === '.tsx') {
        return ts.transpileModule(await readFile(path, 'utf8'), { compilerOptions, fileName: path }).outputText;
      }
      return null;
    },
  };
}

const STUBS = new Set(['fs', 'path', 'url', 'crypto', 'os', 'util', 'stream', 'events', 'assert', 'buffer', 'process', 'module', 'worker_threads', 'child_process', 'tty', 'zlib', 'http', 'https', 'net', 'perf_hooks']);
/**
 * Node builtins are only required by branches this bundle never runs. Inline the stand-in rather
 * than importing it: an unresolved `\0`-prefixed id would stay in the output and break the browser.
 */
const STUB = '(() => { const fail = () => { throw new Error("Node builtin is unavailable in the browser preview"); }; return new Proxy(fail, { get: () => fail, apply: fail }); })()';

/**
 * Drop a top-level `if (<env> [!=]= 'production') { ... } else { ... }` block, keeping the
 * branch this bundle targets. Package entry shims (react, react-dom, scheduler) use exactly
 * this shape to choose a build; bundling both branches double-exports every name.
 */
function pickBranch(code, production) {
  // After the NODE_ENV replacement the test is either `"production" === 'x'` or `process.env... === 'x'`.
  const pattern = /if\s*\(\s*((['"])production\2|[\w.]*NODE_ENV)\s*(===|!==|==|!=)\s*(['"])production\4\s*\)\s*\{/g;
  let match;
  while ((match = pattern.exec(code))) {
    const positive = match[3] === '===' || match[3] === '==';
    const keepPositive = production === positive;
    let depth = 1;
    let end = pattern.lastIndex;
    while (end < code.length && depth > 0) {
      if (code[end] === '{') depth++;
      else if (code[end] === '}') depth--;
      end++;
    }
    const thenBlock = code.slice(pattern.lastIndex, end - 1);
    const rest = code.slice(end);
    const otherwise = /^\s*else\s*\{/.exec(rest);
    let tail = rest;
    let elseBlock = '';
    if (otherwise) {
      const start = end + otherwise[0].length;
      let nested = 1;
      let at = start;
      while (at < rest.length && nested > 0) {
        if (rest[at] === '{') nested++;
        else if (rest[at] === '}') nested--;
        at++;
      }
      elseBlock = rest.slice(start, at - 1);
      tail = rest.slice(at);
    }
    const kept = keepPositive ? thenBlock : elseBlock;
    code = `${code.slice(0, match.index)}${kept}${tail}`;
    pattern.lastIndex = match.index + kept.length;
  }
  return code;
}

/** Minimal CommonJS -> ESM shim: enough for React, ReactDOM, scheduler and KaTeX. */
function cjsInterop() {
  const named = (code) => {
    const names = new Set();
    for (const m of code.matchAll(/Object\.defineProperty\(\s*exports\s*,\s*['"]([^'"]+)['"]/g)) names.add(m[1]);
    for (const m of code.matchAll(/\bexports\.([A-Za-z_$][\w$]*)\s*=/g)) names.add(m[1]);
    return [...names];
  };
  return {
    name: 'preview-cjs',
    async transform(code, id) {
      const path = id.split('?')[0];
      if (!/\.(js|cjs)$/.test(path)) return null;
      if (!/\bmodule\.exports\b|\bexports\.[A-Za-z_$]|\brequire\(/.test(code)) return null;
      const body = pickBranch(code.replace(/process\.env\.NODE_ENV/g, JSON.stringify('production')), true);
      // Resolve every require() statically so nested conditionals are bundled like an ESM graph.
      const specs = new Set();
      for (const m of body.matchAll(/\brequire\(\s*['"]([^'"]+)['"]\s*\)/g)) specs.add(m[1]);
      const resolved = new Map();
      for (const spec of specs) resolved.set(spec, spec.startsWith('.') ? resolve(dirname(path), spec) : await bare(spec));
      const imported = new Map();
      let head = '';
      for (const [spec, file] of resolved) {
        if (!file) continue;
        const local = `__ns${imported.size}`;
        imported.set(spec, local);
        head += `import * as ${local} from ${JSON.stringify(file)};\n`;
      }
      const table = [...imported].map(([spec, local]) => `${JSON.stringify(spec)}: ${local}`).join(', ');
      // Entry shims such as react/index.js re-export a sibling build wholesale; forward those names.
      const reexports = [...specs]
        .filter(spec => body.includes(`module.exports = require('${spec}')`) || body.includes(`module.exports = require("${spec}")`))
        .filter(spec => resolved.get(spec))
        .map(spec => `export * from ${JSON.stringify(resolved.get(spec))};`)
        .join('\n');
      const shim = `(id) => { const ns = { ${table} }[id]; if (ns === undefined) throw new Error('unresolved require: ' + id); return ns.default !== undefined ? ns.default : ns; }`;
      return {
        code: `${head}const __m = { exports: {} };\n(function (module, exports, require) {\n${body}\n})(__m, __m.exports, ${shim});\n${named(body).map(name => `export const ${name} = __m.exports[${JSON.stringify(name)}];`).join('\n')}\n${reexports}\nexport default __m.exports;\n`,
        map: null,
      };
    },
  };
}

function html(entryName) {
  return {
    name: 'preview-html',
    async generateBundle() {
      // Must live under /assets: the app serves that subtree as static files and would otherwise
      // answer /index.css with index.html, which the browser refuses as a stylesheet.
      this.emitFile({ type: 'asset', fileName: 'assets/index.css', source: styles.join('\n\n') });
      const source = await readFile(resolve(web, 'index.html'), 'utf8');
      this.emitFile({
        type: 'asset',
        fileName: 'index.html',
        source: source.replace(/\s*<script[^>]*src="[^"]*"[^>]*><\/script>/, '').replace('</head>', '    <link rel="stylesheet" href="/assets/index.css">\n  </head>').replace('</body>', `    <script type="module" src="/assets/${entryName}.js"></script>\n  </body>`),
      });
    },
  };
}

const entryName = 'main';

export default {
  input: resolve(web, 'src/main.tsx'),
  output: { dir: resolve(web, 'preview'), format: 'es', entryFileNames: 'assets/[name].js', chunkFileNames: 'assets/[name].js', assetFileNames: 'assets/[name][extname]' },
  treeshake: false,
  onwarn: () => {},
  plugins: [
    nodeGlue(),
    {
      name: 'preview-env',
      transform(code) { return code.replace(/process\.env\.NODE_ENV/g, JSON.stringify('production')); },
    },
    cjsInterop(),
    html(entryName),
  ],
};
