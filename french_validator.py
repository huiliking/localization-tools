# French localization validator - v0.1
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
