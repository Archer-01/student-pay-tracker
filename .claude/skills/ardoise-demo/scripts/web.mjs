// The app for a demo, run from frontend/: `node web.mjs <dev|prod> <port> <apiPort> <dir>`.
// dev: Vite's dev server without the repo's vite.config.ts, whose proxy points at the developer's
// own backend on :8000. prod: `vite preview` of the build demo.sh made in <dir>/dist.
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const [mode, port, apiPort, dir] = process.argv.slice(2);
const frontend = process.cwd();
const require = createRequire(`${frontend}/package.json`);
const load = (name) => import(pathToFileURL(require.resolve(name)).href);

const { createServer, preview } = await load("vite");
const proxy = {
  "/api": { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
  "/health": { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
};
const listen = { host: "127.0.0.1", port: Number(port), strictPort: true, proxy };

if (mode === "prod") {
  const server = await preview({ configFile: false, root: frontend, build: { outDir: `${dir}/dist` }, preview: listen });
  server.printUrls();
} else {
  const { default: react } = await load("@vitejs/plugin-react");
  const server = await createServer({
    configFile: false,
    root: frontend,
    cacheDir: `${dir}/vite-cache`,
    plugins: [react()],
    server: { ...listen, hmr: false },
  });
  await server.listen();
  server.printUrls();
}
