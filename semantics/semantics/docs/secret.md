# 🦑 Cuttlefish

If you're reading this, you found it.

`Semantics` was internally codenamed **Cuttlefish** during development —
a nod to *Sepiida*, the cephalopod famous for two things this project
aspired to:

1. **Camouflage through understanding, not mimicry.** A cuttlefish
   doesn't copy the exact pixels of its surroundings — its skin reads
   the *structure* of the scene (texture, contrast, edges) and produces
   a fitting pattern from scratch. That's the same bet `repo_map` makes:
   understand a codebase's structure well enough to act in it, without
   ever needing a literal copy of everything (no vector DB required).

2. **A distributed nervous system.** Roughly two-thirds of a cuttlefish's
   neurons live outside its central brain, in its arms — each arm can
   react locally without waiting for a top-down decision. That's the
   inspiration for PicoClaw sub-agents (`src/pro/pico.py`): small,
   cheap, semi-autonomous workers fanning out from one coordinating
   agent loop.

## Easter egg unlocked

Run:

```bash
ctf --version --explain 2>/dev/null | grep -i cuttlefish || echo "🦑 Cuttlefish sees you."
```

Nothing else changes. There's no hidden mode — we just liked the name
enough to leave a trail to it.

— The Semantics team
