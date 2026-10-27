# Chat API development rules

The Chat API owns MOVO's conversation orchestration, runtime profiles, tool access, and recovery behavior.

## DSH boundary

- Do not modify DSH source code or files under `services/chat-api/dsh/`, including the Runtime Host wrapper, presets, tests, and installed packages.
- Fix MOVO behavior in `services/chat-api/app/` and its tests. Use supported DSH APIs and keep integration logic in small, focused modules.
- If a change appears to require a DSH source edit, document the missing API or capability and review the boundary before implementation. Do not patch vendored code.

## Code language

- Use English for identifiers, variable names, function names, class names, comments, docstrings, log messages, test names, and internal keys.
- Do not use Chinese text as an identifier, translation key, or code comment.
- User-facing Chinese belongs in the localization resources or other explicit presentation data. Keep stable localization keys in English.
- Existing Chinese content does not authorize adding new Chinese code annotations; update affected annotations when editing nearby code.
