# Contributing to FluentSignalCopier

## Thanks for your interest in contributing! 🎉

This guide explains how to set up your environment, follow coding standards, and release new versions.

📦 Development Setup

- **Clone the repo**:

```bash
git clone https://github.com/The-R4V3N/FluentSignalCopier.git
cd FluentSignalCopier
```

- **Install dependencies**:

```bash
pip install -r requirements.txt

```bash
pip install -r requirements.txt
```

- **Run locally**:

- GUI

```bash
python fluent_copier.py
```

- CLI

```bash
python telegram_bridge.py
```

🧑‍💻 Coding Standards

- Use Python 3.11+ (aligned with CI).
- Follow PEP8 for formatting.
- Replace print() with the centralized logger (setup_logging).
- Keep functions small and modular — one purpose, one responsibility.
- Write docstrings for all public functions/classes.

## ✅Pull Requests

```bash
git checkout -b feature/my-new-thing
```

- **Commit messages should follow this style**:

```bash
feat: add new monitoring panel
fix: handle Telegram reconnects
docs: update README with new setup instructions
chore: bump version to 0.10.0
```

- Open a PR with a clear description of what was added/changed/removed.
- Add screenshots or logs if it’s a UI/logging change.

## 🔄 Versioning & Releases

We follow ([Semantic Versioning](https://semver.org/)).

Every new release requires bumping versions in three places:

- README.md → version badge at the top
- CHANGELOG.md → add new release entry
- version_info.txt → update FileVersion and ProductVersion

Example: bump from 0.9.1 → 0.10.0

```bash
StringStruct('FileVersion', '0.10.0')
StringStruct('ProductVersion', '0.10.0')
```

## Release Steps

- Update versions in all files.
- Commit with:

```bash
chore(release): bump version to 0.10.0
```

- Tag the release:

```bash
git tag v0.10.0
git push origin v0.10.0
```

- Publish a GitHub Release and attach built .exe artifacts.

## 🧪 Testing

Run unit tests before submitting PRs:

```bash
pytest
```

- Test both GUI and CLI to ensure logging and monitoring behave consistently.
- Verify MT5 EA connectivity in demo mode before pushing production changes.

## 🙏 Credits

Big thanks to all contributors! 💜
If you have ideas, open an issue before making large changes — saves time and keeps direction clear.
