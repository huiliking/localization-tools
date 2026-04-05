"""
Localization Audit Agent

An agent that uses Ollama (llama3.2) to decide which MCP tools to call
for auditing website localization.

Agent + MCP pattern:
  - Ollama #1 (Agent brain): parses user intent, decides which tool to call next
  - Ollama #2 (Tool execution): inside MCP server for classify_buttons,
    detect_language, check_locale_support, evaluate_localization_quality
  - MCP tool: fetch_page_content (real HTTP fetch, no LLM needed)

Usage:
    python l10n_agent.py
    python l10n_agent.py "Is amazon.com localized in French?"
    python l10n_agent.py "Does stripe.com support Japanese?"
"""

# ---------------------------------------------------------------------------
# Fix Windows GBK / non-UTF-8 console encoding BEFORE any print() calls
# ---------------------------------------------------------------------------
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import json
import re
import httpx
from dataclasses import dataclass, field
from typing import Optional

# MCP SDK imports
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ============================================================================
# Configuration
# ============================================================================

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2:latest"
SERVER_MODULE = "button_classifier.server"

MAX_ITERATIONS = 6   # guard against infinite agent loops


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class AgentState:
    task: str
    target_url: str
    target_locale: str
    iterations: int = 0
    tool_results: list = field(default_factory=list)
    final_answer: str = ""


# ============================================================================
# Ollama Helper
# ============================================================================

async def call_ollama(prompt: str, temperature: float = 0.1) -> str:
    """Call local Ollama LLM and return raw response text."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": 1024},
            },
        )
        resp.raise_for_status()
        return resp.json()["response"]


def extract_json(text: str) -> Optional[dict]:
    """Extract the first JSON object from an LLM response."""
    # Direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Markdown fenced block
    for pattern in (r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass
    # Bare JSON object
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


# ============================================================================
# Step 0 – Intent Parsing
# ============================================================================

async def parse_user_intent(user_input: str) -> tuple[str, str, str]:
    """
    Use llama3.2 to extract (url, locale_code, task_description) from
    a natural-language question like 'Is amazon.com localized in French?'.

    Returns:
        url          – e.g. "amazon.com"
        locale       – e.g. "fr" or "fr-ca"
        task_desc    – cleaned task description for the agent prompt
    """
    prompt = f"""You are a localization audit assistant. Extract structured information from this user question.

User question: "{user_input}"

Locale name → code mapping (examples):
  French / francais / français         → fr
  French Canadian / francais canadien  → fr-ca
  Spanish / espanol / español          → es
  Spanish (Spain)                      → es-ES
  German / deutsch                     → de
  Japanese                             → ja
  Chinese / mandarin                   → zh
  Portuguese                           → pt
  Brazilian Portuguese                 → pt-br
  Italian / italiano                   → it
  Korean                               → ko
  Arabic                               → ar

Respond with ONLY valid JSON, no prose:
{{
  "url": "<website domain or full URL, e.g. amazon.com>",
  "locale": "<2-5 char locale code, e.g. fr or fr-ca>",
  "task": "<one-sentence rephrasing of the question suitable as an audit task>"
}}

JSON:"""

    try:
        response = await call_ollama(prompt)
        result = extract_json(response)
        if result:
            url = result.get("url", "").strip()
            locale = result.get("locale", "fr").strip()
            task = result.get("task", user_input).strip()
            # Validate: the URL must actually appear in the original input
            # to prevent the LLM from hallucinating placeholder domains
            url_base = re.sub(r"^https?://(?:www\.)?", "", url).rstrip("/")
            if url_base and url_base not in user_input and url_base.replace("www.", "") not in user_input:
                url = ""  # LLM fabricated a URL; discard it
            return url, locale, task
    except Exception as e:
        print(f"  [intent parser] Warning: {e}")

    # Fallback: simple regex extraction
    url_match = re.search(
        r"(?:https?://)?([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+\.[a-zA-Z]{2,})", user_input
    )
    locale_map = {
        "french canadian": "fr-ca",
        "french": "fr", "français": "fr", "francais": "fr",
        "spanish": "es", "español": "es",
        "german": "de", "deutsch": "de",
        "japanese": "ja",
        "chinese": "zh",
        "portuguese": "pt",
        "italian": "it",
        "korean": "ko",
        "arabic": "ar",
    }
    locale = "fr"
    lower = user_input.lower()
    for name, code in locale_map.items():
        if name in lower:
            locale = code
            break
    url = url_match.group(1) if url_match else ""
    return url, locale, user_input


# ============================================================================
# Agent Prompt
# ============================================================================

def build_agent_prompt(state: AgentState, available_tools: list[dict]) -> str:
    tools_desc = []
    for t in available_tools:
        props = t.get("inputSchema", {}).get("properties", {})
        params = ", ".join(props.keys()) if props else "none"
        tools_desc.append(f"  - {t['name']}: {(t['description'] or '')[:120]}... (params: {params})")
    tools_text = "\n".join(tools_desc)

    if state.tool_results:
        results_text = "\n".join(
            f"  {i+1}. [{r['tool']}] {json.dumps(r['result'])[:300]}"
            for i, r in enumerate(state.tool_results)
        )
    else:
        results_text = "  (none yet)"

    tools_called = [r["tool"] for r in state.tool_results]

    return f"""You are a Localization Audit Agent. Decide the NEXT single action to answer the task.

TASK: {state.task}
TARGET URL: {state.target_url}
TARGET LOCALE: {state.target_locale}
ITERATION: {state.iterations + 1}/{MAX_ITERATIONS}

AVAILABLE TOOLS:
{tools_text}

TOOLS ALREADY CALLED (do NOT repeat): {tools_called if tools_called else "none"}

TOOL RESULTS SO FAR:
{results_text}

TARGET URL is: {"SET to " + state.target_url if state.target_url else "NOT SET (no website in the question)"}

TOOL SELECTION RULES (follow EXACTLY in order):

A. If TARGET URL is NOT SET (empty):
   - NEVER call fetch_page_content (there is no URL to fetch)
   - If the task asks to detect language of a text sample → call detect_language
   - If the task asks about localization quality or mixed-language text → call evaluate_localization_quality
   - If the task asks about button classification → call classify_buttons

B. If TARGET URL IS SET:
   1. Call fetch_page_content FIRST (url=target_url, target_locale=target_locale)
   2. After fetch returns, call the appropriate analysis tool:
      - For locale support questions → check_locale_support
      - For language detection → detect_language (using the text_sample from fetch)
      - For quality evaluation → evaluate_localization_quality
   3. After one analysis tool → give final_answer

NEVER call fetch_page_content with a made-up URL like "example.com".
NEVER call the same tool twice.

Respond with ONLY ONE of these JSON formats:

Call a tool:
{{
  "action": "call_tool",
  "tool_name": "<tool name>",
  "arguments": {{<key-value pairs matching the tool's params exactly>}},
  "reasoning": "<one sentence>"
}}

Give final answer:
{{
  "action": "final_answer",
  "verdict": "YES/NO/PARTIAL",
  "answer": "<2-4 sentence human-readable answer for the user>",
  "reasoning": "<one sentence summary>"
}}

JSON RESPONSE:"""


# ============================================================================
# Agent Decision
# ============================================================================

async def agent_decide(state: AgentState, available_tools: list[dict]) -> dict:
    prompt = build_agent_prompt(state, available_tools)
    print(f"\n[Agent] Thinking (iteration {state.iterations + 1})...")

    try:
        raw = await call_ollama(prompt)
    except httpx.TimeoutException:
        print("  [Agent] Ollama timeout — using fallback")
        return _fallback_decision(state)

    decision = extract_json(raw)
    if not decision:
        print(f"  [Agent] Could not parse response, using fallback")
        print(f"  [Agent] Raw: {raw[:300]}")
        return _fallback_decision(state)

    return decision


def _fallback_decision(state: AgentState) -> dict:
    """Rule-based fallback when the LLM response can't be parsed."""
    tools_called = {r["tool"] for r in state.tool_results}

    # No URL: do text analysis
    if not state.target_url and "detect_language" not in tools_called:
        return {
            "action": "call_tool",
            "tool_name": "detect_language",
            "arguments": {
                "text_sample": state.task[:800],
                "expected_locale": state.target_locale,
            },
            "reasoning": "Fallback: no URL given, analyzing text directly",
        }

    if "fetch_page_content" not in tools_called and state.target_url:
        return {
            "action": "call_tool",
            "tool_name": "fetch_page_content",
            "arguments": {"url": state.target_url, "target_locale": state.target_locale},
            "reasoning": "Fallback: fetching page first",
        }

    if "fetch_page_content" in tools_called and "check_locale_support" not in tools_called:
        fetch_result = next(
            (r["result"] for r in state.tool_results if r["tool"] == "fetch_page_content"), {}
        )
        return {
            "action": "call_tool",
            "tool_name": "check_locale_support",
            "arguments": {
                "page_url": state.target_url,
                "available_links": fetch_result.get("locale_links", []),
                "target_locale": state.target_locale,
            },
            "reasoning": "Fallback: checking locale support with fetched links",
        }

    if state.tool_results:
        results_summary = "; ".join(
            f"{r['tool']}: {json.dumps(r['result'])[:200]}" for r in state.tool_results
        )
        return {
            "action": "final_answer",
            "verdict": "PARTIAL",
            "answer": f"Analysis results: {results_summary[:400]}",
            "reasoning": "Fallback synthesized from tool results",
        }

    return {
        "action": "call_tool",
        "tool_name": "health_check",
        "arguments": {},
        "reasoning": "Fallback: health check",
    }


# ============================================================================
# Synthesize Final Answer from Tool Results
# ============================================================================

async def synthesize_answer(state: AgentState) -> dict:
    """Ask llama3.2 to synthesize a clear Yes/No answer from all tool results."""
    results_text = "\n".join(
        f"[{r['tool']}]: {json.dumps(r['result'])[:500]}"
        for r in state.tool_results
    )

    prompt = f"""You are a Localization Audit Agent answering a user question about website localization.

USER QUESTION: {state.task}
WEBSITE: {state.target_url}
TARGET LOCALE: {state.target_locale}

EVIDENCE COLLECTED BY TOOLS:
{results_text}

Using the evidence above AND your own knowledge about the website, give a clear, useful answer.

Important notes:
- Many large websites (Amazon, Netflix, etc.) use REGIONAL DOMAINS (e.g. amazon.fr for French)
  rather than path-based locale URLs. If no locale links were found on the base domain, consider
  whether the site is known to have a regional domain for the target locale.
- The html_lang attribute tells you what language the fetched page is in.
- hreflang_includes_target=true is strong evidence of locale support.
- locale_supported=false with confidence=low means the tool could not find direct evidence —
  it does NOT definitively mean the site has no French version.

Write 2-4 plain English sentences. Start with "Yes", "No", or "Partially" based on your verdict.
State what evidence was found and what the user should check if uncertain.

Respond with ONLY this JSON (no prose outside the JSON):
{{
  "action": "final_answer",
  "verdict": "YES/NO/PARTIAL",
  "answer": "<2-4 sentence plain-English answer starting with Yes/No/Partially>",
  "reasoning": "<one sentence: key evidence>"
}}

JSON:"""

    try:
        raw = await call_ollama(prompt, temperature=0.2)
        result = extract_json(raw)
        if result and result.get("answer"):
            return result
    except Exception:
        pass

    # Structured hard fallback — pull signals from tool results
    signals = []
    verdict = "NO"
    for r in state.tool_results:
        res = r.get("result", {})
        if not isinstance(res, dict):
            continue
        if res.get("hreflang_includes_target"):
            signals.append(f"hreflang link found for {state.target_locale}")
            verdict = "YES"
        if res.get("locale_supported"):
            signals.append(f"locale support confirmed by URL analysis")
            verdict = "YES"
        if res.get("html_lang") and res.get("html_lang") != "en":
            signals.append(f"page HTML lang is {res.get('html_lang')}")
        if res.get("matches_expected"):
            signals.append("page language matches expected locale")
            verdict = "YES"
        if res.get("verdict") == "PASS":
            verdict = "YES"

    if not signals:
        signals = [
            "no hreflang links found on the fetched page",
            "site may use regional domains (e.g. separate .fr domain)",
        ]

    answer = (
        f"{'Yes' if verdict == 'YES' else 'No, based on available signals'}, "
        f"{state.target_url} {'appears to support' if verdict == 'YES' else 'did not show clear evidence of'} "
        f"the {state.target_locale} locale. "
        f"Evidence: {'; '.join(signals)}. "
        f"Note: Sites using regional domains (e.g. amazon.fr) may not show locale links on the base domain."
        if verdict == "NO" else
        f"Yes, {state.target_url} supports the {state.target_locale} locale. "
        f"Evidence: {'; '.join(signals)}."
    )

    return {
        "action": "final_answer",
        "verdict": verdict,
        "answer": answer,
        "reasoning": "; ".join(signals[:2]) if signals else "synthesized from tool results",
    }


# ============================================================================
# Main Agent Loop
# ============================================================================

async def run_agent(task: str, target_url: str, target_locale: str) -> AgentState:
    print("=" * 70)
    print("  LOCALIZATION AUDIT AGENT")
    print("=" * 70)
    print(f"\nTask:   {task}")
    print(f"URL:    {target_url or '(not specified)'}")
    print(f"Locale: {target_locale}")

    state = AgentState(
        task=task,
        target_url=target_url,
        target_locale=target_locale,
    )

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", SERVER_MODULE],
        env=None,
    )

    print("\n[MCP] Connecting to MCP server...")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("  [MCP] Connected")

            tools_resp = await session.list_tools()
            available_tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.inputSchema,
                }
                for t in tools_resp.tools
            ]
            print(f"  [MCP] Tools available: {[t['name'] for t in available_tools]}")

            # ----------------------------------------------------------------
            # Agent loop
            # ----------------------------------------------------------------
            while state.iterations < MAX_ITERATIONS:
                decision = await agent_decide(state, available_tools)
                state.iterations += 1

                action = decision.get("action")
                # Normalize: LLM sometimes puts tool name directly in "action"
                tool_names = {t["name"] for t in available_tools}
                if action not in ("call_tool", "final_answer") and action in tool_names:
                    decision["tool_name"] = action
                    decision["action"] = "call_tool"
                    action = "call_tool"

                tools_called = {r["tool"] for r in state.tool_results}

                # Guard: agent wants to skip web fetch on a URL task
                # Only enforce when there's a real URL and no tools called yet
                if (
                    action == "final_answer"
                    and state.target_url
                    and "fetch_page_content" not in tools_called
                    and not tools_called  # only on very first step
                ):
                    print("  [Guard] Agent skipped fetch — forcing fetch_page_content first")
                    decision = {
                        "action": "call_tool",
                        "tool_name": "fetch_page_content",
                        "arguments": {
                            "url": state.target_url,
                            "target_locale": state.target_locale,
                        },
                        "reasoning": "Guard: must fetch page before giving final answer",
                    }
                    action = "call_tool"

                # Guard: agent wants to repeat a tool
                if action == "call_tool" and decision.get("tool_name") in tools_called:
                    repeated = decision.get("tool_name")
                    print(f"  [Guard] Agent tried to repeat '{repeated}'")
                    # If fetch done but locale check not yet done, redirect there
                    if (
                        "fetch_page_content" in tools_called
                        and "check_locale_support" not in tools_called
                    ):
                        fetch_result = next(
                            (r["result"] for r in state.tool_results
                             if r["tool"] == "fetch_page_content"),
                            {},
                        )

                        # If fetch itself errored, pivot to text-based analysis
                        if fetch_result.get("error"):
                            print("  [Guard] Fetch failed — pivoting to text analysis")
                            decision = {
                                "action": "call_tool",
                                "tool_name": "detect_language",
                                "arguments": {
                                    "text_sample": state.task,
                                    "expected_locale": state.target_locale,
                                },
                                "reasoning": "Fetch failed; attempting text-based language detection",
                            }
                            action = "call_tool"
                        # Fast path: hreflang already confirms target locale
                        elif fetch_result.get("hreflang_includes_target"):
                            hreflang_match = fetch_result.get("hreflang_match_detail", {})
                            locale_url = (hreflang_match or {}).get("href", "")
                            print("  [Guard] hreflang match found — fast-path YES verdict")
                            decision = {
                                "action": "final_answer",
                                "verdict": "YES",
                                "answer": (
                                    f"Yes, {state.target_url} is localized in "
                                    f"{state.target_locale}. "
                                    f"A hreflang alternate link was found for the target locale"
                                    f"{': ' + locale_url if locale_url else ''}. "
                                    f"This is the strongest signal that the site officially "
                                    f"supports this locale."
                                ),
                                "reasoning": f"hreflang alternate link found for {state.target_locale}",
                            }
                            action = "final_answer"
                        else:
                            # Combine locale_links (from <a> tags) + hreflang hrefs
                            # (from <link> tags) so check_locale_support has full context
                            hreflang_hrefs = [
                                lk.get("href", "")
                                for lk in fetch_result.get("hreflang_links", [])
                                if lk.get("href")
                            ]
                            all_links = list(
                                set(fetch_result.get("locale_links", []) + hreflang_hrefs)
                            )
                            print("  [Guard] Redirecting to check_locale_support")
                            decision = {
                                "action": "call_tool",
                                "tool_name": "check_locale_support",
                                "arguments": {
                                    "page_url": state.target_url,
                                    "available_links": all_links,
                                    "target_locale": state.target_locale,
                                },
                                "reasoning": "Guard redirect: locale check after page fetch",
                            }
                            action = "call_tool"
                    else:
                        # Both fetch + locale check done → synthesize now
                        print("  [Guard] Sufficient data collected — synthesizing final answer")
                        decision = await synthesize_answer(state)
                        action = "final_answer"

                # Proactive check: if we have a successful domain analysis result,
                # force final_answer rather than letting the agent keep spinning
                if action == "call_tool":
                    domain_tools = {
                        "check_locale_support", "detect_language",
                        "evaluate_localization_quality", "classify_buttons"
                    }
                    successful_domain = any(
                        r["tool"] in domain_tools and not r["result"].get("error")
                        for r in state.tool_results
                    )
                    if successful_domain:
                        print(
                            "  [Guard] Domain analysis already done — synthesizing final answer"
                        )
                        decision = await synthesize_answer(state)
                        action = "final_answer"

                # ---- Final answer ----
                if action == "final_answer":
                    state.final_answer = decision.get("answer", "")
                    verdict = decision.get("verdict", "N/A")
                    reasoning = decision.get("reasoning", "")

                    print(f"\n{'=' * 70}")
                    print("  FINAL ANSWER")
                    print(f"{'=' * 70}")
                    print(f"\n  Verdict : {verdict}")
                    print(f"\n  Answer  : {state.final_answer}")
                    print(f"\n  Evidence: {reasoning}")
                    break

                # ---- Call tool ----
                elif action == "call_tool":
                    tool_name = decision.get("tool_name", "")
                    arguments = decision.get("arguments", {})
                    reasoning = decision.get("reasoning", "")

                    print(f"\n[Tool] Calling '{tool_name}'")
                    print(f"  Reason : {reasoning}")
                    print(f"  Args   : {json.dumps(arguments)[:120]}")

                    try:
                        result = await session.call_tool(tool_name, arguments)
                        result_text = next(
                            (c.text for c in result.content if c.type == "text"), ""
                        )
                        try:
                            result_parsed = json.loads(result_text)
                        except Exception:
                            result_parsed = {"raw": result_text[:500]}

                        print(f"  Result : {json.dumps(result_parsed)[:200]}")
                        state.tool_results.append(
                            {"tool": tool_name, "arguments": arguments, "result": result_parsed}
                        )

                    except Exception as exc:
                        print(f"  [ERROR] {exc}")
                        state.tool_results.append(
                            {"tool": tool_name, "arguments": arguments, "result": {"error": str(exc)}}
                        )

                else:
                    print(f"  [Agent] Unknown action: {action!r} — stopping")
                    break

            if state.iterations >= MAX_ITERATIONS and not state.final_answer:
                print(f"\n[Agent] Max iterations reached — synthesizing answer")
                final = await synthesize_answer(state)
                state.final_answer = final.get("answer", "")
                print(f"\nVerdict: {final.get('verdict')}\nAnswer: {state.final_answer}")

    # Summary
    print(f"\n{'=' * 70}")
    print("  AGENT SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Iterations : {state.iterations}")
    print(f"  Tools used : {[r['tool'] for r in state.tool_results]}")

    return state


# ============================================================================
# Entry Point
# ============================================================================

EXAMPLE_TASKS = [
    "Is amazon.com localized in French?",
    "Does stripe.com support Japanese?",
    "Is netflix.com available in Spanish?",
    "Check if github.com has a French version",
    "Detect the language of this text: 'Bienvenue sur notre site. Créez un compte pour commencer.'",
    "Evaluate localization quality for: ['Sign up', 'Connexion', 'Aide', 'Contact']  (target: fr-ca)",
]


async def main():
    print("""
+----------------------------------------------------------------------+
|           LOCALIZATION AUDIT AGENT                                   |
|           Agent + MCP + Ollama (llama3.2) Demo                       |
+----------------------------------------------------------------------+
""")

    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
    else:
        print("Example questions:")
        for i, ex in enumerate(EXAMPLE_TASKS, 1):
            print(f"  {i}. {ex}")
        print(f"\nEnter a question (or 1-{len(EXAMPLE_TASKS)} for an example):")
        user_input = input("> ").strip()
        if user_input.isdigit() and 1 <= int(user_input) <= len(EXAMPLE_TASKS):
            user_input = EXAMPLE_TASKS[int(user_input) - 1]

    print(f"\n[Intent Parser] Parsing: {user_input!r}")
    target_url, target_locale, task = await parse_user_intent(user_input)
    print(f"  URL    : {target_url or '(none detected)'}")
    print(f"  Locale : {target_locale}")
    print(f"  Task   : {task}")

    await run_agent(task, target_url, target_locale)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nAgent interrupted.")
    except Exception as exc:
        print(f"\nError: {exc}")
        import traceback
        traceback.print_exc()
