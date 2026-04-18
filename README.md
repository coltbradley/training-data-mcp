# Training Data MCP Server

![Training Data MCP Server](docs/heading.png)

An MCP (Model Context Protocol) server that gives Claude access to your training data from **Intervals.icu**.

> Repo is `intervals-icu-mcp`. The published Docker image is `ghcr.io/coltbradley/training-data-mcp`.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## What you get

- **48 tools** across 9 categories
- **1 MCP resource** — athlete profile for ongoing context
- **6 MCP prompts** — canned queries for common analyses
- Runs locally over stdio **or** remotely over HTTP (Docker)

---

## Quick start (easiest path)

You need: Python 3.11+, [`uv`](https://docs.astral.sh/uv/getting-started/installation/), and your Intervals.icu API key.

```bash
git clone https://github.com/coltbradley/intervals-icu-mcp.git
cd intervals-icu-mcp
make setup
```

`make setup` installs dependencies and walks you through entering:

1. Your Intervals.icu **API key** (from [intervals.icu/settings](https://intervals.icu/settings) → Developer)
2. Your Intervals.icu **athlete ID** (from your profile URL, e.g. `i123456`)

Then add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "training-data": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/ABSOLUTE/PATH/TO/intervals-icu-mcp",
        "intervals-icu-mcp"
      ]
    }
  }
}
```

Restart Claude Desktop. Ask "show my activities from the last 7 days". Done.

---

## Alternative: always-on HTTP server (Docker)

For running on a NAS, home server, or anywhere you want persistent remote access.

```bash
cp .env.example .env
# edit .env with your credentials
docker compose up -d
```

The server listens on `http://localhost:8080/mcp` with a health endpoint at `/health`.

Claude Desktop config:

```json
{
  "mcpServers": {
    "training-data": {
      "type": "url",
      "url": "http://<host>:8080/mcp"
    }
  }
}
```

**TrueNAS SCALE:** paste `docker-compose.truenas.yml` into Apps → Discover → Install via YAML. Set env vars in the TrueNAS UI. Watchtower auto-updates the container every 5 minutes when a new `:latest` image publishes.

---

## Configuration

All config lives in `.env` (or container env vars).

| Variable                   | Required | Purpose                                      |
| -------------------------- | -------- | -------------------------------------------- |
| `INTERVALS_ICU_API_KEY`    | yes      | Intervals.icu API key (Settings → Developer) |
| `INTERVALS_ICU_ATHLETE_ID` | yes      | Your athlete ID, e.g. `i123456`              |
| `MCP_TRANSPORT`            | optional | `stdio` (default) or `http`                  |
| `PORT`                     | optional | HTTP port (default `8080`)                   |

---

## Usage examples

Use natural language — Claude picks the right tool.

```
"How's my fitness trending? Show CTL and TSB."
"Find all my threshold workouts in the last 60 days."
"Deep dive on yesterday's ride — power, HR, intervals, best efforts."
"What's my 20-minute power? Estimate my FTP."
"How was my recovery this week?"
"Compare my planned TSS to actual TSS for the last 2 weeks."
```

### Built-in prompts

Accessible via prompt suggestions in Claude:

- `analyze-recent-training` — training analysis over any period
- `performance-analysis` — power/HR/pace curves + zones
- `activity-deep-dive` — streams, intervals, best efforts for one activity
- `recovery-check` — wellness + training load readiness
- `training-plan-review` — evaluate upcoming plan
- `plan-training-week` — AI-assisted weekly plan creation

---

## Tool catalog

### Activities (10)

`get-recent-activities` · `get-activity-details` · `search-activities` · `search-activities-full` · `get-activities-around` · `update-activity` · `delete-activity` · `download-activity-file` · `download-fit-file` · `download-gpx-file`

### Activity analysis (8)

`get-activity-streams` · `get-activity-intervals` · `get-best-efforts` · `search-intervals` · `get-power-histogram` · `get-hr-histogram` · `get-pace-histogram` · `get-gap-histogram`

### Athlete (2)

`get-athlete-profile` · `get-fitness-summary`

### Wellness (3)

`get-wellness-data` · `get-wellness-for-date` · `update-wellness`

### Events / calendar (9)

`get-calendar-events` · `get-upcoming-workouts` · `get-event` · `create-event` · `update-event` · `delete-event` · `bulk-create-events` · `bulk-delete-events` · `duplicate-event`

### Performance / curves (3)

`get-power-curves` · `get-hr-curves` · `get-pace-curves`

### Workout library (2)

`get-workout-library` · `get-workouts-in-folder`

### Gear (6)

`get-gear-list` · `create-gear` · `update-gear` · `delete-gear` · `create-gear-reminder` · `update-gear-reminder`

### Sport settings (5)

`get-sport-settings` · `update-sport-settings` · `apply-sport-settings` · `create-sport-settings` · `delete-sport-settings`

### Resource

`intervals-icu://athlete/profile` — current fitness metrics and sport settings

---

## Common tasks

```bash
make setup      # install + interactive auth
make run        # run server over stdio
make test       # run tests
make lint       # ruff + pyright
make format     # auto-fix style
make docker/build
make help       # list all targets
```

---

## Troubleshooting

- **"Intervals.icu credentials not configured"** — run `make auth`.
- **Docker health check failing** — `curl http://localhost:8080/health` should return `{"status": "ok", "version": "..."}`.
- **Claude Desktop can't find the server** — make sure the path in the config is absolute, and restart Claude Desktop fully.

---

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

Not affiliated with Intervals.icu. All trademarks belong to their respective owners.
