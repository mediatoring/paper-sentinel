# Paper Sentinel

Paper Sentinel is a self-hosted, open-source research radar for arXiv. It scans new papers from selected categories, filters them by your research tags, and optionally uses a **local OpenAI-compatible LLM** to summarize why each paper matters.

It is designed to run without paid LLM API credits. Use LM Studio, Ollama, llama.cpp server, vLLM, or another OpenAI-compatible local endpoint.

Default UI: **http://localhost:5792**

## Features

- Browser configuration; no config file editing required
- arXiv categories: 23 built-in (cs.AI, cs.CL, cs.CV, cs.LG, cs.IR, cs.RO, stat.ML, …) plus any other arXiv category id you type in
- Clickable suggested research tags plus custom tags; custom tags and categories become toggleable chips
- `ANY` / `ALL` tag matching against title + abstract before LLM inference
- Scheduled scanning from every 30 minutes to daily
- Short / medium / long AI summaries
- 2-card, 3-card or table layout, switchable from the toolbar
- Read-later shelf: save any paper for later and switch between all papers and saved ones
- Like / Not interested reactions stored per paper, with Liked and Not interested views
- Full-text search (SQLite FTS5 with stemming) over title, abstract, summary, your notes and PDF text
- Semantic and hybrid search plus "Similar papers" using embeddings from your local LLM server
- Notes and your own tags on every paper
- PDF library: download PDFs into `data/library`, text is extracted and indexed
- Learns from your reactions: a match score ranks new papers and liked/disliked titles inform the LLM summaries
- LLM server monitor: shows whether LM Studio / Ollama is reachable and which models are loaded, with the exact command to start it and one-click Start / Load buttons when the CLI is available locally
- Local OpenAI-compatible LLM support
- Graceful extractive fallback when the LLM is disabled or unavailable
- Basic cross-reference hints against recently stored papers
- Browser notifications
- Optional SMTP email digest
- Optional generic JSON webhook
- Local SQLite database
- RSS feed at `/feed.xml`
- Manual **Scan now** button
- Docker support
- MIT License

## Quick start

### macOS / Linux

```bash
git clone https://github.com/mediatoring/paper-sentinel.git
cd paper-sentinel
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

Open:

```text
http://localhost:5792
```

### Windows PowerShell

```powershell
git clone https://github.com/mediatoring/paper-sentinel.git
cd paper-sentinel
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\run.ps1
```

### Docker

```bash
docker compose up -d --build
```

Then open http://localhost:5792.

When Paper Sentinel itself runs in Docker, a local LLM running on the host is usually reached as `http://host.docker.internal:1234/v1` (LM Studio) or `http://host.docker.internal:11434/v1` (Ollama). The included Compose file maps this host name on Linux as well.

## Search, library and learning

- **Search box** (press `/`): *Text* uses SQLite FTS5 with Porter stemming, so `retrieving` also finds `retrieval`. Quote phrases: `"long context"`. *Semantic* embeds your query with the local embedding model and ranks by cosine similarity. *Hybrid* (default) fuses both with reciprocal rank fusion and falls back to text when embeddings are unavailable.
- **Embeddings** are requested from the same OpenAI-compatible server via `/v1/embeddings`. Leave the model empty to auto-detect the first model whose id contains `embed` (LM Studio: load e.g. `text-embedding-nomic-embed-text-v1.5`). Use *Rebuild embeddings* in Settings after changing the model.
- **Similar** on a card lists the closest stored papers by meaning.
- **Notes and tags** are yours; they are searchable and shown as green badges.
- **PDF library**: *Save PDF* downloads the paper into `data/library/` and indexes its text; by default this also happens when you save or like a paper. Files are served at `/library/<arxiv_id>.pdf`.
- **Match score**: once you like something, every embedded paper gets a score (similarity to the mean of liked papers, pushed away from disliked ones). Sort by *Best match* to see it in action. Liked and disliked titles are also passed to the LLM as preference context for new summaries.

## LLM server monitor

The status bar shows a coloured dot for the local LLM server. When it is offline or a model is not loaded, a banner explains what is wrong and shows the command to fix it, for example:

```text
lms server start --port 1234
lms load openai/gpt-oss-20b -y
```

If Paper Sentinel runs on the same machine as LM Studio (`lms` in PATH or `~/.lmstudio/bin/lms`) or Ollama (`ollama` in PATH), the banner also offers **Start server** and **Load model** buttons that run those commands for you. In Docker the buttons are hidden and you run the command on the host.

## Local LLM setup

Paper Sentinel expects an OpenAI-compatible `/v1/chat/completions` endpoint.

### LM Studio

1. Download and load a local instruct model.
2. Start the Local Server in LM Studio.
3. In Paper Sentinel → Settings use:

```text
Base URL: http://127.0.0.1:1234/v1
Model: local-model
```

If your LM Studio server exposes a specific model identifier, use that instead.

### Ollama

Recent Ollama versions expose an OpenAI-compatible API. Start your model, then use:

```text
Base URL: http://127.0.0.1:11434/v1
Model: <your Ollama model name>
```

Example:

```bash
ollama run qwen3:14b
```

## How scanning works

Paper Sentinel intentionally uses the LLM only after inexpensive filtering:

```text
arXiv categories
      ↓
latest metadata + abstracts
      ↓
local keyword/tag matcher
      ↓
only matching papers
      ↓
local LLM summary + relevance analysis
      ↓
SQLite + dashboard + notifications + RSS
```

This avoids spending inference time on every arXiv paper.

## Data and privacy

Paper Sentinel stores settings, paper metadata, and summaries in `./data/paper_sentinel.db` by default. No LLM content is sent to a paid provider unless you deliberately configure a remote OpenAI-compatible endpoint.

SMTP passwords and optional LLM API keys are currently stored in the local SQLite settings database. Treat the `data/` directory as private.

## Notifications

### Browser

Enable browser notifications in Settings. They work while the Paper Sentinel page is open. `localhost` is treated as a secure context by modern browsers for notification permissions.

### Email

Enable SMTP notifications and fill in host, port, credentials, sender and recipient.

### Webhook

Enable the generic webhook and provide an HTTP(S) URL. Paper Sentinel sends JSON containing a text digest and the new paper records.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
python -m uvicorn app.main:app --host 127.0.0.1 --port 5792 --reload
```

## Scope of v0.1

This first release analyzes arXiv title + abstract. It does not yet download and parse complete PDFs, calculate embedding similarity, or make strong novelty/contradiction claims across the literature. Those are natural next steps, but keeping v0.1 metadata-first makes installation lightweight and avoids unnecessary local inference.

## License

MIT. See [LICENSE](LICENSE).
