# Contributing to FluentSignalCopier

## Thanks for your interest in contributing! 🎉

This guide explains how to set up your environment, coding standards, commit conventions, testing, and releases.

📦 Development Setup

- **Clone the repo**:

```powershell
    git clone https://github.com/The-R4V3N/FluentSignalCopier.git
    cd FluentSignalCopier
```

- **Install dependencies with Poetry:**:

Make sure you have Poetry installed (recommended via pipx)

```powershell
    poetry install --no-root
```

This will install all runtime + dev dependencies into a Poetry-managed virtual environment.

- **Activate the virtual environment:**:

```powershell
    poetry shell
```

- **Run locally**:

- GUI

```powershell
    poetry run python fluent_copier.py
```

- CLI

```powershell
    poetry run python telegram_bridge.py
```

## Building exe

``` powershell
    poetry run pyinstaller --clean --noconfirm --onefile --noconsole `
  --name FluentSignalCopier `
  --icon .\app.ico `
  --add-data "app.ico;." `
  --collect-all PySide6 `
  --collect-all qfluentwidgets `
  .\fluent_copier.py
```

- **Notes:**

- collect-all PySide6 ensures Qt plugins (platforms, styles, etc.) are bundled.
- collect-all qfluentwidgets pulls in QFluentWidgets assets.
- noconsole hides the console window for GUI builds. For debugging, drop it.

Binary lands in dist/FluentSignalCopier(.exe).

- **🧑‍💻 Coding Standards**:

- Use Python 3.11+ (aligned with CI).
- Follow PEP8 for formatting.
- Replace print() with the centralized logger (setup_logging).
- Keep functions small and modular — one purpose, one responsibility.
- Write docstrings for all public functions/classes.
- Prefer clear, defensive error handling; include context in log messages.

- **✍️ Commit Message Guidelines**:

- We use Conventional Commits. Each message must be:

``` powershell
    <type>(optional scope): <short description>
```

- **Ensure version is correct:**

- README.md badge
- CHANGELOG.md

- **Allowed types**:

``` powershell
    feat:       A new feature
    fix:        A bug fix
    docs:       Documentation only changes
    style:      Changes that do not affect the meaning of the code (white-space, formatting, etc)
    refactor:   A code change that neither fixes a bug nor adds a feature
    perf:       A code change that improves performance
    test:       Adding missing or correcting existing tests
    build:      Changes to the build system or dependencies
    ci:         Changes to CI/CD configuration
    chore:      Changes to the build process or auxiliary tools and libraries such as documentation generation
    revert:     Revert a previous commit

    Examples:

    feat(parser): score CLOSE/MODIFY signals
    fix(gui): render log lines without ANSI colors
    docs: add SECURITY policy
    ci: add commitlint workflow
```

Local enforcement: Husky runs commitlint on commit/push if you’ve set it up locally.
Remote enforcement: CI also runs commitlint on PRs.

## ✅Pull Requests

- **Create a new branch for your feature/fix**:

```powershell
    git checkout -b feature/my-new-thing
```

Before opening a PR:

- Make sure your commits follow Conventional Commits.
- Add screenshots/logs for GUI/logging changes.
- Include tests where practical (parsers, helpers).
- Update docs (README/CHANGELOG) if behavior or public API changes.

PR checklist

- [ ] Commits follow Conventional Commits
- [ ] Tests added/updated (if applicable)
- [ ] Docs updated (README/CHANGELOG)
- [ ] Manually tested GUI/CLI
- [ ] Demo MT5 EA integration verified (for trade-path changes)

- **🧪 Testing**:

- Run unit tests before submitting PRs:

```powershell
    poetry run pytest
```

Manual checks (as applicable):

- GUI: parsing, logging, confidence slider, heartbeat file writing.
- CLI: bridge behavior and JSONL output.
- EA: demo account end-to-end (OPEN/CLOSE/MODIFY/MODIFY_TP).

- **🔄 Versioning & Releases**:

We follow Semantic Versioning.
When cutting a release, bump versions in:

- README.md → version badge
- CHANGELOG.md → add new entry
- mt5/version_info.txt (or your path) → FileVersion and ProductVersion

Example (0.9.1 → 0.10.0):

```powershell
    StringStruct('FileVersion', '0.10.0')
    StringStruct('ProductVersion', '0.10.0')
```

- **Release steps**:

```powershell
    poetry version 0.10.0
    git commit -m "chore(release): v0.10.0"
    git tag v0.10.0
    git push origin v0.10.0
```

Publish a GitHub release; attach built .exe artifacts if you’re distributing binaries.

- **🧰 Useful Local Commands**:

- Check commit messages:

```powershell
    npx commitlint --from=HEAD~10 --to=HEAD
```

- Format + lint:

```powershell
    poetry run black .
    poetry run ruff check .
    poetry run pytest
```

- **Code of Conduct**:

Please read our [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Be respectful and collaborative.

- **🔐 Security**:

For vulnerability reports, see [SECURITY.md](SECURITY.md).
Please do not open public issues for security-sensitive reports.

## 🙏 Credits

Big thanks to all contributors! 💜
If you have ideas, open an issue before making large changes — saves time and keeps direction clear.
