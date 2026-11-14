/*
 * Ardoise's service worker: lets the installed app open, and show the last data it saw, without
 * a connection ("lecture seule"). It never stores or replays a write.
 *
 * Built by the `ardoise-service-worker` plugin in vite.config.ts, which fills in the build id and
 * the list of files to keep; it is not used in development. See frontend/CLAUDE.md, "Offline".
 */

const BUILD_ID = "__ARDOISE_BUILD_ID__";
const PRECACHE = /*__ARDOISE_PRECACHE__*/ [];

// The app's own files, one cache per build: a new deploy brings a new worker, which drops the
// old build's files so the installed app can't stay on an old version.
const SHELL = `ardoise-shell-${BUILD_ID}`;
// The last copy of each screen's data. Not versioned: the page clears it on sign-in, sign-out
// and an expired session (src/lib/offlineData.ts), so one account's data never shows for another.
const DATA = "ardoise-data";
// With one bar of signal a request can hang rather than fail; past this, use what is stored.
const TIMEOUT_MS = 4000;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names.filter((n) => n.startsWith("ardoise-shell-") && n !== SHELL).map((n) => caches.delete(n)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  // Only reads from this site are ever served from storage. Writes go straight to the network,
  // and fail plainly when there is none.
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/api/v1/")) {
    // PDFs are files to download, not screens to show again.
    if (url.pathname.endsWith(".pdf")) return;
    event.respondWith(networkFirstData(event, request));
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(networkFirstShell(request));
    return;
  }
  if (url.pathname.startsWith("/assets/") || PRECACHE.includes(url.pathname)) {
    event.respondWith(cacheFirst(request));
  }
});

function timeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("timeout")), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

/**
 * The network first; the stored copy only when the network fails or is too slow. A response
 * from the server, even a 401 or a 500, is always passed on as is: old data must never hide an
 * expired session or a server error. Successful reads are stored, stamped with when.
 */
async function networkFirstData(event, request) {
  const cache = await caches.open(DATA);
  const network = fetch(request).then(async (response) => {
    if (response.ok) {
      const headers = new Headers(response.headers);
      headers.set("x-ardoise-saved-at", new Date().toISOString());
      const body = await response.clone().blob();
      await cache.put(request, new Response(body, { status: response.status, headers }));
    }
    return response;
  });
  // A slow answer still refreshes the stored copy when it arrives.
  event.waitUntil(network.catch(() => undefined));

  try {
    return await timeout(network, TIMEOUT_MS);
  } catch {
    const stored = await cache.match(request);
    if (stored) return stored;
    try {
      return await network;
    } catch {
      // Never opened online: there is nothing to show. The app turns this code into a sentence.
      return new Response(JSON.stringify({ detail: "offline", code: "offline" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      });
    }
  }
}

/** Pages: the network first (so a new deploy is picked up), the stored app when offline. */
async function networkFirstShell(request) {
  try {
    return await timeout(fetch(request), TIMEOUT_MS);
  } catch {
    const shell = await caches.open(SHELL);
    return (await shell.match("/")) ?? Response.error();
  }
}

/** The build's own files never change under the same name, so the stored copy is always right. */
async function cacheFirst(request) {
  const stored = await caches.match(request);
  if (stored) return stored;
  const response = await fetch(request);
  if (response.ok) {
    const shell = await caches.open(SHELL);
    await shell.put(request, response.clone());
  }
  return response;
}
