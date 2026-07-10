---
name: httpx client across mixed event loops
description: Why a shared/global httpx.AsyncClient breaks when a module is called from both a long-running asyncio loop and a sync framework using per-call asyncio.run()
---

Don't cache an `httpx.AsyncClient` (or an `asyncio.Lock` guarding one) as a
module-level global if the module can be called both from a long-running
event loop (e.g. a Telegram bot's polling loop) and from a sync framework
route that wraps each call in its own `asyncio.run(...)` (e.g. Flask). Each
`asyncio.run()` call creates and destroys a new event loop, and an
AsyncClient is bound to the loop that created it — reusing it from a
different loop causes runtime errors (or silent connection issues) on the
second and later calls, even though a quick single-call test looks fine.

**Why:** discovered while wiring a shared `generate_ai_response()` AI client
module into both a Telegram bot (own event loop) and a Flask mini-app route
(`asyncio.run()` per request).

**How to apply:** if a shared async helper module must be callable from both
worlds, don't pool a client/lock globally — open a fresh client scoped to
the duration of each top-level call (`async with httpx.AsyncClient(...) as
client:` inside the function), accepting the loss of cross-call pooling in
exchange for correctness. Only pool a client globally if you control the
single event loop it will always run on.
