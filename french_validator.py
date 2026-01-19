# French localization validator - v0.2
# Checks if text follows one simple rule

def has_french_quotes(text):
    """Check if text uses « » instead of " " """
    if '"' in text:
        return False, "Uses English quotes, should use French « »"
    return True, "OK"

# Test it
test_text = "This is a \"test\" string"
result, message = has_french_quotes(test_text)
print(f"{result}: {message}")

def check_french_punctuation_spacing(text):
    """
    Check if text has proper spacing before French punctuation.
    French requires non-breaking space before : ; ! ?
    
    Returns: (bool, str) - (is_valid, message)
    """
    import re
    
    # Patterns that indicate missing or wrong spacing before punctuation
    wrong_patterns = [
        (r'[^\s]:',  'Missing space before :'),
        (r'[^\s];',  'Missing space before ;'),
        (r'[^\s]!',  'Missing space before !'),
        (r'[^\s]\?', 'Missing space before ?'),
    ]
    
    issues = []
    for pattern, issue_msg in wrong_patterns:
        if re.search(pattern, text):
            issues.append(issue_msg)
    
    if issues:
        return False, f"Issues: {', '.join(issues)}"
    return True, "Punctuation spacing OK"


# Test cases
if __name__ == "__main__":
    test_cases = [
        ("Bonjour!", "Should flag: missing space before !"),
        ("Bonjour !", "Should pass: has space before !"),
        ("Comment allez-vous?", "Should flag: missing space before ?"),
        ("Vraiment? C'est bon!", "Should flag: both punctuation issues"),
    ]
    
    print("=== Testing French Punctuation Spacing ===")
    for text, description in test_cases:
        result, message = check_french_punctuation_spacing(text)
        print(f"\nText: '{text}'")
        print(f"Expected: {description}")
        print(f"Result: {result} - {message}")
