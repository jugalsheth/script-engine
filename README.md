# Script Engine

Automated weekly video script generation for personal content creators. Runs on a GitHub Actions cron schedule every **Sunday at 8:17am ET**, researches trending topics, filters for safety, matches against your knowledge base, generates 5–10 ready-to-record scripts, and delivers them via Telegram.

## How It Works

```
Research (Perplexity) → Safety Filter → Knowledge Matcher → Script Generator (Claude) → Telegram
```

1. **Research** — One batched Perplexity Sonar query (low search context) + manual overrides
2. **Safety Filter** — Blocklist + Claude Haiku batch check for H1B-safe content
3. **Matcher** — Scores topics against your knowledge domains
4. **Generator** — Creates 8 scripts via Claude Sonnet using your voice profile
5. **Deliver** — Sends formatted scripts to your Telegram chat

## Quick Start

### 1. Clone and install locally

```bash
cd script-engine
pip install -r requirements.txt
```

### 2. Create a `.env` file (local testing)

```bash
ANTHROPIC_API_KEY=sk-ant-...
PERPLEXITY_API_KEY=pplx-...
TELEGRAM_BOT_TOKEN=123456789:ABC...
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. Run locally

```bash
python main.py
```

---

## Telegram Setup

### Get a bot token

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow prompts to name your bot
3. Copy the **HTTP API token** — this is `TELEGRAM_BOT_TOKEN`

### Get your chat ID

1. Message your new bot (send any text)
2. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find `"chat":{"id":123456789}` in the JSON — that number is `TELEGRAM_CHAT_ID`

For a group chat, add the bot to the group and use the group's chat ID from the same endpoint.

---

## GitHub Actions Setup

### Push the repository

Push the contents of `script-engine/` as your GitHub repository root (or set `working-directory: script-engine` in the workflow if nested).

### Add secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | From [console.anthropic.com](https://console.anthropic.com) |
| `PERPLEXITY_API_KEY` | From [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api) |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Your personal chat ID |

### Manual trigger

1. Go to **Actions** tab in your repo
2. Select **Generate Weekly Scripts**
3. Click **Run workflow**

The cron schedule runs automatically every Sunday at 8:17am ET (`17 12 * * 0` UTC).

---

## Config Files

All config lives in `config/`:

| File | Purpose |
|------|---------|
| `voice_profile.txt` | System prompt for script generation — your voice, tone, structure rules, anonymization, and safety rules |
| `territories.txt` | Content territories (Tech Made Simple, Career + Money, etc.) used to tag scripts |
| `blocklist.txt` | Terms that cause topics to be dropped by the first safety layer (one per line) |
| `topics_override.txt` | Manual topics for this week — one per line. Leave instructional lines; add your topics below them |

### Adding manual topics

Edit `config/topics_override.txt` and add one topic per line:

```
How to negotiate a salary offer in tech
What AI engineers actually do all day
```

Manual topics are tagged `estimated_virality: manual` and always included in research output.

---

## Estimated Monthly Cost

Based on weekly runs (4× per month):

| Service | Usage per run | Est. cost/run | Monthly (4 runs) |
|---------|---------------|---------------|------------------|
| Perplexity Sonar | 1 batched query (low context) | ~$0.005 | ~$0.02 |
| Claude Haiku | 1 batch safety check | ~$0.01 | ~$0.04 |
| Claude Sonnet | 8 scripts × ~1.5K tokens | ~$0.40 | ~$1.60 |
| Telegram | Free | $0 | $0 |
| GitHub Actions | ~2 min/run, public repo free | $0 | $0 |

**Estimated total: ~$1.40–$2.00/month** (Perplexity is now ~80% cheaper)

Costs vary with topic count, script length, and API pricing changes.

### Perplexity cost controls

Perplexity charges a **per-request search fee** ($5/1,000 at low context) — not per topic. The engine is optimized for this:

- **1 batched query** instead of 5 parallel calls (~$0.005/run vs ~$0.025)
- **`search_context_size: low`** — cheapest tier; enough for topic ideation
- **`max_tokens: 2000`** — caps output size
- **Cost logged** each run in GitHub Actions output

To skip Perplexity entirely (free — uses evergreen fallbacks + manual topics):

```bash
PERPLEXITY_SKIP=true python main.py
```

Add `PERPLEXITY_SKIP=true` to GitHub Actions env if you prefer manual topics only.

---

## Error Handling

- **Perplexity fails** → Falls back to 5 evergreen topics + manual overrides
- **Single script fails** → Skips that script, continues with remaining topics
- **Claude Haiku safety check fails** → Continues with blocklist-filtered topics only
- **Telegram message too long** → Automatically splits into multiple messages

---

## Project Structure

```
script-engine/
├── .github/workflows/generate_scripts.yml
├── config/
│   ├── voice_profile.txt
│   ├── topics_override.txt
│   ├── territories.txt
│   └── blocklist.txt
├── src/
│   ├── research.py
│   ├── matcher.py
│   ├── safety_filter.py
│   ├── generator.py
│   └── deliver.py
├── main.py
├── requirements.txt
└── README.md
```

---

## License

Personal use. Built for Jugal Sheth's content workflow.
