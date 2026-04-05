# Localization Audit Agent — MCP + Ollama Demo

A demonstration of the **Agent + MCP (Model Context Protocol)** pattern using
local Ollama (`llama3.2`) to audit whether public websites are localized.

## What it demonstrates

```
User question (natural language)
        |
        v
[Intent Parser — llama3.2]   extracts URL + locale from question
        |
        v
[Agent Brain — llama3.2]     decides which MCP tool to call next
        |
        v
[MCP Server — button_classifier]   hosts 6 registered tools
    ├── fetch_page_content          real HTTP fetch, no LLM
    ├── check_locale_support        LLM (llama3.2) analyses URLs/links
    ├── detect_language             LLM (llama3.2) identifies language
    ├── evaluate_localization_quality  LLM quality evaluation
    ├── classify_buttons            LLM button scoring
    └── health_check               Ollama connectivity check
        |
        v
[Synthesizer — llama3.2]     produces plain-English Yes/No answer
```

## Prerequisites

1. **Ollama** installed and running
   ```bash
   ollama serve          # start service
   ollama pull llama3.2  # pull the model
   ```

2. **Python 3.10+**

## Quick Start

```bash
cd button-classifier-mcp

# Create venv and install
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS/Linux

pip install -e .

# Run the agent
python l10n_agent.py "Is amazon.com localized in French?"
python l10n_agent.py "Does apple.com have a Japanese version?"
python l10n_agent.py "Detect the language of this text: Bonjour, bienvenue."

# Or interactive menu
python l10n_agent.py
```

## Example output

```
[Intent Parser] Parsing: 'Does apple.com have a French version?'
  URL    : apple.com
  Locale : fr

[MCP] Tools available: ['classify_buttons', 'health_check', 'detect_language',
                         'check_locale_support', 'evaluate_localization_quality',
                         'fetch_page_content']

[Agent] Thinking (iteration 1)...
[Tool] Calling 'fetch_page_content'  (real HTTP GET to apple.com)
  Result : hreflang_links found, hreflang_includes_target=True

[Guard] hreflang match found — fast-path YES verdict

======= FINAL ANSWER =======
Verdict : YES
Answer  : Yes, apple.com is localized in fr. A hreflang alternate link was found
          for the target locale: https://www.apple.com/befr/. This is the strongest
          signal that the site officially supports this locale.
```

## MCP Tools registered in the server

| Tool | What it does | Uses LLM? |
|------|-------------|-----------|
| `fetch_page_content` | Fetches the live page, extracts html lang, hreflang links, locale URLs, text sample | No — pure HTTP |
| `check_locale_support` | Analyzes URL patterns and links to infer locale support | Yes — llama3.2 |
| `detect_language` | Identifies the language of a text sample | Yes — llama3.2 |
| `evaluate_localization_quality` | Checks for mixed languages, untranslated elements | Yes — llama3.2 |
| `classify_buttons` | Scores button texts for signup/login/checkout intent | Yes — llama3.2 |
| `health_check` | Verifies Ollama is reachable | No |

## Agent flow for "Is X localized in Y?"

1. **Intent parsing** — llama3.2 extracts URL and locale code from the question
2. **Iteration 1** — Agent calls `fetch_page_content(url=X, target_locale=Y)` to get real HTML signals
3. **Hreflang fast-path** — if hreflang alt link for Y is found → immediate YES verdict
4. **Iteration 2** — otherwise Agent calls `check_locale_support` with the fetched links
5. **Synthesis** — llama3.2 produces a 2-4 sentence plain-English answer

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Ollama not responding | `ollama serve` in a separate terminal |
| Model not found | `ollama pull llama3.2` |
| Slow responses | First call loads the model (~10s); subsequent calls are faster |
| Windows encoding error | Already fixed — stdout is reconfigured to UTF-8 at startup |

## Files

```
button-classifier-mcp/
├── l10n_agent.py              # Main entry point — run this
├── mcp_client_demo.py         # Minimal MCP protocol demo (no agent)
├── src/button_classifier/
│   └── server.py              # MCP server with all 6 tools
└── pyproject.toml
```

## License

MIT
