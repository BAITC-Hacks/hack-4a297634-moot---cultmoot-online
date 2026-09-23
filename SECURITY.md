# Security and latency controls

Halyk Voice is an independent assistance platform, not a certified banking service. The default assistant mode does not execute simulated or real banking operations. Legacy demo mode is available only for explicit testing.

- Passwords use salted scrypt (N=32768, r=8, p=3); older hashes are upgraded after successful login.
- Login quotas persist in SQLite and apply to email and IP. Hashing concurrency is limited.
- Session cookies are HttpOnly/SameSite=Strict; production requires HTTPS and Secure cookies. Set ALLOWED_HOSTS and HTTPS ALLOWED_ORIGINS explicitly.
- Conversation text is encrypted with Fernet. Existing plaintext rows migrate at startup. Keep runtime/history.key with protected backups of the database: losing it makes history unreadable. The key is local to this server; a compromise of the server account can expose it. Runtime files must never be committed.
- History, audio and traces are owner-scoped. Deleting history clears cached traces, audio and conversation context. Each account retains at most 2000 messages.
- State-changing requests require approved Origin and session CSRF tokens. WebSocket connections require an approved Origin and a valid account/session.
- Body sizes and receive duration are limited; model, audio and authentication concurrency are bounded. Direct Realtime token issuance is disabled.
- CSP, anti-framing and same-origin resource headers are enabled. SQL uses bound parameters. Submitted passwords are not echoed in validation errors.
- Model decisions still undergo catalog validation and explicit confirmation before mock mutations. The compact model response has 11 fields; derived policy fields are calculated on the server. A single model request has an 8-second total deadline (ROUTER_DEADLINE_SECONDS). Timeouts return clarification, not an invented answer.
- Unambiguous exact catalog examples can select a safe initial information/slot-collection action locally. This shortcut never extracts identifiers or executes a mutation, and is disabled for ongoing scenarios and pending confirmations.
- Completed TTS responses are cached only in the owning session, capped at 512 KiB, and expire with the audio entry. Repeat playback avoids a second OpenAI request.

Deployment: keep one application worker while in-memory routing sessions and limits are used; place HTTPS and connection/DDoS controls at a trusted reverse proxy. Do not trust arbitrary forwarded headers. Use a shared session/rate-limit store before scaling across workers. Email verification, MFA, external penetration testing and infrastructure DDoS protection are not implemented by this release. Password changes revoke other login sessions; users can also revoke all devices explicitly.

Run checks: `.venv/Scripts/python.exe -m unittest discover -s tests -p test_upgrade.py -v` and `npm run build` from frontend.
