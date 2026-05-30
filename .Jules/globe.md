## 2026-05-30 - System C locale dependency in dates
**Learning:** Python's `strftime` using `%b` relies on the system C locale and doesn't dynamically translate month abbreviations in a web server thread without Babel.
**Action:** Use numeric date representations (`%Y-%m-%d`) to bypass system C locale constraints and adhere to Canadian (`en-CA` / `fr-CA`) date formatting.
