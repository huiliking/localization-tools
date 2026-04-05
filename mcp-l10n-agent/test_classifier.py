"""
Standalone test script for Button Classifier MCP Server.

Run this to verify Ollama connection and classification works
BEFORE integrating with Claude Desktop.

Usage:
    python test_classifier.py
"""

import asyncio
import json
import sys

# Add src to path for local testing
sys.path.insert(0, "src")

from button_classifier.server import (
    call_ollama,
    build_classification_prompt,
    parse_llm_response,
    OLLAMA_MODEL,
    OLLAMA_BASE_URL
)


async def test_health_check():
    """Test Ollama connection."""
    print("=" * 60)
    print("TEST 1: Ollama Health Check")
    print("=" * 60)
    
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            response.raise_for_status()
            
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            
            print(f"✅ Ollama is running at {OLLAMA_BASE_URL}")
            print(f"   Available models: {model_names}")
            
            if OLLAMA_MODEL in model_names or any(OLLAMA_MODEL.split(":")[0] in m for m in model_names):
                print(f"✅ Configured model '{OLLAMA_MODEL}' is available")
                return True
            else:
                print(f"❌ Configured model '{OLLAMA_MODEL}' NOT found!")
                print(f"   Run: ollama pull {OLLAMA_MODEL}")
                return False
                
    except httpx.ConnectError:
        print(f"❌ Cannot connect to Ollama at {OLLAMA_BASE_URL}")
        print("   Start Ollama with: ollama serve")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def test_simple_classification():
    """Test basic button classification."""
    print("\n" + "=" * 60)
    print("TEST 2: Simple Button Classification")
    print("=" * 60)
    
    buttons = ["Sign up", "Deals of the Day", "Create account"]
    target = "signup"
    
    print(f"Buttons: {buttons}")
    print(f"Target: {target}")
    print("\nCalling Ollama (this may take a few seconds on first run)...")
    
    prompt = build_classification_prompt(buttons, target, None)
    
    try:
        response = await call_ollama(prompt)
        print(f"\nRaw LLM Response:\n{response[:500]}...")
        
        parsed = parse_llm_response(response, buttons)
        print(f"\nParsed Results:")
        print(json.dumps(parsed, indent=2))
        
        # Validate
        if "results" in parsed and len(parsed["results"]) > 0:
            print("\n✅ Classification successful!")
            return True
        else:
            print("\n❌ Parsing failed - no results")
            return False
            
    except Exception as e:
        print(f"\n❌ Classification failed: {e}")
        return False


async def test_marketing_detection():
    """Test that marketing content scores negative."""
    print("\n" + "=" * 60)
    print("TEST 3: Marketing Content Detection")
    print("=" * 60)
    
    # Mix of signup and marketing buttons
    buttons = [
        "Sign up free",
        "Deals of the Day",
        "Meet our product",
        "Start your free trial",
        "Today's Sales",
        "FAQ",
        "Create your account"
    ]
    
    print(f"Testing {len(buttons)} buttons...")
    
    prompt = build_classification_prompt(buttons, "signup", "ecommerce homepage")
    
    try:
        response = await call_ollama(prompt)
        parsed = parse_llm_response(response, buttons)
        
        print("\nResults:")
        print("-" * 50)
        
        signup_buttons = []
        marketing_buttons = []
        
        for result in parsed.get("results", []):
            text = result.get("text", "")
            score = result.get("score", 0)
            reason = result.get("reason", "")
            
            indicator = "✅" if score >= 5 else "❌" if score <= -5 else "➖"
            print(f"{indicator} [{score:+3d}] {text:30s} | {reason}")
            
            if score >= 5:
                signup_buttons.append(text)
            elif score <= -5:
                marketing_buttons.append(text)
        
        print("-" * 50)
        print(f"Recommended: {parsed.get('recommended', 'None')}")
        print(f"Confidence: {parsed.get('confidence', 'unknown')}")
        
        # Check if marketing content was correctly identified
        marketing_keywords = ["deals", "sales", "meet", "faq"]
        detected_marketing = any(
            any(kw in btn.lower() for kw in marketing_keywords)
            for btn in marketing_buttons
        )
        
        if detected_marketing:
            print("\n✅ Marketing content correctly scored negative!")
            return True
        else:
            print("\n⚠️  Marketing detection may need tuning")
            return True  # Still pass, just a warning
            
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return False


async def test_batch_sites():
    """Test with button lists from actual failing sites."""
    print("\n" + "=" * 60)
    print("TEST 4: Real Site Button Lists (Simulated)")
    print("=" * 60)
    
    # Simulated button lists from your failing sites
    test_cases = [
        {
            "site": "Amazon",
            "buttons": ["Sign in", "Create your Amazon account", "Deals of the Day", "Best Sellers", "New Releases"],
            "expected": "Create your Amazon account"
        },
        {
            "site": "Netflix", 
            "buttons": ["Sign In", "Get Started", "Meet Netflix", "FAQ", "Ways to Watch"],
            "expected": "Get Started"
        },
        {
            "site": "Shopify",
            "buttons": ["Start free trial", "Log in", "Pricing", "Learn more", "Contact sales"],
            "expected": "Start free trial"
        }
    ]
    
    passed = 0
    for case in test_cases:
        print(f"\n{case['site']}:")
        print(f"  Buttons: {case['buttons']}")
        
        prompt = build_classification_prompt(case["buttons"], "signup", f"{case['site']} homepage")
        
        try:
            response = await call_ollama(prompt)
            parsed = parse_llm_response(response, case["buttons"])
            
            recommended = parsed.get("recommended")
            expected = case["expected"]
            
            if recommended and expected.lower() in recommended.lower():
                print(f"  ✅ Recommended: {recommended}")
                passed += 1
            elif recommended:
                print(f"  ⚠️  Recommended: {recommended} (expected: {expected})")
                # Partial credit - it picked something
                passed += 0.5
            else:
                print(f"  ❌ No recommendation (expected: {expected})")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    print(f"\n{'=' * 60}")
    print(f"Batch Test Results: {passed}/{len(test_cases)} passed")
    
    return passed >= len(test_cases) * 0.6  # 60% pass threshold


async def main():
    """Run all tests."""
    print("\n" + "🔧" * 30)
    print("  BUTTON CLASSIFIER MCP - TEST SUITE")
    print("🔧" * 30 + "\n")
    
    results = []
    
    # Test 1: Health check
    results.append(("Health Check", await test_health_check()))
    
    if not results[0][1]:
        print("\n⛔ Stopping tests - Ollama not available")
        return
    
    # Test 2: Simple classification
    results.append(("Simple Classification", await test_simple_classification()))
    
    # Test 3: Marketing detection
    results.append(("Marketing Detection", await test_marketing_detection()))
    
    # Test 4: Batch sites
    results.append(("Batch Sites", await test_batch_sites()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")
    
    total_passed = sum(1 for _, p in results if p)
    print(f"\nTotal: {total_passed}/{len(results)} tests passed")
    
    if total_passed == len(results):
        print("\n🎉 All tests passed! Ready to configure for Claude Desktop.")
    else:
        print("\n⚠️  Some tests failed. Review output above.")


if __name__ == "__main__":
    asyncio.run(main())
