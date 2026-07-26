/* ============================================================================
   Due — service worker.

   Goal: the app opens from a cold start with no network. Before this, the
   localStorage cache only helped if the page was already loaded.

   Deliberately network-first for the page itself, so it does NOT need to know
   the app version and can never pin you to a stale build while you're online.
   index.html still self-updates by comparing APP_VERSION; that probe carries a
   ?u= cache-buster and is passed straight through, never served from cache.
   ========================================================================== */
"use strict";

const CACHE = "due-shell-v1";

// Everything needed to boot with no network. Same-origin only: a cross-origin
// asset that hangs (rather than failing) would leave the worker stuck installing
// forever. The Supabase bundle is self-hosted (v6.1) precisely so it can live in
// this list — as a CDN script its response was opaque and uncacheable, which broke
// cold offline starts.
const SHELL = [
  "./",
  "./index.html",
  "./supabase.js",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-maskable-512.png",
  "./apple-touch-icon.png"
];

// Belt and braces: never let one slow asset hold up activation.
const withTimeout = (p, ms) => Promise.race([p, new Promise(r => setTimeout(r, ms))]);

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE)
      // one bad URL shouldn't fail the whole install, so add them individually
      .then(c => withTimeout(Promise.all(SHELL.map(u => c.add(u).catch(() => {}))), 10000))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

const isSupabaseApi = url =>
  url.hostname.endsWith(".supabase.co") || url.pathname.startsWith("/rest/v1") || url.pathname.startsWith("/auth/v1");

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Never touch the API — stale subscription data would be worse than an error.
  if (isSupabaseApi(url)) return;

  // The app's own update probe (index.html?u=<ts>). Must always hit the network,
  // or the app could never notice a new version.
  if (url.searchParams.has("u")) return;

  // The page: network first so you always get the newest build when online,
  // cache only as the offline fallback.
  if (req.mode === "navigate" || req.destination === "document") {
    e.respondWith(
      fetch(req)
        .then(res => {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put("./index.html", copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match("./index.html").then(r => r || caches.match("./")))
    );
    return;
  }

  // Static assets: cache first (they're immutable in practice), refreshed quietly
  // in the background so a changed icon still lands on the next launch.
  e.respondWith(
    caches.match(req).then(hit => {
      const live = fetch(req)
        .then(res => {
          if (res && res.ok) caches.open(CACHE).then(c => c.put(req, res.clone())).catch(() => {});
          return res;
        })
        .catch(() => hit);
      return hit || live;
    })
  );
});
