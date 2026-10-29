# Admin API development rules

## Code language

- Use English for identifiers, variable and function names, class names, comments, docstrings, log messages, test names, and internal keys.
- Do not use Chinese text as an identifier, code comment, or translation key.
- Keep translation keys stable and in English. Put user-facing Chinese in localization or other explicit presentation data, with an English translation.
- When editing existing code, do not add new Chinese code annotations; update nearby annotations when practical.

## Module boundaries

- Do not create or expand giant files. Separate routes, validation, business rules, and persistence into focused modules.
- Keep API endpoints thin and put reusable behavior behind clear service interfaces.
- When changing a large existing file, extract the affected responsibility instead of adding another large block. Preserve behavior and run relevant tests.
