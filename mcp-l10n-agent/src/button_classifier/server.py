"""
Button Classifier MCP Server

An MCP server that uses local Ollama LLM to classify buttons
for signup/login/checkout detection in web pages.

Usage:
    python -m button_classifier.server
"""

import json
import re
import httpx
from html.parser import HTMLParser
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# ============================================================================
# Configuration
# ============================================================================

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2:latest"
OLLAMA_TIMEOUT = 120.0  # seconds (increased for large button lists)

# ============================================================================
# Initialize MCP Server
# ============================================================================

mcp = FastMCP("button_classifier_mcp")

# ============================================================================
# Enums and Models
# ============================================================================

class TargetAction(str, Enum):
    """Supported button classification targets."""
    SIGNUP = "signup"
    LOGIN = "login"
    CHECKOUT = "checkout"
    SUBSCRIBE = "subscribe"


class ButtonInput(BaseModel):
    """Single button for classification."""
    text: str = Field(..., description="The button text to classify", min_length=1)
    

class ClassifyButtonsInput(BaseModel):
    """Input model for batch button classification."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    buttons: list[str] = Field(
        ..., 
        description="List of button texts to classify (e.g., ['Sign up', 'Deals of the Day', 'Create account'])",
        min_length=1,
        max_length=50
    )
    target_action: TargetAction = Field(
        default=TargetAction.SIGNUP,
        description="The action type to identify: signup, login, checkout, or subscribe"
    )
    site_context: Optional[str] = Field(
        default=None,
        description="Optional context about the website (e.g., 'Amazon homepage', 'Netflix landing page')"
    )


class ButtonScore(BaseModel):
    """Classification result for a single button."""
    text: str
    score: int = Field(..., ge=-10, le=10)
    is_match: bool
    reason: str


class ClassificationResult(BaseModel):
    """Result of batch button classification."""
    results: list[ButtonScore]
    recommended: Optional[str] = None
    confidence: str  # "high", "medium", "low"
    model_used: str


# ============================================================================
# Ollama Integration
# ============================================================================

async def call_ollama(prompt: str) -> str:
    """Call local Ollama LLM and return response text."""
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temperature for consistent classification
                    "num_predict": 4096  # Increased to handle 50 buttons
                }
            }
        )
        response.raise_for_status()
        return response.json()["response"]


def extract_json_from_response(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown code blocks."""
    import re
    
    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    
    # Try to extract from markdown code block
    patterns = [
        r'```json\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```',
        r'\{[\s\S]*\}'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                json_str = match.group(1) if '```' in pattern else match.group(0)
                return json.loads(json_str.strip())
            except json.JSONDecodeError:
                continue
    
    return None


def build_classification_prompt(buttons: list[str], target_action: str, site_context: Optional[str]) -> str:
    """Build the prompt for button classification."""
    
    button_list = "\n".join([f"  {i+1}. \"{btn}\"" for i, btn in enumerate(buttons)])
    
    context_line = f"\nWebsite context: {site_context}" if site_context else ""
    
    action_descriptions = {
        "signup": "account creation, registration, or starting a free trial",
        "login": "signing in to an existing account",
        "checkout": "purchasing, payment, or completing an order",
        "subscribe": "subscribing to a newsletter, service, or mailing list"
    }
    
    action_desc = action_descriptions.get(target_action, target_action)
    
    return f"""You are a button classifier for web automation testing.

Task: Score each button's likelihood of being a {target_action.upper()} button ({action_desc}).
{context_line}

Buttons to classify:
{button_list}

For EACH button, provide:
- score: integer from -10 (definitely NOT {target_action}) to +10 (definitely IS {target_action})
- is_match: true if score >= 5, false otherwise  
- reason: brief explanation (10 words max)

Scoring guidelines:
- +8 to +10: Clear {target_action} button (e.g., "Sign up", "Create account", "Register")
- +4 to +7: Likely {target_action} (e.g., "Get started", "Join free", "Start trial")
- -3 to +3: Ambiguous or unclear
- -4 to -7: Unlikely {target_action} (e.g., "Learn more", "Explore")
- -8 to -10: Definitely NOT {target_action} (e.g., "Deals", "FAQ", "Blog", "News")

IMPORTANT: Marketing/promotional content ("Deals of the Day", "Sale", "Meet our product") should score NEGATIVE.

Respond ONLY with valid JSON in this exact format:
{{
  "results": [
    {{"text": "button text", "score": 0, "is_match": false, "reason": "brief reason"}}
  ],
  "recommended": "text of highest scoring button or null if none score >= 5",
  "confidence": "high/medium/low"
}}"""


def parse_llm_response(response_text: str, buttons: list[str]) -> dict:
    """Parse LLM response, handling common formatting issues."""
    
    # Try to extract JSON from response
    text = response_text.strip()
    
    # Remove markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    
    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON object in response
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    
    # Fallback: return neutral scores for all buttons
    return {
        "results": [
            {"text": btn, "score": 0, "is_match": False, "reason": "Parse error - neutral score"}
            for btn in buttons
        ],
        "recommended": None,
        "confidence": "low"
    }


# ============================================================================
# MCP Tools
# ============================================================================

@mcp.tool(
    name="classify_buttons",
    annotations={
        "title": "Classify Buttons for Target Action",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def classify_buttons(params: ClassifyButtonsInput) -> str:
    """Classify a batch of buttons to identify which one matches the target action.

    Uses local Ollama LLM to analyze button texts and score their likelihood
    of being signup, login, checkout, or subscribe buttons.

    Args:
        params (ClassifyButtonsInput): Input containing:
            - buttons (list[str]): Button texts to classify
            - target_action (str): Action to identify (signup, login, checkout, subscribe)
            - site_context (str, optional): Context about the website

    Returns:
        str: JSON with scores for each button and recommendation

    Example:
        Input: {"buttons": ["Sign up", "Deals"], "target_action": "signup"}
        Output: {"results": [...], "recommended": "Sign up", "confidence": "high"}
    """
    try:
        # Build and send prompt to Ollama
        prompt = build_classification_prompt(
            buttons=params.buttons,
            target_action=params.target_action.value,
            site_context=params.site_context
        )

        llm_response = await call_ollama(prompt)

        # Parse response
        parsed = parse_llm_response(llm_response, params.buttons)
        
        # Validate and normalize results
        results = []
        for item in parsed.get("results", []):
            # Ensure score is within bounds
            score = max(-10, min(10, item.get("score", 0)))
            results.append(ButtonScore(
                text=item.get("text", ""),
                score=score,
                is_match=score >= 5,
                reason=item.get("reason", "No reason provided")
            ))
        
        # Determine recommendation
        matching = [r for r in results if r.is_match]
        if matching:
            recommended = max(matching, key=lambda x: x.score).text
        else:
            recommended = parsed.get("recommended")
        
        # Build final result
        result = ClassificationResult(
            results=results,
            recommended=recommended,
            confidence=parsed.get("confidence", "medium"),
            model_used=OLLAMA_MODEL
        )
        
        return json.dumps(result.model_dump(), indent=2)
        
    except httpx.ConnectError:
        return json.dumps({
            "error": "Cannot connect to Ollama. Is it running? Try: ollama serve",
            "results": [],
            "recommended": None
        })
    except httpx.TimeoutException:
        return json.dumps({
            "error": f"Ollama request timed out after {OLLAMA_TIMEOUT}s",
            "results": [],
            "recommended": None
        })
    except Exception as e:
        return json.dumps({
            "error": f"Classification failed: {str(e)}",
            "results": [],
            "recommended": None
        })


@mcp.tool(
    name="health_check",
    annotations={
        "title": "Check Ollama Connection",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def health_check() -> str:
    """Check if Ollama is running and the configured model is available.
    
    Returns:
        str: JSON with connection status and available models
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Check Ollama is running
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            response.raise_for_status()
            
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            
            configured_available = OLLAMA_MODEL in model_names or \
                                   OLLAMA_MODEL.replace(":latest", "") in [m.split(":")[0] for m in model_names]
            
            return json.dumps({
                "status": "connected",
                "ollama_url": OLLAMA_BASE_URL,
                "configured_model": OLLAMA_MODEL,
                "model_available": configured_available,
                "available_models": model_names
            }, indent=2)
            
    except httpx.ConnectError:
        return json.dumps({
            "status": "disconnected",
            "error": "Cannot connect to Ollama. Start it with: ollama serve",
            "ollama_url": OLLAMA_BASE_URL
        })
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": str(e)
        })


# ============================================================================
# Localization Tools
# ============================================================================

@mcp.tool(
    name="detect_language",
    annotations={
        "title": "Detect Page Language",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def detect_language(
    text_sample: str,
    expected_locale: str | None = None
) -> str:
    """Detect the language of a text sample using LLM.
    
    Use this to verify if a page is displayed in the expected language.
    
    Args:
        text_sample: Sample text from the page (first 500-1000 chars recommended)
        expected_locale: Optional expected locale code (e.g., "fr-ca", "es", "ja")
    
    Returns:
        str: JSON with detected language, confidence, and match status
    """
    prompt = f"""Analyze this text and determine what language it is written in.

Text sample:
{text_sample[:800]}

Respond in this exact JSON format:
{{
    "detected_language": "<language code like en, fr, es, ja, zh, de, pt, ko>",
    "detected_language_name": "<full name like English, French, Spanish>",
    "confidence": "<high/medium/low>",
    "evidence": "<brief explanation of why you detected this language>"
}}

JSON response:"""

    try:
        llm_response = await call_ollama(prompt)
        result = extract_json_from_response(llm_response)
        
        # Add match info if expected_locale provided
        if expected_locale and result:
            expected_base = expected_locale.split('-')[0].split('_')[0].lower()
            detected_base = result.get("detected_language", "").split('-')[0].lower()
            
            result["expected_locale"] = expected_locale
            result["matches_expected"] = expected_base == detected_base
            
            if result["matches_expected"]:
                result["verdict"] = "PASS"
                result["message"] = f"Page is in expected language ({expected_locale})"
            else:
                result["verdict"] = "FAIL"
                result["message"] = f"Expected {expected_locale}, but page is in {result.get('detected_language')}"
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "detected_language": "unknown"
        })


@mcp.tool(
    name="check_locale_support",
    annotations={
        "title": "Check Locale Support",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def check_locale_support(
    page_url: str,
    available_links: list[str],
    target_locale: str
) -> str:
    """Analyze page URLs and links to determine if a target locale is supported.
    
    Use this to check if a website offers localized versions for a specific market.
    
    Args:
        page_url: Current page URL
        available_links: List of URLs/links found on the page
        target_locale: Target locale to check (e.g., "fr-ca", "es", "ja")
    
    Returns:
        str: JSON with locale support analysis
    """
    # Build a prompt to analyze locale support
    links_sample = available_links[:30]  # Limit for prompt size
    
    # Extract base domain for regional domain reasoning
    import re as _re
    domain_match = _re.search(r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,})", page_url)
    base_domain = domain_match.group(1) if domain_match else page_url

    # Map locale → common regional domain TLD or subdomain patterns
    locale_domain_hints = {
        "fr": f"amazon.fr / {base_domain.replace('.com','')}.fr",
        "fr-ca": f"amazon.ca / {base_domain}/ca",
        "de": f"{base_domain.replace('.com','')}.de",
        "ja": f"{base_domain.replace('.com','')}.co.jp",
        "es": f"{base_domain.replace('.com','')}.es or /es/ paths",
        "it": f"{base_domain.replace('.com','')}.it",
        "pt-br": f"{base_domain.replace('.com','')}.com.br or /pt/ paths",
        "zh": f"{base_domain.replace('.com','')}.cn or /zh/ paths",
    }
    domain_hint = locale_domain_hints.get(target_locale.lower(), f"/{target_locale}/ path or regional domain")

    prompt = f"""Analyze whether the website at "{page_url}" supports the locale "{target_locale}".

Current page URL: {page_url}
Base domain: {base_domain}

Locale-related links found on the page:
{chr(10).join(f"  - {link}" for link in links_sample) if links_sample else "  (none detected — site may use regional domains or JavaScript navigation)"}

Look for ALL of these localization patterns:
1. Language/locale codes in URL paths (e.g., /fr/, /en-ca/, /ja-jp/)
2. Language selector or country selector links
3. Regional domain patterns (e.g., amazon.fr for French, amazon.co.jp for Japanese)
4. hreflang attributes or alternate language links
5. Known regional domain for {target_locale}: {domain_hint}

If no locale links were found on this page, reason about whether the website
LIKELY has a regional domain or separate localized site based on the domain "{base_domain}"
and the target locale "{target_locale}".

Target locale: {target_locale}

Respond in this exact JSON format:
{{
    "target_locale": "{target_locale}",
    "locale_supported": true/false,
    "confidence": "high/medium/low",
    "evidence": [
        "list evidence items — include reasoning about regional domains if no links found"
    ],
    "locale_url": "<likely URL for target locale, e.g. https://amazon.fr for French, or null>",
    "other_locales_found": ["list of other locale codes detected"],
    "localization_pattern": "regional_domain/path_based/subdomain/unknown",
    "recommendation": "<one sentence: what the user should check next>"
}}

JSON response:"""

    try:
        llm_response = await call_ollama(prompt)
        result = extract_json_from_response(llm_response)
        
        if result:
            # Add verdict
            if result.get("locale_supported"):
                result["verdict"] = "PASS"
            else:
                result["verdict"] = "FAIL"
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "target_locale": target_locale,
            "locale_supported": False,
            "verdict": "ERROR"
        })


@mcp.tool(
    name="evaluate_localization_quality",
    annotations={
        "title": "Evaluate Localization Quality",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def evaluate_localization_quality(
    page_texts: list[str],
    target_locale: str,
    page_context: str | None = None
) -> str:
    """Evaluate the quality of localization on a page.
    
    Checks for common localization issues like:
    - Mixed languages
    - Untranslated UI elements
    - Locale-inappropriate formats (dates, currencies)
    
    Args:
        page_texts: List of text samples from the page (buttons, headings, labels)
        target_locale: Expected locale (e.g., "fr-ca", "es-ES")
        page_context: Optional context about the page (e.g., "signup page", "homepage")
    
    Returns:
        str: JSON with localization quality analysis
    """
    context_line = f"Page context: {page_context}" if page_context else ""
    texts_sample = page_texts[:40]
    
    locale_expectations = {
        "fr-ca": "French Canadian (Québécois French, CAD currency, Canadian date formats)",
        "fr": "French (European French, EUR currency)",
        "es": "Spanish",
        "es-ES": "Spanish (Spain, EUR currency)",
        "es-MX": "Mexican Spanish (MXN currency)",
        "en-ca": "Canadian English (CAD currency, Canadian spelling)",
        "en-gb": "British English (GBP currency, British spelling)",
        "ja": "Japanese",
        "de": "German",
        "pt-br": "Brazilian Portuguese",
    }
    
    locale_desc = locale_expectations.get(target_locale.lower(), target_locale)
    
    prompt = f"""Evaluate the localization quality of this page for the {target_locale} market.

Expected: {locale_desc}
{context_line}

Text samples from the page:
{chr(10).join(f"  - {text}" for text in texts_sample)}

Check for these issues:
1. Mixed languages (some text in wrong language)
2. Untranslated elements (English buttons on French page, etc.)
3. Wrong locale variant (European French on Canadian French site)
4. Inappropriate formats (wrong currency symbol, date format)

Respond in this exact JSON format:
{{
    "overall_quality": "good/acceptable/poor",
    "target_locale": "{target_locale}",
    "detected_primary_language": "<detected language code>",
    "issues_found": [
        {{
            "type": "mixed_language/untranslated/wrong_variant/format_issue",
            "text": "<problematic text>",
            "explanation": "<what's wrong>"
        }}
    ],
    "untranslated_count": <number of untranslated elements>,
    "score": <0-100>,
    "verdict": "PASS/FAIL/WARNING",
    "summary": "<one sentence summary>"
}}

JSON response:"""

    try:
        llm_response = await call_ollama(prompt)
        result = extract_json_from_response(llm_response)
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "target_locale": target_locale,
            "verdict": "ERROR"
        })


# ============================================================================
# HTML Parser for Localization Signals
# ============================================================================

class LocalizationHTMLParser(HTMLParser):
    """Extracts localization signals from raw HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.html_lang: Optional[str] = None
        self.title: Optional[str] = None
        self._in_title = False
        self.hreflang_links: list[dict] = []
        self.all_hrefs: list[str] = []
        self.text_chunks: list[str] = []
        self._skip_depth = 0
        self._SKIP_TAGS = {"script", "style", "noscript"}

    def handle_starttag(self, tag: str, attrs):
        d = dict(attrs)
        t = tag.lower()
        if t == "html" and "lang" in d:
            self.html_lang = d["lang"]
        if t == "title":
            self._in_title = True
        if t == "link" and "alternate" in d.get("rel", "") and d.get("hreflang"):
            self.hreflang_links.append({"lang": d["hreflang"], "href": d.get("href", "")})
        if t == "a" and d.get("href"):
            self.all_hrefs.append(d["href"])
        if t in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str):
        t = tag.lower()
        if t == "title":
            self._in_title = False
        if t in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data: str):
        stripped = data.strip()
        if not stripped:
            return
        if self._in_title:
            self.title = stripped
        elif self._skip_depth == 0:
            self.text_chunks.append(stripped)


# Regex to spot locale-related hrefs: /fr/, /en-us/, ?lang=fr, .fr domain, etc.
_LOCALE_HREF_RE = re.compile(
    r"(?:"
    r"/[a-z]{2}(?:-[a-zA-Z]{2,4})?/"      # /fr/ or /fr-CA/
    r"|/[a-z]{2}(?:-[a-zA-Z]{2,4})?$"     # ends with /fr
    r"|[?&](?:lang|locale|language)=[a-z]"  # ?lang=fr
    r"|//[a-z]{2}\."                        # //fr.example.com
    r"|\.[a-z]{2,3}/[^/]"                  # .fr/ TLD
    r")",
    re.IGNORECASE,
)


# ============================================================================
# Fetch Page Content Tool
# ============================================================================

@mcp.tool(
    name="fetch_page_content",
    annotations={
        "title": "Fetch Web Page & Extract Localization Signals",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def fetch_page_content(url: str, target_locale: str) -> str:
    """Fetch a live web page and extract all localization signals.

    Use this FIRST when given a website URL to audit for localization.
    Returns the page's HTML lang attribute, hreflang links, locale-related
    navigation links, a text sample, and a preliminary verdict for the
    target locale.

    Args:
        url: Website URL to fetch (e.g. "amazon.com" or "https://amazon.com")
        target_locale: Locale to check for (e.g. "fr", "fr-ca", "es", "ja")

    Returns:
        str: JSON with page language data, links, text sample, and initial verdict
    """
    # Normalize URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers=headers
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            final_url = str(response.url)
            html = response.text

        # Parse HTML (limit to first 150 KB for speed)
        parser = LocalizationHTMLParser()
        parser.feed(html[:153600])

        # Locale-related links
        locale_links = list(
            {h for h in parser.all_hrefs if _LOCALE_HREF_RE.search(h)}
        )[:30]

        # Text sample for detect_language / quality analysis
        text_sample = " ".join(parser.text_chunks)[:1200].strip()

        # Preliminary verdict: does the target locale appear in hreflang?
        target_base = target_locale.split("-")[0].lower()
        hreflang_match = next(
            (
                lk
                for lk in parser.hreflang_links
                if lk.get("lang", "").lower().startswith(target_base)
            ),
            None,
        )

        return json.dumps(
            {
                "fetched_url": url,
                "final_url": final_url,
                "status_code": response.status_code,
                "html_lang": parser.html_lang,
                "title": parser.title,
                "hreflang_links": parser.hreflang_links[:25],
                "locale_links": locale_links,
                "text_sample": text_sample,
                "target_locale": target_locale,
                "hreflang_includes_target": hreflang_match is not None,
                "hreflang_match_detail": hreflang_match,
            },
            indent=2,
        )

    except httpx.ConnectError as exc:
        return json.dumps({"error": f"Cannot reach {url}: {exc}", "fetched_url": url})
    except httpx.TimeoutException:
        return json.dumps({"error": f"Timeout fetching {url}", "fetched_url": url})
    except Exception as exc:
        return json.dumps({"error": f"Fetch failed: {exc}", "fetched_url": url})


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    mcp.run()
