# Fluent Signal Copier - Pre-Launch Tasks

> Checklist of everything needed before this product is sellable.
> Current state: ~60-70% ready. Core product is solid, commercialization layer is missing.

---

## P0 - Critical Blockers

These must be fixed before any public release.

- [ ] **Fix license contradiction** — `pyproject.toml` says `"MIT"` but `LICENSE` file is custom restrictive. Change pyproject.toml to `license = "Proprietary"`
- [ ] **Align version numbers** — pyproject.toml says `0.10.0`, README badge says `v0.13.0-beta`. Pick one source of truth and sync everywhere
- [ ] **Implement license key system** — Validate license keys on startup, enforce seat/device limits defined in LICENSE (1 seat, 2 devices, 2 MT5 accounts)
- [ ] **Add payment integration** — Gumroad, Paddle, LemonSqueezy, or Stripe. Must handle license key delivery on purchase
- [ ] **Remove `.vscode/` from tracking** — Add to `.gitignore`, remove from git index

---

## P1 - Customer Experience

Required for a professional product launch.

- [ ] **First-run setup wizard** — Guide new users through Telegram API setup, MT5 directory selection, and first signal test
- [ ] **Improve error handling** — Replace bare `except Exception:` blocks with structured error types and user-facing messages
- [ ] **Add crash reporting** — Integrate Sentry or similar opt-in crash/error telemetry
- [ ] **Create customer onboarding flow** — Purchase > license key email > setup wizard > activation > first signal test
- [ ] **Device fingerprinting** — Implement hardware/machine ID for device limit enforcement
- [ ] **Trial period mechanism** — Time-limited or feature-limited trial so customers can evaluate before buying
- [ ] **Auto-update system** — Notify users of new versions, ideally with one-click update

---

## P2 - Quality & Testing

- [ ] **Expand test coverage** — Currently only 3 test files for a complex system
  - [ ] Integration tests for Telegram > Parser > JSONL > MT5 flow
  - [ ] Frontend component tests (React)
  - [ ] Performance/load tests (validate 500+ signals/day claim)
  - [ ] MQL5 EA edge case tests
- [ ] **Add CI test runs** — Run pytest on every PR via GitHub Actions
- [ ] **Add linting/type checking to CI** — mypy, ruff, or flake8 for Python; tsc --noEmit for TypeScript
- [ ] **Clean up TODO/FIXME/HACK comments** — Resolve or remove all development placeholders
- [ ] **Code review pass** — Full review of all modules for dead code, debug prints, development shortcuts

---

## P3 - Code Protection

- [ ] **Distribute compiled `.ex5` only** — Do not ship MQL5 source code to customers
- [ ] **PyInstaller obfuscation** — Make Python source harder to extract from distributed executables
- [ ] **License validation hardening** — Make it non-trivial to bypass the license check (server-side validation, code signing)
- [ ] **Strip development artifacts from release builds** — No test files, no `.github/`, no dev configs

---

## P4 - Legal & Business

- [ ] **Privacy Policy** — Required if collecting any user data or telemetry
- [ ] **Terms of Service** — Customer-facing terms for using the product
- [ ] **Refund Policy** — Clear refund terms (common: 14-day money-back)
- [ ] **EULA** — End User License Agreement shown during installation (can reference existing LICENSE)
- [ ] **Business entity** — Consider registering a company name (currently branded as "R4V3N")
- [ ] **Cookie/GDPR compliance** — If the web dashboard collects data from EU users

---

## P5 - Documentation & Support

- [ ] **API reference docs** — Auto-generate from FastAPI OpenAPI schema
- [ ] **Production deployment guide** — How to run on a VPS (nginx, systemd, Docker)
- [ ] **Docker setup** — Dockerfile + docker-compose for easy deployment
- [ ] **Customer FAQ / Knowledge Base** — Common issues, broker compatibility, troubleshooting
- [ ] **Support channel** — Dedicated email, Discord, or ticket system for paying customers
- [ ] **Video walkthrough** — Setup and usage tutorial for non-technical traders

---

## P6 - Nice to Have

- [ ] **Landing page / marketing site** — Product page with features, pricing, testimonials
- [ ] **Usage analytics dashboard** — Internal metrics on active users, signals processed, common errors
- [ ] **Multi-language support** — UI translations for non-English markets
- [ ] **Referral / affiliate program** — Incentivize existing users to bring new customers
- [ ] **Changelog delivery** — In-app "what's new" notifications on update

---

## Already Done

- [x] Core signal parsing engine (~99% accuracy)
- [x] MT5 Expert Advisor with multi-TP, break-even, risk management
- [x] Three interfaces (Desktop GUI, Web Dashboard, Headless CLI)
- [x] Real-time WebSocket monitoring
- [x] Comprehensive README with architecture diagrams
- [x] CHANGELOG with full version history
- [x] CONTRIBUTING guide and SECURITY policy
- [x] Custom commercial license (well-written, just needs enforcement)
- [x] CI/CD workflows (branch protection, conventional commits, PR checks)
- [x] PyInstaller build specs for Windows executables
- [x] Symbol normalization for broker compatibility
- [x] Sub-200ms latency, production-tested at 500+ signals/day
- [x] `.env` properly gitignored with `.env.example` template on GitHub
