/**
 * Localization Benchmark — Option A
 * -----------------------------------
 * Compares two translation approaches on token consumption, response time,
 * and output quality (keys matched vs. expected).
 *
 * Approach 1 — Context-Aware
 *   One prompt per locale: send the full TSX component source + target language.
 *   The AI sees UI structure (labels next to inputs, buttons inside forms, etc.)
 *   and produces a locale JSON directly — no prior extraction step.
 *
 * Approach 2 — Context-Free (Direct)
 *   One prompt per locale: send en.json key-value pairs + target language.
 *   The AI translates strings in isolation, without seeing how they are used.
 *
 * Both make exactly 4 AI calls (one per locale), so timing is directly comparable.
 *
 * Usage: npx ts-node benchmark.ts
 */

import * as fs   from "fs";
import * as path from "path";

// ── Config ────────────────────────────────────────────────────────────────────

const COMPONENT_FILE = "SignupPage.tsx";
const LOCALES_DIR    = "locales";
const OLLAMA_URL     = "http://localhost:11434";
const OLLAMA_MODEL   = "llama3.2";

const TARGET_LOCALES = [
  { code: "es", name: "Spanish"  },
  { code: "ja", name: "Japanese" },
  { code: "fr", name: "French"   },
  { code: "de", name: "German"   },
];

// ── Types ─────────────────────────────────────────────────────────────────────

interface CallResult {
  text:         string;
  inputTokens:  number;
  outputTokens: number;
  durationMs:   number;
}

interface LocaleResult {
  locale:        string;
  inputTokens:   number;
  outputTokens:  number;
  durationMs:    number;
  keysMatched:   number;   // how many expected keys were present in output
  keysExpected:  number;
  ok:            boolean;
}

// ── Ollama ────────────────────────────────────────────────────────────────────

async function callOllama(prompt: string): Promise<CallResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10 * 60 * 1000);

  const start = Date.now();
  const response = await fetch(`${OLLAMA_URL}/api/generate`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    signal:  controller.signal,
    body: JSON.stringify({
      model:   OLLAMA_MODEL,
      prompt,
      stream:  false,
      options: { temperature: 0.1, num_predict: -1 },
    }),
  });
  clearTimeout(timeout);

  if (!response.ok) throw new Error(`Ollama ${response.status}: ${await response.text()}`);

  const raw = await response.json() as {
    response:          string;
    prompt_eval_count: number;
    eval_count:        number;
  };

  return {
    text:         raw.response,
    inputTokens:  raw.prompt_eval_count ?? 0,
    outputTokens: raw.eval_count        ?? 0,
    durationMs:   Date.now() - start,
  };
}

// ── JSON repair ───────────────────────────────────────────────────────────────

function repairAndParse(raw: string): Record<string, string> {
  let cleaned = raw
    .replace(/[\u201C\u201D\u201E\u201F\u2033\u2036]/g, '"')
    .replace(/[\u2018\u2019\u201A\u201B\u2032\u2035]/g, "'")
    .replace(/\uFEFF/g, "")
    .replace(/```json/gi, "")
    .replace(/```/g, "")
    .trim();

  const start = cleaned.indexOf("{");
  if (start === -1) throw new Error("No JSON object found");
  let end = cleaned.lastIndexOf("}");
  if (end === -1) cleaned = cleaned + "}";
  end = cleaned.lastIndexOf("}");
  cleaned = cleaned.slice(start, end + 1);

  cleaned = cleaned.replace(/"(\s*\n\s*)"/g, '",$1"');
  cleaned = cleaned.replace(/(?<=[{,]\s*)"[^"]+",\s*(?="[^"]*"\s*:)/g, "");
  cleaned = cleaned.replace(/,\s*"([^"]+)"\s*}/g, "}");
  cleaned = cleaned.replace(/,\s*}/g, "}");

  return JSON.parse(cleaned);
}

// ── Approach 1: Context-Aware ─────────────────────────────────────────────────
// Send full TSX source + target language → AI extracts AND translates in one shot

async function contextAwareTranslation(
  componentSource: string,
  locale: { code: string; name: string },
  expectedKeys: string[],
): Promise<LocaleResult> {
  const guidelines: Record<string, string> = {
    es: "Use Latin American Spanish. Natural, friendly SaaS product tone.",
    ja: "Use polite keigo form (です/ます). Appropriate for a business SaaS product.",
    fr: "Use standard French. Natural product UI tone, not overly formal.",
    de: "Use standard German. Clear, professional SaaS product tone.",
  };

  const prompt = `You are localizing a React signup page into ${locale.name}.

Here is the full component source:
\`\`\`tsx
${componentSource}
\`\`\`

Task: extract every user-facing string from the component and translate it directly into ${locale.name}.

Guidelines: ${guidelines[locale.code] ?? "Natural, professional tone."}

Rules:
- Keys: snake_case English identifiers (e.g. "welcome_heading", "submit_button")
- Values: the translated ${locale.name} string
- Include ALL visible text: headings, labels, placeholders, buttons, links, legal text, bullet points
- Use idiomatic phrasing a native speaker would use in a product UI
- Return ONLY a valid JSON object, no explanation, no markdown fences`;

  const call = await callOllama(prompt);

  try {
    const parsed = repairAndParse(call.text);
    const keysMatched = expectedKeys.filter(k => k in parsed).length;
    return { locale: locale.code, ok: true, keysMatched, keysExpected: expectedKeys.length, ...pick(call) };
  } catch {
    return { locale: locale.code, ok: false, keysMatched: 0, keysExpected: expectedKeys.length, ...pick(call) };
  }
}

// ── Approach 2: Context-Free ──────────────────────────────────────────────────
// Send en.json key-value pairs + target language → AI translates in isolation

async function contextFreeTranslation(
  englishKeys: Record<string, string>,
  locale: { code: string; name: string },
): Promise<LocaleResult> {
  const guidelines: Record<string, string> = {
    es: "Use Latin American Spanish. Natural, friendly SaaS product tone.",
    ja: "Use polite keigo form (です/ます). Appropriate for a business SaaS product.",
    fr: "Use standard French. Natural product UI tone, not overly formal.",
    de: "Use standard German. Clear, professional SaaS product tone.",
  };

  const keyValueList = Object.entries(englishKeys)
    .map(([k, v]) => `  "${k}": "${v}"`)
    .join("\n");

  const prompt = `Translate these UI strings into ${locale.name}.

Strings to translate:
{
${keyValueList}
}

Guidelines: ${guidelines[locale.code] ?? "Natural, professional tone."}

Rules:
- Keep the exact same JSON keys
- Translate only the values
- Use idiomatic phrasing a native speaker would use in a product UI
- Return ONLY a valid JSON object, no explanation, no markdown fences`;

  const call = await callOllama(prompt);
  const expectedKeys = Object.keys(englishKeys);

  try {
    const parsed = repairAndParse(call.text);
    const keysMatched = expectedKeys.filter(k => k in parsed).length;
    return { locale: locale.code, ok: true, keysMatched, keysExpected: expectedKeys.length, ...pick(call) };
  } catch {
    return { locale: locale.code, ok: false, keysMatched: 0, keysExpected: expectedKeys.length, ...pick(call) };
  }
}

// ── Report ────────────────────────────────────────────────────────────────────

function printReport(
  results1: LocaleResult[],
  results2: LocaleResult[],
  expectedKeys: string[],
) {
  const W = 74;
  console.log("\n" + "═".repeat(W));
  console.log("  BENCHMARK RESULTS  —  " + OLLAMA_MODEL);
  console.log("═".repeat(W));

  const col = (s: string | number, w: number, right = false) =>
    right ? String(s).padStart(w) : String(s).padEnd(w);

  const header = [
    col("Locale", 8),
    col("In tokens", 11, true),
    col("Out tokens", 11, true),
    col("Time (ms)", 11, true),
    col("Keys matched", 14, true),
    col("Status", 8),
  ].join("  ");

  const sep = "  " + "-".repeat(W - 2);

  for (const [label, results] of [
    ["Approach 1 — Context-Aware  (full component → translated JSON)", results1],
    ["Approach 2 — Context-Free   (en.json strings → translated JSON)", results2],
  ] as [string, LocaleResult[]][]) {
    console.log(`\n  ${label}`);
    console.log(`  ${header}`);
    console.log(sep);

    let totIn = 0, totOut = 0, totMs = 0, totKeys = 0;

    for (const r of results) {
      const keysFrac = `${r.keysMatched}/${r.keysExpected}`;
      console.log("  " + [
        col(r.locale, 8),
        col(r.inputTokens, 11, true),
        col(r.outputTokens, 11, true),
        col(r.durationMs, 11, true),
        col(keysFrac, 14, true),
        col(r.ok ? "✓" : "❌", 8),
      ].join("  "));
      totIn  += r.inputTokens;
      totOut += r.outputTokens;
      totMs  += r.durationMs;
      totKeys += r.keysMatched;
    }

    console.log(sep);
    console.log("  " + [
      col("TOTAL", 8),
      col(totIn,  11, true),
      col(totOut, 11, true),
      col(totMs,  11, true),
      col(`${totKeys}/${expectedKeys.length * results.length}`, 14, true),
      col("", 8),
    ].join("  "));
  }

  // Delta
  const sum = (rs: LocaleResult[]) => ({
    in:   rs.reduce((a, r) => a + r.inputTokens,  0),
    out:  rs.reduce((a, r) => a + r.outputTokens, 0),
    ms:   rs.reduce((a, r) => a + r.durationMs,   0),
    keys: rs.reduce((a, r) => a + r.keysMatched,  0),
  });

  const s1 = sum(results1), s2 = sum(results2);
  const pct = (a: number, b: number) =>
    b === 0 ? "n/a" : `${((a - b) / b * 100).toFixed(1)}%`;

  console.log("\n" + "═".repeat(W));
  console.log("  DELTA  (Approach 1 vs Approach 2)\n");
  console.log(`  Input tokens :  ${s1.in} vs ${s2.in}  →  Approach 1 uses ${pct(s1.in,  s2.in)}  more input tokens`);
  console.log(`  Output tokens:  ${s1.out} vs ${s2.out}  →  Approach 1 uses ${pct(s1.out, s2.out)}  more output tokens`);
  console.log(`  Total time   :  ${s1.ms}ms vs ${s2.ms}ms  →  Approach 1 is ${pct(s1.ms, s2.ms)}  slower`);
  console.log(`  Keys matched :  ${s1.keys}/${expectedKeys.length * 4} vs ${s2.keys}/${expectedKeys.length * 4}  →  completeness comparison`);
  console.log("\n  Interpretation:");
  console.log("  • Input token delta = cost of sending full component source vs. just strings");
  console.log("  • Keys matched = quality signal: did the AI cover all expected strings?");
  console.log("  • Approach 1 may produce better translations (sees UI context/structure)");
  console.log("  • Approach 2 is cheaper but translates strings without usage context");
  console.log("═".repeat(W) + "\n");
}

function pick(c: CallResult) {
  return { inputTokens: c.inputTokens, outputTokens: c.outputTokens, durationMs: c.durationMs };
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  console.log("\n╔══════════════════════════════════════════════════════════════════════════╗");
  console.log("║  Localization Benchmark — Context-Aware vs Context-Free                  ║");
  console.log(`║  Model: ${OLLAMA_MODEL.padEnd(66)}║`);
  console.log("╚══════════════════════════════════════════════════════════════════════════╝\n");

  const componentSource = fs.readFileSync(path.join(__dirname, COMPONENT_FILE), "utf-8");
  const englishKeys     = JSON.parse(fs.readFileSync(path.join(__dirname, LOCALES_DIR, "en.json"), "utf-8")) as Record<string, string>;
  const expectedKeys    = Object.keys(englishKeys);

  console.log(`Component: ${COMPONENT_FILE} (${componentSource.split("\n").length} lines)`);
  console.log(`English keys in en.json: ${expectedKeys.length}`);
  console.log(`Target locales: ${TARGET_LOCALES.map(l => l.code).join(", ")}\n`);

  // Run both approaches, interleaved per locale so model cache state is similar
  const results1: LocaleResult[] = [];
  const results2: LocaleResult[] = [];

  for (const locale of TARGET_LOCALES) {
    console.log(`── ${locale.name} (${locale.code}) ──────────────────────────────────────────`);

    process.stdout.write(`  Approach 1 (context-aware)... `);
    const r1 = await contextAwareTranslation(componentSource, locale, expectedKeys);
    console.log(`${r1.ok ? "✓" : "❌"}  ${r1.durationMs}ms  |  in: ${r1.inputTokens}  out: ${r1.outputTokens}  |  keys: ${r1.keysMatched}/${r1.keysExpected}`);
    results1.push(r1);

    process.stdout.write(`  Approach 2 (context-free)....  `);
    const r2 = await contextFreeTranslation(englishKeys, locale);
    console.log(`${r2.ok ? "✓" : "❌"}  ${r2.durationMs}ms  |  in: ${r2.inputTokens}  out: ${r2.outputTokens}  |  keys: ${r2.keysMatched}/${r2.keysExpected}`);
    results2.push(r2);

    console.log();
  }

  printReport(results1, results2, expectedKeys);
}

main().catch(err => { console.error("Fatal:", err); process.exit(1); });
