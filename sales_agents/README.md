# Sales agent frameworks (LangGraph)

One shared toolkit, several businesses. Everything runs from the repo root (`neo-cortex`).

| Business | Find targets | Collect public contacts | Outreach |
|---|---|---|---|
| **Corporate gifting** (Ahmedabad/Vadodara) | `companies.csv` (+ built-in list) | `python -m sales_agents.prospecting.graph [medium\|large]` -> `prospects.csv`, `company_contacts.csv` | `python -m sales_agents.outreach.run` |
| **Solitiq - AI training tie-ups with colleges** | `colleges.csv` | `python -m sales_agents.colleges.graph` -> `college_contacts.csv`, `college_targets.csv` | `python -m sales_agents.outreach.run --profile colleges` |

Shared pieces: `prospecting/webscan.py` (public contact scan), `prospecting/search.py` (Tavily + validated website finder),
`outreach/run.py` (capped, opt-out-aware emailer; preview by default, `--send` to really send), `mailer.py`, `llm.py` (AI is off unless `SALES_USE_LLM=1`).

Rules baked in: only public business inboxes, no guessed emails, one email per organisation, 25/day cap, one follow-up after 5 days, STOP replies are honoured.

Add a new business = new `<name>/` folder with a CSV of targets, a role labeller, email templates, and a profile entry in `outreach/run.py`.
