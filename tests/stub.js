/* ============================================================================
   Supabase stub for Due's test harness.

   Replaces the real @supabase/supabase-js CDN bundle with an in-memory fake so
   the app can be driven headlessly with no network and no auth. Loaded INSTEAD
   of the CDN script by tests/harness.py (it rewrites the <script src> tag).

   Test hooks (all on window):
     __db        {subscriptions:[], accounts:[], payments:[]}  seed data
     __delays    {accounts: 1200}      per-table response delay in ms
     __errors    {accounts: {message}} per-table injected error (cleared manually)
     __calls     []                    log of every operation, for assertions
     __rpc       {name: fn(args)}      handlers for sb.rpc(name, args)
     __session   truthy => signed in
   ========================================================================== */
(function () {
  "use strict";

  window.__db = window.__db || { subscriptions: [], accounts: [], payments: [] };
  window.__delays = window.__delays || {};
  window.__errors = window.__errors || {};
  window.__calls = window.__calls || [];
  window.__rpc = window.__rpc || {};
  window.__session = window.__session === undefined ? { user: { id: "test-user" } } : window.__session;

  let idSeq = 0;
  const uid = () => "id-" + ++idSeq;
  const clone = v => JSON.parse(JSON.stringify(v));
  const wait = ms => new Promise(r => setTimeout(r, ms || 0));

  function table(name) {
    if (!window.__db[name]) window.__db[name] = [];
    return window.__db[name];
  }

  function matches(row, filters) {
    return filters.every(([col, val]) => row[col] === val);
  }

  async function exec(s) {
    window.__calls.push({ table: s.table, op: s.op, filters: clone(s.filters), payload: clone(s.payload) });
    await wait(window.__delays[s.table]);

    const err = window.__errors[s.table];
    if (err) return { data: null, error: err };

    const rows = table(s.table);
    let out;

    if (s.op === "select") {
      out = rows.filter(r => matches(r, s.filters));
      if (s.orderBy) {
        out = out.slice().sort((a, b) => {
          const x = a[s.orderBy], y = b[s.orderBy];
          const c = x === y ? 0 : (x == null ? -1 : y == null ? 1 : x < y ? -1 : 1);
          return s.asc ? c : -c;
        });
      }
      if (s.limitN != null) out = out.slice(0, s.limitN);
      out = clone(out);
    } else if (s.op === "insert") {
      const list = Array.isArray(s.payload) ? s.payload : [s.payload];
      const made = list.map(p => Object.assign({ id: uid(), user_id: "test-user", created_at: new Date().toISOString(), active: true }, p));
      made.forEach(r => rows.push(r));
      out = clone(made);
    } else if (s.op === "update") {
      const hit = rows.filter(r => matches(r, s.filters));
      hit.forEach(r => Object.assign(r, s.payload));
      out = clone(hit);
    } else if (s.op === "delete") {
      const keep = [], gone = [];
      rows.forEach(r => (matches(r, s.filters) ? gone : keep).push(r));
      rows.length = 0;
      keep.forEach(r => rows.push(r));
      out = clone(gone);
    }

    if (s.wantSingle) {
      if (!out.length) return { data: null, error: { message: "No rows found" } };
      return { data: out[0], error: null };
    }
    return { data: out, error: null };
  }

  function builder(name) {
    const s = { table: name, op: "select", filters: [], orderBy: null, asc: true, limitN: null, payload: null, wantSingle: false };
    const b = {
      select() { return b; },
      order(col, o) { s.orderBy = col; s.asc = !(o && o.ascending === false); return b; },
      limit(n) { s.limitN = n; return b; },
      eq(c, v) { s.filters.push([c, v]); return b; },
      is(c, v) { s.filters.push([c, v]); return b; },
      insert(p) { s.op = "insert"; s.payload = p; return b; },
      update(p) { s.op = "update"; s.payload = p; return b; },
      delete() { s.op = "delete"; return b; },
      single() { s.wantSingle = true; return b; },
      maybeSingle() { s.wantSingle = true; return b; },
      then(onOk, onErr) { return exec(s).then(onOk, onErr); }
    };
    return b;
  }

  const authListeners = [];

  window.supabase = {
    createClient() {
      return {
        from: builder,
        async rpc(name, args) {
          window.__calls.push({ rpc: name, payload: clone(args) });
          await wait(window.__delays[name]);
          if (window.__errors[name]) return { data: null, error: window.__errors[name] };
          const fn = window.__rpc[name];
          if (!fn) return { data: null, error: { message: "no stub for rpc " + name } };
          try { return { data: await fn(args), error: null }; }
          catch (e) { return { data: null, error: { message: String(e.message || e) } }; }
        },
        auth: {
          async getSession() { return { data: { session: window.__session }, error: null }; },
          onAuthStateChange(cb) { authListeners.push(cb); return { data: { subscription: { unsubscribe() {} } } }; },
          async signInWithPassword() { window.__session = { user: { id: "test-user" } }; authListeners.forEach(f => f("SIGNED_IN")); return { data: {}, error: null }; },
          async signUp() { return { data: { session: null }, error: null }; },
          async signInWithOtp() { return { data: {}, error: null }; },
          async updateUser() { return { data: {}, error: null }; },
          async signOut() { window.__session = null; authListeners.forEach(f => f("SIGNED_OUT")); return { error: null }; }
        }
      };
    }
  };
})();
