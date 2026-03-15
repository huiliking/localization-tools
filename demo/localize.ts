/**
 * AI-Powered Localization Script
 * --------------------------------
 * Reads a React/TSX component, extracts all user-facing strings,
 * and generates idiomatic locale JSON files — all at once, with full UI context.
 *
 * Usage:  npx ts-node localize.ts
 * Output: locales/en.json, es.json, ja.json, fr.json, de.json
 *
 * Why this matters:
 *   Traditional i18n: write UI → extract strings → send to translator → wait → integrate
 *   This approach:    write UI → run this script → all locales ready in seconds
 */

import * as fs from "fs";
import * as path from "path";

// ── Config ────────────────────────────────────────────────────────────────────

const COMPONENT_FILE = "SignupPage.tsx";

const TARGET_LOCALES = [
  { code: "en", name: "English" },
  { code: "es", name: "Spanish" },
  { code: "ja", name: "Japanese" },
  { code: "fr", name: "French" },
  { code: "de", name: "German" },
];

// 🔀 Switch between local Ollama (free) and Anthropic API (cloud)
const USE_OLLAMA = true; // set to false to use Anthropic instead

const OLLAMA_URL = "http://localhost:11434";
const OLLAMA_MODEL = "llama3.2";

// ── AI Providers ──────────────────────────────────────────────────────────────

async function callOllama(prompt: string): Promise<string> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10 * 60 * 1000); // 10 min

  const response = await fetch(`${OLLAMA_URL}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal: controller.signal,
    body: JSON.stringify({
      model: OLLAMA_MODEL,
      prompt,
      stream: false,
      options: { temperature: 0.1, num_predict: -1 },
    }),
  });

  clearTimeout(timeout);

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Ollama error ${response.status}: ${err}`);
  }

  const result = await response.json() as { response: string };
  return result.response;
}

async function callAnthropic(prompt: string): Promise<string> {
  const Anthropic = (await import("@anthropic-ai/sdk")).default;
  const client = new Anthropic();

  const message = await client.messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 1024,
    messages: [{ role: "user", content: prompt }],
  });

  const content = message.content[0] as { type: string; text: string };
  return content.text;
}

async function callAI(prompt: string): Promise<string> {
  return USE_OLLAMA ? callOllama(prompt) : callAnthropic(prompt);
}

// ── JSON Repair ───────────────────────────────────────────────────────────────

function repairAndParseJSON(raw: string): Record<string, string> {
  console.log("\n[DEBUG] Raw response:\n", raw);

  // Normalize Unicode smart/curly quotes → straight ASCII quotes
  // Ollama models often emit these; they look identical in terminals but break JSON.parse
  let cleaned = raw
    .replace(/[\u201C\u201D\u201E\u201F\u2033\u2036]/g, '"')  // smart double quotes → "
    .replace(/[\u2018\u2019\u201A\u201B\u2032\u2035]/g, "'")  // smart single quotes → '
    .replace(/\uFEFF/g, "")                                    // strip BOM
    // Strip markdown fences if model added them
    .replace(/```json/gi, "")
    .replace(/```/g, "")
    .trim();

  // Extract just the JSON object; if closing } is missing, append one to repair truncated output
  const start = cleaned.indexOf("{");
  if (start === -1) throw new Error("No JSON object found");
  let end = cleaned.lastIndexOf("}");
  if (end === -1) cleaned = cleaned + "}";
  end = cleaned.lastIndexOf("}");
  cleaned = cleaned.slice(start, end + 1);

  // Fix missing commas between entries: "value"\n  "key" → "value",\n  "key"
  cleaned = cleaned.replace(/"(\s*\n\s*)"/g, '",$1"');

  // Fix common small-model mistake: list items output as bare string keys
  // e.g. "✓ No setup fees", → remove these orphan entries
  // They look like: "some string",  (no colon after them)
  cleaned = cleaned.replace(/(?<=[{,]\s*)"[^"]+",\s*(?="[^"]*"\s*:)/g, "");  // orphan before valid key (not a value after :)
  cleaned = cleaned.replace(/,\s*"([^"]+)"\s*}/g, "}");          // orphan at end of object

  // Remove trailing commas before closing brace
  cleaned = cleaned.replace(/,\s*}/g, "}");

  try {
    return JSON.parse(cleaned);
  } catch (e: any) {
    // Extract position from error message and dump surrounding char codes
    const pos = parseInt(e.message.match(/position (\d+)/)?.[1] ?? "0", 10);
    const window = cleaned.slice(Math.max(0, pos - 5), pos + 10);
    console.error(`[DEBUG] Parse failed at pos ${pos}. Chars around it:`);
    console.error([...window].map(c => `U+${c.codePointAt(0)!.toString(16).padStart(4,"0")} (${c})`).join("  "));
    throw e;
  }
}

// ── First Pass: Extract Keys ──────────────────────────────────────────────────

async function extractKeys(componentSource: string): Promise<Record<string, string>> {
  console.log(`\n  [1/2] Extracting string keys from component...`);

  const prompt = `Extract all user-facing strings from this React component and return them as a JSON object.

Component:
\`\`\`tsx
${componentSource}
\`\`\`

Rules:
- Keys: snake_case English identifiers (e.g. "welcome_heading", "submit_button")
- Values: the exact English string from the component
- Include ALL visible text: headings, labels, placeholders, buttons, links, legal text, bullet points
- For bullet list items, use keys like "feature_1", "feature_2", "feature_3"
- Return ONLY a valid JSON object, no explanation, no markdown fences

Example format:
{"welcome_heading": "Welcome", "submit_button": "Create Account", "feature_1": "✓ Free trial"}`;

  const raw = await callAI(prompt);
  return repairAndParseJSON(raw);
}

// ── Second Pass: Translate Per Locale ────────────────────────────────────────

async function translateLocale(
  keys: Record<string, string>,
  locale: { code: string; name: string }
): Promise<Record<string, string>> {

  // English just returns the keys as-is
  if (locale.code === "en") return keys;

  const keyValueList = Object.entries(keys)
    .map(([k, v]) => `  "${k}": "${v}"`)
    .join("\n");

  const guidelines: Record<string, string> = {
    es: "Use Latin American Spanish. Natural, friendly SaaS product tone.",
    ja: "Use polite keigo form (です/ます). Appropriate for a business SaaS product.",
    fr: "Use standard French. Natural product UI tone, not overly formal.",
    de: "Use standard German. Clear, professional SaaS product tone.",
  };

  const prompt = `Translate these UI strings into ${locale.name}.

Strings to translate:
{
${keyValueList}
}

Guidelines: ${guidelines[locale.code] || "Natural, professional tone."}

Rules:
- Keep the exact same JSON keys
- Translate only the values
- Use idiomatic phrasing a native speaker would use in a product UI
- Return ONLY a valid JSON object, no explanation, no markdown fences`;

  const raw = await callAI(prompt);
  return repairAndParseJSON(raw);
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function localizeComponent() {
  console.log("\n╔══════════════════════════════════════════════════════════╗");
  console.log("║          AI-Powered Localization Generator               ║");
  console.log(`║  Provider: ${USE_OLLAMA ? `Ollama (${OLLAMA_MODEL})                  ` : "Anthropic (claude-sonnet-4-6)    "}║`);
  console.log("╚══════════════════════════════════════════════════════════╝\n");

  // 1. Read component
  const componentPath = path.join(__dirname, COMPONENT_FILE);
  if (!fs.existsSync(componentPath)) {
    console.error(`❌  Could not find ${COMPONENT_FILE}`);
    process.exit(1);
  }

  const componentSource = fs.readFileSync(componentPath, "utf-8");
  console.log(`📄  Read component: ${COMPONENT_FILE} (${componentSource.split("\n").length} lines)`);

  // 2. Create output folder
  const outputDir = path.join(__dirname, "locales");
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir);
  }

  const totalStart = Date.now();

  // 3. Extract English keys first (one focused call)
  const englishKeys = await extractKeys(componentSource);
  console.log(`  ✓  Extracted ${Object.keys(englishKeys).length} strings\n`);

  // Write English baseline
  fs.writeFileSync(
    path.join(outputDir, "en.json"),
    JSON.stringify(englishKeys, null, 2),
    "utf-8"
  );
  console.log(`  ✓  locales/en.json`);

  // 4. Translate each locale separately (one focused call per locale)
  console.log(`\n  [2/2] Translating into ${TARGET_LOCALES.length - 1} languages...\n`);

  for (const locale of TARGET_LOCALES.filter(l => l.code !== "en")) {
    const start = Date.now();
    process.stdout.write(`  ⏳  locales/${locale.code}.json  (${locale.name})...`);

    try {
      const translated = await translateLocale(englishKeys, locale);
      const elapsed = ((Date.now() - start) / 1000).toFixed(1);

      fs.writeFileSync(
        path.join(outputDir, `${locale.code}.json`),
        JSON.stringify(translated, null, 2),
        "utf-8"
      );

      process.stdout.write(`  ✓  (${elapsed}s)\n`);
    } catch (err) {
      process.stdout.write(`  ❌  Failed: ${err}\n`);
    }
  }

  // 5. Summary
  const totalElapsed = ((Date.now() - totalStart) / 1000).toFixed(1);

  console.log("\n──────────────────────────────────────────────────────────");
  console.log(`\n🎉  Done in ${totalElapsed}s! Generated ${TARGET_LOCALES.length} locale files.\n`);
  console.log("Keys extracted:");
  Object.keys(englishKeys).forEach(k => console.log(`  · ${k}`));

  console.log("\n──────────────────────────────────────────────────────────");

  if (USE_OLLAMA) {
    console.log(`\nCost: $0.00  (running locally — no API key needed)\n`);
  }
}

localizeComponent().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
