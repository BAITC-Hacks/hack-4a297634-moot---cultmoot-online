# Halyk Voice

Independent voice assistance platform with Russian, Kazakh and English interface, OpenAI speech recognition and a female synthesized voice. It provides conversation history and spoken step-by-step guides. It is not an official Halyk Bank service and has no access to banking accounts.

## Run locally on Windows

1. Create a Python virtual environment: `python -m venv .venv`.
2. Install dependencies: `.venv/Scripts/python.exe -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY` locally.
4. In `frontend`, run `npm ci` and `npm run build`.
5. Run `./start.ps1`, then open http://localhost:8010 and create an account.

`APP_MODE=assistant` is the normal operating mode: information and navigation, without fake balances, synthetic client identifiers, or mock transactions. `APP_MODE=demo` is a legacy test mode and must not be used as an actual bank integration. The internal scenario taxonomy helps classify topics; it does not authorize bank actions.

## Accounts and data

Email/password accounts are stored in SQLite. Passwords are salted scrypt hashes. Conversation text is encrypted with a server-local Fernet key. Users can delete history, change their password and revoke all login sessions. Email address ownership is not verified; Gmail OAuth and password-reset email delivery are not configured.

Back up both `runtime/accounts.sqlite3` and `runtime/history.key` securely. Never publish `.env`, runtime files or backups. A production operator must restrict filesystem permissions and protect backups. See [SECURITY.md](SECURITY.md) for implemented controls and their limits.

## HTTPS deployment

`Dockerfile`, `compose.yaml` and `Caddyfile` provide a single-worker deployment with a non-root application, persistent data and a reverse proxy. Set `PUBLIC_DOMAIN` to a domain you control in the deployment `.env`, configure DNS and make ports 80/443 reachable, then run `docker compose up --build -d`. No application port is published directly. Only the proxy's fixed private address is trusted for forwarded headers. If the subnet conflicts with your server network, change both the subnet/addresses and FORWARDED_ALLOW_IPS together.

These deployment files have not been exercised against a public domain in this workspace. Supply a real bank-approved API and authorization contract before adding banking operations. Infrastructure DDoS protection, email verification, MFA and an independent security assessment remain production rollout tasks.

## Checks

Install `requirements-dev.txt`. Run `.venv/Scripts/python.exe -m unittest tests.test_platform.PlatformTests -v`. Build the frontend, then run `.venv/Scripts/python.exe scripts/check_ui.py` for isolated browser checks using Edge. Set `HV_BROWSER_CHANNEL=chrome` to use Chrome. The UI test creates a temporary database, runs a test server on port 8011 and does not call OpenAI. Screenshots are saved in ignored `reports/`.

Official banking information: https://halykbank.kz/knowledge_base and https://halykbank.kz/knowledge_base/3286.
