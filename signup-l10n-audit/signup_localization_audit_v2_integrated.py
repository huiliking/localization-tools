"""
SIGN-UP LOCALIZATION AUDIT v2 (WITH POPUP HANDLING)
"Do You Really Welcome New Users?"

Improvements:
- Popup/cookie banner auto-dismissal
- Multilingual LLM prompt for signup button detection
- Priority: Language selector > URL culture code
- Canada bilingual test (en-ca -> fr-ca)
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import requests
import json

# Import popup handler
from popup_handler import PopupHandler

class SignupLocalizationAudit:
    """
    Generic test framework for auditing signup page localization
    Tests both homepage and signup page for language support
    """
    
    def __init__(self, base_url, target_locale="es", ollama_url="http://localhost:11434"):
        """
        Args:
            base_url: Base URL of site (e.g., "https://www.stripe.com" or "www.stripe.com")
            target_locale: Locale code to test (e.g., "es" for Spanish, "ja" for Japanese)
            ollama_url: URL of local Ollama instance
        """
        # Auto-add https:// if protocol missing
        if not base_url.startswith(('http://', 'https://')):
            base_url = 'https://' + base_url
        
        self.base_url = base_url.rstrip('/')
        self.target_locale = target_locale
        self.ollama_url = ollama_url
        self.driver = None
        self.popup_handler = None  # NEW: Popup handler
        self.results = {
            'homepage': {},
            'signup_page': {}
        }
        
        # Locale to language name mapping
        self.locale_names = {
            'es': 'Spanish',
            'ja': 'Japanese',
            'fr': 'French',
            'de': 'German',
            'zh': 'Chinese',
            'ko': 'Korean',
            'pt': 'Portuguese',
            'it': 'Italian',
            'ru': 'Russian',
            'ar': 'Arabic'
        }
        
    def create_driver(self, locale=None):
        """Create Chrome driver with optional locale preference"""
        chrome_options = Options()
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        if locale:
            chrome_options.add_argument(f"--lang={locale}")
            chrome_options.add_experimental_option('prefs', {
                'intl.accept_languages': f'{locale},{locale}-{locale.upper()}'
            })
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.maximize_window()
        
        # NEW: Initialize popup handler
        self.popup_handler = PopupHandler(driver)
        
        return driver
    
    def extract_culture_from_url(self, url):
        """
        Extract culture code from URL using regex + validation
        Examples:
            https://stripe.com/es -> 'es'
            https://stripe.com/en-ca -> 'en-ca'
            https://stripe.com/ja-JP -> 'ja-JP'
        """
        # Enhanced patterns: case-insensitive, handles more formats
        patterns = [
            r'/([a-z]{2})(?:/|$)',  # /es/, /fr/, /ja/
            r'/([a-z]{2}-[a-z]{2})(?:/|$)',  # /en-ca/, /pt-br/ (lowercase)
            r'/([a-z]{2}-[A-Z]{2})(?:/|$)',  # /ja-JP/, /en-US/ (mixed case)
            r'/([a-z]{2}_[a-z]{2})(?:/|$)',  # /en_us/ (underscore)
            r'/([a-z]{2}_[A-Z]{2})(?:/|$)',  # /en_US/ (underscore mixed)
        ]
        
        potential_codes = []
        
        for pattern in patterns:
            matches = re.findall(pattern, url, re.IGNORECASE)
            potential_codes.extend(matches)
        
        # Filter out common false positives
        false_positives = ['api', 'v1', 'v2', 'v3', 'css', 'js', 'img', 'cdn', 'app']
        valid_codes = [code for code in potential_codes if code.lower() not in false_positives]
        
        if valid_codes:
            return valid_codes[0]
        
        return None
    
    def check_page_language(self, expected_locale):
        """
        Check if page is in expected language
        Returns: (is_match, detected_language, evidence)
        """
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text[:2000]
            html_lang = self.driver.find_element(By.TAG_NAME, "html").get_attribute("lang")
            
            # Check 1: HTML lang attribute
            if html_lang and expected_locale.lower() in html_lang.lower():
                return (True, html_lang, "HTML lang attribute matches")
            
            # Check 2: Character set analysis
            language_detected = self._detect_language_from_text(body_text, expected_locale)
            
            if language_detected:
                return (True, expected_locale, f"Detected {self.locale_names.get(expected_locale, expected_locale)} text")
            else:
                return (False, "en", f"No {self.locale_names.get(expected_locale, expected_locale)} content detected")
        
        except Exception as e:
            return (False, "unknown", f"Error: {e}")
    
    def _detect_language_from_text(self, text, expected_locale):
        """Detect if text contains expected language characters"""
        sample = text[:1000]
        
        if expected_locale in ['ja', 'jp']:
            return any(0x3040 <= ord(c) <= 0x30FF or 0x4E00 <= ord(c) <= 0x9FFF for c in sample)
        
        elif expected_locale in ['zh', 'zh-cn', 'zh-tw']:
            return any(0x4E00 <= ord(c) <= 0x9FFF for c in sample)
        
        elif expected_locale in ['ko', 'kr']:
            return any(0xAC00 <= ord(c) <= 0xD7AF for c in sample)
        
        elif expected_locale in ['ar']:
            return any(0x0600 <= ord(c) <= 0x06FF for c in sample)
        
        elif expected_locale in ['ru']:
            return any(0x0400 <= ord(c) <= 0x04FF for c in sample)
        
        else:
            spanish_words = ['inicio', 'sobre', 'productos', 'contacto', 'para', 'más', 'gratis']
            french_words = ['accueil', 'à propos', 'produits', 'contact', 'pour', 'plus', 'gratuit']
            german_words = ['über', 'produkte', 'kontakt', 'für', 'mehr', 'startseite', 'kostenlos']
            portuguese_words = ['início', 'sobre', 'produtos', 'contato', 'para', 'mais', 'grátis']
            
            word_lists = {
                'es': spanish_words,
                'fr': french_words,
                'de': german_words,
                'pt': portuguese_words
            }
            
            if expected_locale in word_lists:
                words = word_lists[expected_locale]
                text_lower = sample.lower()
                matches = sum(1 for word in words if word in text_lower)
                return matches >= 2
        
        return False
    
    def find_locale_selector(self):
        """Find locale/language/country selector on page (standard patterns)"""
        selectors = []
        
        patterns = [
            (By.ID, "country"),
            (By.ID, "country_code"),
            (By.ID, "language"),
            (By.ID, "locale"),
            (By.NAME, "country"),
            (By.NAME, "language"),
            (By.NAME, "locale"),
            (By.CSS_SELECTOR, "select[data-locale]"),
            (By.CSS_SELECTOR, "select[data-language]"),
            (By.CSS_SELECTOR, "select[data-country]"),
            (By.XPATH, "//select[contains(@id, 'lang')]"),
            (By.XPATH, "//select[contains(@id, 'country')]"),
        ]
        
        for by, value in patterns:
            try:
                element = self.driver.find_element(by, value)
                if element.is_displayed():
                    selectors.append(element)
            except:
                continue
        
        return selectors
    
    def find_language_selector_with_llm(self):
        """Use LLM to intelligently find language/locale selector"""
        try:
            # First try standard patterns
            standard_selectors = self.find_locale_selector()
            if standard_selectors:
                return standard_selectors
            
            # If no standard selectors, use LLM
            print("  -> Using LLM to find language selector...")
            
            selects = self.driver.find_elements(By.TAG_NAME, "select")
            
            candidates = []
            for element in selects:
                try:
                    options_text = []
                    for option in element.find_elements(By.TAG_NAME, "option")[:5]:
                        options_text.append(option.text.strip())
                    
                    if options_text:
                        candidates.append({
                            'element': element,
                            'options': options_text,
                            'id': element.get_attribute('id') or 'no-id',
                            'name': element.get_attribute('name') or 'no-name'
                        })
                except:
                    continue
            
            if not candidates:
                return []
            
            # Prepare LLM prompt
            candidate_descriptions = []
            for i, c in enumerate(candidates[:10]):
                desc = f"{i+1}. ID: {c['id']}, Name: {c['name']}, Options: {', '.join(c['options'][:3])}"
                candidate_descriptions.append(desc)
            
            prompt = f"""You are analyzing dropdown selectors. Which one is a LANGUAGE or COUNTRY selector?

Language/Country selectors have options like:
- Country names: "Canada", "France", "Japan", "日本"
- Language names: "English", "Français", "Español", "日本語"
- Locale codes: "en-CA", "fr-FR", "es-ES"

Selectors:
{chr(10).join(candidate_descriptions)}

Respond with ONLY the number (1-{len(candidate_descriptions)}) of the language/country selector. If none match, respond with "0".

Number:"""
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 5}
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get('response', '').strip()
                
                number_match = re.search(r'\b(\d+)\b', answer)
                if number_match:
                    index = int(number_match.group(1)) - 1
                    if 0 <= index < len(candidates):
                        print(f"    [+] LLM identified selector: {candidates[index]['id'] or candidates[index]['name']}")
                        return [candidates[index]['element']]
            
            return []
        
        except Exception as e:
            print(f"  [!] LLM error: {e}")
            return []
    
    def test_locale_selector(self, selector):
        """Test if locale selector actually changes page language"""
        try:
            if selector.tag_name != "select":
                return (False, "Not a select element")
            
            select = Select(selector)
            initial_url = self.driver.current_url
            initial_body = self.driver.find_element(By.TAG_NAME, "body").text[:500]
            
            # Try to select target locale
            target_selected = False
            for option in select.options:
                value = option.get_attribute('value').lower()
                text = option.text.lower()
                
                if self.target_locale in value or self.locale_names.get(self.target_locale, '').lower() in text:
                    select.select_by_value(option.get_attribute('value'))
                    target_selected = True
                    time.sleep(3)
                    break
            
            if not target_selected:
                return (False, f"Target locale {self.target_locale} not in selector options")
            
            # Check if anything changed
            new_url = self.driver.current_url
            new_body = self.driver.find_element(By.TAG_NAME, "body").text[:500]
            
            # Check for culture code in URL
            culture_code = self.extract_culture_from_url(new_url)
            if culture_code and self.target_locale in culture_code:
                return (True, f"URL changed to include culture code: {culture_code}")
            
            # Check if content changed
            is_match, detected, evidence = self.check_page_language(self.target_locale)
            if is_match:
                return (True, f"Page language changed: {evidence}")
            
            if new_body != initial_body:
                return ("PARTIAL", "Content changed but language unclear")
            
            return (False, "Selector didn't change page")
        
        except Exception as e:
            return (False, f"Error: {e}")
    
    def _test_french_canada_support(self, current_url, en_ca_code):
        """Test if site supports French-Canada when English-Canada is detected"""
        try:
            fr_ca_url = current_url.replace(en_ca_code, 'fr-ca').replace('en_ca', 'fr_ca')
            
            print(f"  -> Navigating to: {fr_ca_url}")
            self.driver.get(fr_ca_url)
            time.sleep(3)
            
            # Dismiss popups on fr-ca page too
            self.popup_handler.dismiss_all_popups(wait_time=2)
            
            is_french, detected, evidence = self.check_page_language('fr')
            
            actual_url = self.driver.current_url
            
            if 'fr-ca' not in actual_url.lower() and 'fr_ca' not in actual_url.lower() and 'fr' not in actual_url.lower():
                print(f"  [X] FAIL: fr-ca URL redirected away")
                print(f"    Redirected to: {actual_url}")
                return 'FAIL'
            
            if is_french:
                print(f"  [+] PASS: French-Canada (fr-ca) is supported!")
                print(f"    Evidence: {evidence}")
                print(f"    Conclusion: True bilingual Canadian support ✅")
                return 'PASS'
            else:
                print(f"  [X] FAIL: fr-ca URL exists but page is NOT in French")
                print(f"    Evidence: {evidence}")
                return 'FAIL'
        
        except Exception as e:
            print(f"  [X] ERROR testing fr-ca: {e}")
            return 'ERROR'
    
    def find_signup_button_with_llm(self):
        """Use local Ollama to identify signup button intelligently"""
        try:
            # Get fresh elements (important after popup dismissal)
            time.sleep(0.5)  # Brief wait for DOM to stabilize
            
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            links = self.driver.find_elements(By.TAG_NAME, "a")
            
            candidates = []
            for element in buttons + links:
                try:
                    # Only include visible elements
                    if not element.is_displayed():
                        continue
                    
                    # Get text - this might fail if element is stale
                    text = element.text.strip()
                    
                    # Normalize multi-line text (replace newlines with spaces)
                    text = ' '.join(text.split())
                    
                    # Skip empty or very long text (likely not a button)
                    if not text or len(text) > 100:
                        continue
                    
                    # Skip very short text (likely icons or single chars)
                    if len(text) < 3:
                        continue
                    
                    candidates.append({
                        'text': text,
                        'element': element,
                        'tag': element.tag_name,
                        'href': element.get_attribute('href') if element.tag_name == 'a' else None
                    })
                except:
                    # Element became stale or inaccessible - skip it
                    continue
            
            if not candidates:
                print(f"  [X] No button candidates found!")
                return None
            
            # DEBUG: Show first 20 candidates
            print(f"  -> Found {len(candidates)} button/link candidates")
            if len(candidates) > 20:
                print(f"  -> Sending first 20 to LLM for analysis")
            
            # DIAGNOSTIC: Show ALL candidates sent to LLM
            print(f"\n  [DEBUG] Candidates sent to LLM:")
            candidate_texts_display = []
            for i, c in enumerate(candidates[:20]):
                # Normalize text for display and LLM (handle accents properly)
                display_text = c['text']
                try:
                    # Try to properly encode/decode to handle escape sequences
                    display_text = display_text.encode('latin1').decode('utf-8', errors='replace')
                except:
                    pass
                print(f"    {i+1}. '{display_text}'")
                candidate_texts_display.append(f"{i+1}. {display_text}")
            print()
            
            # Use the normalized text for LLM prompt
            candidate_texts = candidate_texts_display
            
            # ULTRA-SIMPLIFIED PROMPT
            prompt = f"""Which button is for creating a NEW account or starting a FREE trial?

Look for buttons that say:
- Sign up, Register, Create account, Join
- Get started, Start free, Try free, Start trial
- Démarrer, S'inscrire, Commencer, Créer compte (French)
- Registrarse, Empezar, Crear cuenta (Spanish)
- Identifícate, Cuenta (Spanish for account/login - sometimes used for signup)

DO NOT select:
- Login/Sign in (existing users)
- Contact sales
- Pricing, About, Products

Buttons:
{chr(10).join(candidate_texts)}

Answer with just the number. Example: 9

Answer:"""
            
            # DIAGNOSTIC: Show prompt being sent
            print(f"  [DEBUG] Calling Ollama...")
            
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 5}
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get('response', '').strip()
                
                # DEBUG: Show raw LLM response
                print(f"  [DEBUG] LLM raw response: '{answer}'")
                
                # Try to extract number - be aggressive about it
                # Look for numbers anywhere in the response
                number_match = re.search(r'\b(\d+)\b', answer)
                
                if number_match:
                    index = int(number_match.group(1)) - 1
                    
                    # Special case: if LLM said "0", it means no match
                    if int(number_match.group(1)) == 0:
                        print(f"  -> LLM said '0' (no clear signup button found)")
                    elif 0 <= index < len(candidates):
                        selected = candidates[index]
                        print(f"  [+] LLM selected #{index+1}: '{selected['text']}'")
                        return selected['element']
                    else:
                        print(f"  [X] LLM selected invalid index: {index+1} (out of range 1-{len(candidates[:20])})")
                else:
                    # Try to parse if it's just a number without word boundaries
                    try:
                        number = int(answer.strip())
                        if number == 0:
                            print(f"  -> LLM said '0' (no clear signup button found)")
                        elif 1 <= number <= len(candidates[:20]):
                            index = number - 1
                            selected = candidates[index]
                            print(f"  [+] LLM selected #{number}: '{selected['text']}'")
                            return selected['element']
                        else:
                            print(f"  [X] LLM selected invalid number: {number}")
                    except:
                        print(f"  [X] Could not extract number from LLM response (got text instead)")
            else:
                print(f"  [X] Ollama API error: HTTP {response.status_code}")
            
            # ENHANCED MULTILINGUAL FALLBACK
            print(f"\n  -> LLM failed, using multilingual keyword fallback...")
            
            # Expanded patterns with multilingual support
            signup_patterns = {
                # English
                'en': ['sign up', 'signup', 'get started', 'start free', 'try free', 
                       'free trial', 'create account', 'register', 'start for free', 'join'],
                # Spanish
                'es': ['registrarse', 'empezar', 'comenzar', 'crear cuenta', 'prueba gratis',
                       'identifícate', 'cuenta y listas', 'cuenta'],
                # French  
                'fr': ['s\'inscrire', 'commencer', 'créer un compte', 'essai gratuit',
                       'démarrer', 'créer compte'],
                # German
                'de': ['anmelden', 'loslegen', 'kostenlos testen', 'registrieren'],
                # Portuguese
                'pt': ['inscrever-se', 'cadastrar', 'teste grátis', 'criar conta'],
            }
            
            # Flatten all patterns
            all_patterns = []
            for lang_patterns in signup_patterns.values():
                all_patterns.extend(lang_patterns)
            
            print(f"  [DEBUG] Checking {len(all_patterns)} multilingual patterns...")
            
            for i, candidate in enumerate(candidates[:20]):
                text_lower = candidate['text'].lower()
                for pattern in all_patterns:
                    if pattern in text_lower:
                        print(f"  [+] Fallback matched '{pattern}' in candidate #{i+1}: '{candidate['text']}'")
                        return candidate['element']
            
            print(f"  [X] No signup button found (LLM + fallback both failed)")
            print(f"  [DEBUG] None of the {len(candidates[:20])} candidates matched any pattern")
            return None
        
        except Exception as e:
            print(f"  [X] Exception in find_signup_button_with_llm: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def test_page(self, page_name):
        """
        Test a page for localization
        NEW PRIORITY: Language selector > URL culture > Page language
        """
        print(f"\n{'='*70}")
        print(f"Testing: {page_name.upper()}")
        print(f"URL: {self.driver.current_url}")
        print(f"{'='*70}\n")
        
        # NEW: Dismiss popups first
        self.popup_handler.dismiss_all_popups(wait_time=3)
        
        results = {}
        current_url = self.driver.current_url
        
        # TEST 1 (PRIORITY): Language selector check
        print("Test 1 (PRIORITY): Language/Locale Selector Check")
        print("Checking if user can manually select their language...")
        
        selectors = self.find_language_selector_with_llm()
        
        if selectors:
            print(f"  [+] Found language/locale selector")
            
            works, message = self.test_locale_selector(selectors[0])
            
            if works == True:
                print(f"  [+] PASS: Selector changes page language")
                print(f"    {message}")
                print(f"  -> User has control over language (URL culture code irrelevant)")
                results['locale_selector'] = 'PASS'
                results['user_language_control'] = 'YES'
                
                culture_code = self.extract_culture_from_url(current_url)
                if culture_code:
                    print(f"  [i] Note: URL also has culture code '{culture_code}' (for reference)")
                
                return results
            
            elif works == "PARTIAL":
                print(f"  [!] PARTIAL: {message}")
                results['locale_selector'] = 'PARTIAL'
            else:
                print(f"  [X] Selector exists but doesn't work: {message}")
                results['locale_selector'] = 'FAIL'
        else:
            print(f"  [i] No language selector found")
            print(f"  -> Checking URL-based localization instead...")
            results['locale_selector'] = 'N/A'
        
        # TEST 2: URL culture code check
        print(f"\nTest 2: URL Culture Code Check")
        culture_code = self.extract_culture_from_url(current_url)
        
        if culture_code:
            print(f"  [+] Found culture code in URL: '{culture_code}'")
            
            base_locale = culture_code.split('-')[0].split('_')[0].lower()
            is_match, detected, evidence = self.check_page_language(base_locale)
            
            if is_match:
                print(f"  [+] PASS: Page language matches URL culture code")
                print(f"    URL locale: {culture_code}, Page language: {detected}")
                print(f"    Evidence: {evidence}")
                results['url_culture_match'] = 'PASS'
            else:
                print(f"  [X] FAIL: Page language doesn't match URL culture code")
                print(f"    URL locale: {culture_code}, Expected: {base_locale}, Detected: {detected}")
                results['url_culture_match'] = 'FAIL'
            
            # Canada bilingual test
            if culture_code.lower() in ['en-ca', 'en_ca']:
                print(f"\n  [CA] BONUS TEST: Canada Bilingual Support")
                print(f"  -> Detected en-ca. Testing if fr-ca is supported...")
                fr_ca_result = self._test_french_canada_support(current_url, culture_code)
                results['french_canada_support'] = fr_ca_result
        else:
            print(f"  [i] No culture code in URL")
            results['url_culture_match'] = 'N/A'
        
        # TEST 3: Target language check
        print(f"\nTest 3: Target Language Check ({self.locale_names.get(self.target_locale, self.target_locale)})")
        is_match, detected, evidence = self.check_page_language(self.target_locale)
        
        if is_match:
            print(f"  [+] PASS: Page is in {self.locale_names.get(self.target_locale, self.target_locale)}")
            print(f"    Evidence: {evidence}")
            results['page_language'] = 'PASS'
        else:
            print(f"  [X] FAIL: Page is NOT in {self.locale_names.get(self.target_locale, self.target_locale)}")
            print(f"    Evidence: {evidence}")
            results['page_language'] = 'FAIL'
        
        return results
    
    def run_full_audit(self):
        """Run complete audit: homepage + signup page"""
        site_name = self.base_url.replace('https://', '').replace('http://', '').split('/')[0]
        
        print(f"\n{'='*70}")
        print(f"SIGN-UP LOCALIZATION AUDIT")
        print(f"Site: {site_name}")
        print(f"Target Locale: {self.target_locale} ({self.locale_names.get(self.target_locale, self.target_locale)})")
        print(f"{'='*70}")
        
        print(f"\nLaunching browser with {self.locale_names.get(self.target_locale, self.target_locale)} locale...")
        self.driver = self.create_driver(locale=self.target_locale)
        
        try:
            # STEP 1: Test Homepage
            print(f"\n{'#'*70}")
            print("STEP 1: HOMEPAGE TEST")
            print(f"{'#'*70}")
            
            self.driver.get(self.base_url)
            time.sleep(3)
            
            self.results['homepage'] = self.test_page("Homepage")
            
            # STEP 2: Find and click signup button
            print(f"\n{'#'*70}")
            print("STEP 2: FIND SIGNUP BUTTON")
            print(f"{'#'*70}\n")
            
            # IMPORTANT: Dismiss popups again before scanning for buttons
            # (Popups might reappear after homepage test, or DOM might have changed)
            print("Preparing page for button detection...")
            self.popup_handler.dismiss_all_popups(wait_time=2)
            time.sleep(1)  # Let page stabilize
            
            print("Using LLM to identify signup button...")
            signup_button = self.find_signup_button_with_llm()
            
            if signup_button:
                button_text = signup_button.text
                print(f"  [+] Found signup button: '{button_text}'")
                print(f"  -> Clicking...")
                
                # NEW: Use safe click with popup handling
                success = self.popup_handler.wait_and_click_safely(signup_button, max_retries=3)
                
                if success:
                    time.sleep(3)
                    
                    # STEP 3: Test Signup Page
                    print(f"\n{'#'*70}")
                    print("STEP 3: SIGNUP PAGE TEST")
                    print(f"{'#'*70}")
                    
                    self.results['signup_page'] = self.test_page("Signup Page")
                else:
                    print(f"  [X] Could not click button (blocked by overlay)")
                    self.results['signup_page'] = {'error': 'Button click blocked'}
            else:
                print(f"  [X] Could not identify signup button")
                self.results['signup_page'] = {'error': 'Signup button not found'}
            
            # Generate final report
            self.print_final_report()
        
        finally:
            if self.driver:
                input("\nPress Enter to close browser...")
                self.driver.quit()
    
    def print_final_report(self):
        """Print comprehensive final report"""
        print(f"\n{'='*70}")
        print("FINAL REPORT")
        print(f"{'='*70}\n")
        
        # Homepage results
        print("HOMEPAGE:")
        homepage = self.results.get('homepage', {})
        for test, result in homepage.items():
            symbol = {'PASS': '[+]', 'FAIL': '[X]', 'PARTIAL': '[!]', 'N/A': '[i]', 'YES': '[+]', 'NO': '[X]'}.get(result, '?')
            print(f"  {symbol} {test}: {result}")
        
        # Signup page results
        print("\nSIGNUP PAGE:")
        signup = self.results.get('signup_page', {})
        if 'error' in signup:
            print(f"  [X] {signup['error']}")
        else:
            for test, result in signup.items():
                symbol = {'PASS': '[+]', 'FAIL': '[X]', 'PARTIAL': '[!]', 'N/A': '[i]', 'YES': '[+]', 'NO': '[X]'}.get(result, '?')
                print(f"  {symbol} {test}: {result}")
        
        # Overall verdict
        print(f"\n{'-'*70}")
        
        homepage_pass = sum(1 for r in homepage.values() if r == 'PASS')
        signup_pass = sum(1 for r in signup.values() if r == 'PASS' and r != 'error')
        
        total_tests = len([r for r in homepage.values() if r not in ['N/A', 'YES', 'NO']]) + len([r for r in signup.values() if r not in ['N/A', 'error', 'YES', 'NO']])
        total_pass = homepage_pass + signup_pass
        
        if total_tests > 0:
            print(f"Overall: {total_pass}/{total_tests} tests passed")
            
            if total_pass == total_tests:
                print("\n[+] EXCELLENT: Full localization support on both pages")
            elif total_pass >= total_tests / 2:
                print("\n[!] PARTIAL: Some localization support exists")
            else:
                print("\n[X] POOR: Limited or no localization support")
        
        print(f"{'='*70}")


if __name__ == "__main__":
    import sys
    
    print("""
====================================================================
            SIGN-UP LOCALIZATION AUDIT v2
           "Do You Really Welcome New Users?"
====================================================================
    """)
    
    base_url = input("Enter base URL (e.g., https://www.stripe.com): ").strip()
    
    if not base_url:
        print("Error: URL required")
        sys.exit(1)
    
    locale = input("Enter target locale [es]: ").strip() or "es"
    
    audit = SignupLocalizationAudit(
        base_url=base_url,
        target_locale=locale
    )
    
    audit.run_full_audit()
