# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |
| < latest | :x:               |

We only provide security patches for the latest release. Please keep your installation up to date.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Instead, report vulnerabilities by emailing:

**security@agentforge.dev**

Include:

- A description of the vulnerability
- Steps to reproduce the issue
- The potential impact
- Any suggested fix (optional)

## Response Timeline

| Action | Timeframe |
|--------|-----------|
| Acknowledgment | Within 48 hours |
| Initial assessment | Within 5 business days |
| Fix development | Depends on severity |
| Public disclosure | After fix is released |

## Severity Levels

- **Critical** — Remote code execution, authentication bypass, data exfiltration. Patched ASAP.
- **High** — Privilege escalation, significant data exposure. Patched within 7 days.
- **Medium** — Limited data exposure, denial of service. Patched in next release.
- **Low** — Minor information disclosure, hardening improvements. Addressed as time allows.

## Scope

The following are in scope:

- The AgentForge web application (frontend and backend)
- The AgentForge CLI
- The AgentForge API
- Database schema and RLS policies
- Authentication and authorization logic
- Code execution sandbox (`code_executor` tool)

The following are out of scope:

- Third-party services (Supabase, OpenAI, Vercel, Render)
- Social engineering attacks
- Denial of service via rate limiting (already mitigated)

## Security Best Practices

If you're deploying AgentForge:

- Never commit `.env` files or API keys
- Use Supabase Row Level Security (enabled by default)
- Keep the `code_executor` sandbox restrictions in place
- Rotate API keys regularly via the Settings page
- Use HTTPS in production
