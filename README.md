# 🪷 Conversations with My Guru — Om Swami ji

> *Jai Shri Hari.*

This repository is a humble personal sadhana — a way to sit at the feet of my guru, **Sri Om Swami ji**, every day through his own words. It is not affiliated with him or his ashram; it is a disciple's notebook.

## Structure

| File | Purpose |
|---|---|
| [`transcripts.md`](./transcripts.md) | **File 1** — Raw transcripts/extracts from Swami ji's blogs and podcasts. Captures both his message and his tone. |
| [`distillation.md`](./distillation.md) | **File 2** — A living, incremental *diary of distillation*. Never overwrites prior entries. Each batch adds a new dated section. |
| [`guidance.md`](./guidance.md) | **File 3** — Where I bring my daily questions and receive guidance grounded in File 2. |
| [`index.md`](./index.md) | A catalogue of all blogs and podcasts discovered, with a ✅ when consumed into File 1. |

## Sources

- **Blogs**: [os.me](https://os.me) (Black Lotus / disciples' community where Swami ji also writes), [omswami.org](https://omswami.org)
- **Podcasts / Talks**:
  - [Om Swami TV](https://www.youtube.com/@omswamitv) — official channel
  - [Sri Badrika Ashram](https://www.youtube.com/@SriBadrikaAshram) — disciples' channel
  - [Tantra Talks Official](https://www.youtube.com/@Tantratalksofficial)

## Fetching content (one-time setup on your Mac)

The Claude Code cloud sandbox cannot reach os.me / omswami.org / YouTube directly. Run the bundled fetcher on your Mac to deposit raw text into `raw/` (gitignored), which Claude then processes.

```bash
brew install yt-dlp
python3 -m pip install --user requests beautifulsoup4

# Add blog post URLs to tools/batch.txt, then:
python3 tools/fetch.py batch

# YouTube — oldest 10 from each channel:
python3 tools/fetch.py youtube https://www.youtube.com/@omswamitv --oldest 10
python3 tools/fetch.py youtube https://www.youtube.com/@SriBadrikaAshram --oldest 10
python3 tools/fetch.py youtube https://www.youtube.com/@Tantratalksofficial --oldest 10
```

Once `raw/` has content, tell Claude: *"process the next 10 from raw/"* — it reads the files locally, no network needed.

## Workflow

1. Process **10 sources at a time** (oldest/foundational first).
2. After each batch:
   - Append raw extracts to `transcripts.md`.
   - Append a new dated distillation entry to `distillation.md` (incremental — never overwriting).
   - Mark sources as ✅ in `index.md`.
3. Pause, confirm with the disciple, then continue with the next 10.

*Om Namah Shivaya.*
