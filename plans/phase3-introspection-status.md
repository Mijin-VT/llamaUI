# Phase 3 — Dynamic llama-server Introspection Status

## Status

Core implemented and smoke-tested.

## Files added/updated

- `qt_app/app/services/help_parser.py`
- `qt_app/app/services/option_schema.py`
- `qt_app/app/services/llama_server.py`
- `qt_app/app/services/__init__.py`
- `qt_app/app/pages/settings.py`
- `qt_app/app/pages/diagnostics.py`
- `qt_app/app/main_window.py`

## Implemented

- Help parser for `llama-server --help` output.
- Parsed option model with flags, value placeholder, inferred kind, inferred group, description, default, and raw help.
- Runtime schema model keyed by binary path, size, mtime, and version.
- Schema cache under app data `schemas/` directory.
- Merge from parsed options into curated catalog:
  - parsed support decides runtime visibility;
  - curated descriptions/groups win when a flag matches catalog metadata;
  - unknown parsed options are preserved as supported Advanced/Raw options.
- `build_runtime_schema(path)` service that validates a binary, captures help, parses options, merges schema, and returns probe + schema.
- Settings page can browse/type a binary path, validate, parse, and show parsed/curated/unknown counts plus first parsed options.
- Diagnostics page now shows actual Qt/session/GPU/portal evidence.

## Verification observed

Parser smoke:

```text
[(['-m', '--model'], 'FNAME', 'string', None, 'model_loading'),
 (['-c', '--ctx-size'], 'N', 'integer', '4096', 'context_kv'),
 (['--no-mmap'], None, 'boolean', None, 'performance'),
 (['--host'], 'HOST', 'string', None, 'server_api'),
 (['--top-p'], 'P', 'float', '0.95', 'sampling')]
```

Schema/cache smoke:

```text
parsed= 6 merged= 6 unknown= 2
```

Service smoke:

```text
pass framework diagnostics type
pass gpu vendor enum
pass Qt Wayland plugin discoverable
pass llama probe type
pass missing binary rejected
pass config round trip
pass library round trip
pass profile round trip
```

Qt shell smoke:

```text
platform= wayland
visible= True
rc= 0
```

Static compile:

```text
python -m compileall -q qt_app
```

completed with no output/errors.

## Notes

- Parser handles representative flags and continuation lines. It still needs validation against a real selected `llama-server --help` output in the target environment.
- Unknown count in synthetic schema smoke is expected because the sample includes `--new-flag`, and some aliases may not yet be in the curated catalog.
- Settings UI is real for validation/introspection, but the full settings editor comes in Phase 5.

## Next phase

Phase 4: Qt frontend shell rewrite beyond placeholders.

- Replace Library/Discover/Profiles placeholders with real page scaffolds and state flow.
- Keep Run page aligned with the setting schema from Phase 3.
- Make Settings persist selected binary/config through the stores.
