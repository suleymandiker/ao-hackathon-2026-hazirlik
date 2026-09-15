

## AI response cache
Completed AI responses are cached by model + prompt + input + generation settings. Repeated runs of the same analysis can skip model calls entirely. Failed or truncated responses are not cached.


## v40 additions
- AI response cache is bounded with TTL, LRU-style access eviction, max entry count and max response-byte budget.
- Added bounded AI-assisted Drain3 SRE Fidelity Tuner. The model sees only a representative sample and compact template statistics; Python/Drain3 remains authoritative.
- Tuned Drain3 policies are persisted by dataset/sample fingerprint and reused.
- Runtime/debug output exposes selected `sim_th`, `depth`, tuner call count and cache-hit state.
- The main streaming path remains bounded; autotune reads only a small pre-sample and never loads the full file.
