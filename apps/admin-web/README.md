# Admin Web development rules

## Code language

- Use English for identifiers, variable and function names, component names, comments, log messages, test names, and internal keys.
- Do not use Chinese text as an identifier, code comment, or translation key.
- Keep translation keys stable and in English. Put user-facing Chinese in locale resources, with an English translation.
- When editing existing code, do not add new Chinese code annotations; update nearby annotations when practical.

## Module boundaries

- Do not create or expand giant files. Split pages by cohesive UI sections, state, and behavior into focused components and composables.
- Keep page entry files responsible for composition and wiring; place reusable logic in dedicated modules.
- When changing a large existing file, extract the affected responsibility instead of adding another large block. Preserve behavior and verify the relevant flows.
