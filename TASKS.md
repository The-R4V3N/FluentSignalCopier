# Fluent Signal Copier - Pre-Launch Tasks

> **Business model:** Self-hosted signal copier (Option C)
> - Software license: €25/month subscription
> - Setup assistance via screen share: €75 one-time
> - Custom parser template (weird signal formats): €30 one-time
> - User brings their own signal provider & broker — we sell the tool, not signals
>
> Current state: ~60-70% ready. Core product is solid, commercialization layer is missing.

---

## P0 - Critical Blockers

These must be fixed before any public release.

- [ ] **Fix license contradiction** — `pyproject.toml` says `"MIT"` but `LICENSE` file is custom restrictive. Change pyproject.toml to `license = "Proprietary"`
- [ ] **Align version numbers** — pyproject.toml says `0.10.0`, README badge says `v0.13.0-beta`. Pick one source of truth and sync everywhere
- [ ] **Implement license key system** — Validate license keys on startup, enforce seat/device limits defined in LICENSE (1 seat, 2 devices, 2 MT5 accounts)
- [ ] **Add payment integration** — Gumroad, Paddle, or LemonSqueezy. Must handle license key delivery on purchase and recurring €25/month billing
- [ ] **Remove `.vscode/` from tracking** — Add to `.gitignore`, remove from git index

---

## P1 - Customer Experience

Required for a professional product launch.

- [ ] **First-run setup wizard** — Guide new users through:
  - Telegram API setup (link to my.telegram.org, explain API ID/hash)
  - Adding their own Telegram signal channel(s)
  - MT5 directory selection
  - Signal format auto-detection test (paste a sample signal, show parsed result)
  - First live signal confirmation
- [ ] **Signal format template library** — Pre-built parser templates by category (not providers):
  - Gold/XAUUSD style signals
  - Forex standard (majors/minors)
  - Crypto (BTC, ETH, etc.)
  - Indices (US30, NAS100, DE40)
  - Custom / Auto-detect (default)
  - User can test their provider's format against templates before going live
- [ ] **Improve error handling** — Replace bare `except Exception:` blocks with structured error types and user-facing messages
- [ ] **Add crash reporting** — Integrate Sentry or similar opt-in crash/error telemetry
- [ ] **Create customer onboarding flow** — Purchase > license key email > download > setup wizard > activation > first signal test
- [ ] **Device fingerprinting** — Implement hardware/machine ID for device limit enforcement
- [ ] **Trial period mechanism** — 7-day free trial with full features so customers can test with their own signal provider before paying
- [ ] **Auto-update system** — Notify users of new versions, ideally with one-click update
- [ ] **"Request format support" button** — If auto-detect fails, user can submit a sample signal for you to add support (€30 upsell or free if common format)

---

## P2 - Quality & Testing

- [ ] **Expand test coverage** — Currently only 3 test files for a complex system
  - [ ] Integration tests for Telegram > Parser > JSONL > MT5 flow
  - [ ] Frontend component tests (React)
  - [ ] Performance/load tests (validate 500+ signals/day claim)
  - [ ] MQL5 EA edge case tests
  - [ ] Parser template tests (one test per format category)
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

- [ ] **Update LICENSE for SaaS model** — Current license says "no SaaS." Update to allow self-hosted subscription use
- [ ] **Privacy Policy** — Required if collecting any user data or telemetry
- [ ] **Terms of Service** — Customer-facing terms, include disclaimer: "not financial advice, not a signal provider, user is responsible for their own trading decisions"
- [ ] **Refund Policy** — Clear refund terms (suggestion: 14-day money-back, no questions asked)
- [ ] **EULA** — End User License Agreement shown during installation
- [ ] **Trading disclaimer** — Prominent "past performance ≠ future results" and "trading involves risk of loss" in app and on website
- [ ] **Business entity** — Consider registering a company name (currently branded as "R4V3N")
- [ ] **Cookie/GDPR compliance** — If the web dashboard collects data from EU users

---

## P5 - Documentation & Support

- [ ] **Customer setup guide** — Step-by-step with screenshots: "How to connect your signal provider"
- [ ] **Broker compatibility list** — Document tested brokers and any quirks (symbol suffixes, etc.)
- [ ] **API reference docs** — Auto-generate from FastAPI OpenAPI schema
- [ ] **Production deployment guide** — How to run on a VPS (nginx, systemd, Docker)
- [ ] **Docker setup** — Dockerfile + docker-compose for easy self-hosting
- [ ] **Customer FAQ / Knowledge Base** — Common issues, "my signals aren't parsing," troubleshooting
- [ ] **Support channel** — Dedicated email or Discord for paying customers
- [ ] **Video walkthrough** — Setup tutorial showing the full flow from purchase to first copied signal

---

## P6 - Marketing & Growth

- [ ] **Landing page / marketing site** — Product page with features, pricing, demo video
- [ ] **Pricing page** — Clear tiers: Free trial (7 days) → €25/month → Setup service (€75)
- [ ] **SEO content** — "How to copy Telegram signals to MT5" blog posts / YouTube
- [ ] **Community** — Discord server for customers to help each other and request format support
- [ ] **Referral program** — Existing users get 1 month free for each referral
- [ ] **Changelog delivery** — In-app "what's new" notifications on update
- [ ] **Collect testimonials** — Early users / beta testers feedback for the landing page

---

## Already Done

- [x] Core signal parsing engine (~99% accuracy, auto-detects most formats)
- [x] MT5 Expert Advisor with multi-TP, break-even, risk management
- [x] Three interfaces (Desktop GUI, Web Dashboard, Headless CLI)
- [x] Real-time WebSocket monitoring
- [x] LONG/SHORT support + crypto symbol aliases
- [x] EA settings management via web dashboard
- [x] Comprehensive README with architecture diagrams
- [x] CHANGELOG with full version history
- [x] CONTRIBUTING guide and SECURITY policy
- [x] Custom commercial license (needs updates for subscription model)
- [x] CI/CD workflows (branch protection, conventional commits, PR checks)
- [x] PyInstaller build specs for Windows executables
- [x] Symbol normalization for broker compatibility (prefix/suffix handling)
- [x] Sub-200ms latency, production-tested at 500+ signals/day
- [x] `.env` properly gitignored with `.env.example` template on GitHub
- [x] Dependabot vulnerabilities resolved
