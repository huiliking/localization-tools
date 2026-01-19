# 10-Site Test Suite - What to Expect

## Test Configuration
- **Locale:** Spanish (es)
- **Browser:** Chrome with Spanish language preference
- **Sites:** 10 major websites

---

## Site Predictions

### Original 4 Sites (Known Results)

1. **Shopify** - www.shopify.com
   - Expected: English-only, no localization
   - Button: "Start for free"
   - Grade: POOR

2. **Stripe** - www.stripe.com
   - Expected: Canada routing (en-ca or fr-ca)
   - Button: "Démarrer" or similar
   - Grade: PARTIAL (good homepage, English signup)

3. **Amazon** - www.amazon.com
   - Expected: EXCELLENT - Full Spanish support
   - Button: "Hola, Identifícate..." or "Cuenta"
   - Grade: EXCELLENT

4. **BBC** - www.bbc.com
   - Expected: English-only
   - Button: "Register"
   - Grade: POOR

---

### New 6 Sites (Predictions)

5. **Netflix** - www.netflix.com
   - Prediction: Likely partial - IP-based routing
   - Expected Button: "Sign In" or regional variant
   - Predicted Grade: PARTIAL
   - Why: Global service, should have Spanish

6. **Walmart** - www.walmart.com
   - Prediction: US-focused, English-only
   - Expected Button: "Sign in" or "Create account"
   - Predicted Grade: POOR
   - Why: US retailer, limited international

7. **CNN** - www.cnn.com
   - Prediction: English-only news site
   - Expected Button: "Sign in" or "Create account"
   - Predicted Grade: POOR
   - Why: US news, has CNN Español but separate

8. **OpenAI** - www.openai.com
   - Prediction: EXCELLENT - Multi-language AI company
   - Expected Button: Regional variant of signup
   - Predicted Grade: EXCELLENT
   - Why: AI company with global focus, should localize

9. **Microsoft** - www.microsoft.com
   - Prediction: EXCELLENT - Enterprise global company
   - Expected Button: Regional language variant
   - Predicted Grade: EXCELLENT
   - Why: Global enterprise, proven multi-language support

10. **Anthropic** - www.anthropic.com
    - Prediction: English-only (ironic!)
    - Expected Button: "Get started" or similar
    - Predicted Grade: POOR
    - Why: AI company that builds multilingual models but might not localize own site
    - **MOST INTERESTING TEST** - Do they practice what they preach?

---

## Expected Overall Results

**Predicted Distribution:**
- EXCELLENT: 3/10 (30%) - Amazon, OpenAI, Microsoft
- PARTIAL: 2/10 (20%) - Stripe, Netflix
- POOR: 5/10 (50%) - Shopify, BBC, Walmart, CNN, Anthropic

**Key Findings to Watch:**
1. Do AI companies (OpenAI, Anthropic) localize their own signups?
2. Does Microsoft live up to enterprise reputation?
3. Does Netflix respect browser settings or force IP routing?

---

## Success Metrics to Track

**Button Detection:**
- Target: 100% (10/10 sites)
- Method breakdown: LLM vs Fallback

**Localization Quality:**
- Homepage in Spanish?
- Signup page in Spanish?
- Language selector available?
- URL culture code present?

---

## Most Anticipated Result

**Anthropic.com** - Will the company that builds Claude (multilingual AI) have a localized signup experience?

**Hypothesis:** Probably not, because:
- Focus on product, not marketing site
- Small company, limited resources
- English-dominant AI research community

**But if they DO localize:** Major props for practicing what they preach!

---

## Run Command

```cmd
python run_test_suite.py
```

or

```cmd
run_audit_tests.bat
```

**Estimated time:** ~15-20 minutes for all 10 sites

---

## What Counts as Success

**For the test suite:**
- 100% button detection (all 10 sites)
- Clean execution (no crashes)
- Accurate results

**For the sites:**
- EXCELLENT: Homepage + Signup both in Spanish
- PARTIAL: Either homepage OR signup in Spanish
- POOR: Neither in Spanish

---

Good luck! 🚀
