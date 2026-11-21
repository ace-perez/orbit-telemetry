# Vendored browser files

Served from `/static/vendor/` so the page loads nothing from outside the site (strict CSP,
no CDN at runtime). Every file is copied unchanged from the npm package named below;
`SHA256SUMS` records its hash and `tests/test_web.py` fails if any file changes.

| File | npm package | Path in the package | Licence |
|---|---|---|---|
| `d3.min.js` | `d3@7.9.2` | `package/dist/d3.min.js` | ISC (`licenses/d3.txt`) |
| `topojson-client.min.js` | `topojson-client@3.1.0` | `package/dist/topojson-client.min.js` | ISC (`licenses/topojson-client.txt`) |
| `land-110m.json` | `world-atlas@2.0.2` | `package/land-110m.json` | ISC, data from Natural Earth (public domain) (`licenses/world-atlas.txt`) |
| `fonts/inter-latin-{400,600}-normal.woff2` | `@fontsource/inter@5.3.0` | `package/files/` | SIL OFL 1.1 (`licenses/inter-OFL.txt`) |
| `fonts/jetbrains-mono-latin-{400,500,600}-normal.woff2` | `@fontsource/jetbrains-mono@5.3.0` | `package/files/` | SIL OFL 1.1 (`licenses/jetbrains-mono-OFL.txt`) |

Check a file against the registry yourself, for example:

    curl -sSL https://registry.npmjs.org/d3/-/d3-7.9.2.tgz | tar -xzO package/dist/d3.min.js | shasum -a 256

Updating a file: download the new package version, copy the file, update this table and
regenerate the manifest with `shasum -a 256 <files> > SHA256SUMS` (in this folder). Dependabot
does not track these files, so check for new releases by hand when touching the page.
