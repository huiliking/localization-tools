"""
Popup and Cookie Banner Handler
Auto-dismiss common overlays that interrupt testing
"""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

class PopupHandler:
    """
    Handles common popups and overlays that interrupt testing
    """
    
    def __init__(self, driver):
        self.driver = driver
    
    def dismiss_all_popups(self, wait_time=3):
        """
        Try to dismiss all common popups/overlays
        Call this after page load or before clicking elements
        """
        print("  -> Checking for popups/overlays...")
        
        dismissed = []
        
        # Wait a moment for popups to appear
        time.sleep(wait_time)
        
        # Try common cookie banner dismissal
        dismissed.extend(self._dismiss_cookie_banners())
        
        # Try common modal overlays
        dismissed.extend(self._dismiss_modals())
        
        # Try consent iframes
        dismissed.extend(self._dismiss_consent_iframes())
        
        if dismissed:
            print(f"    [+] Dismissed {len(dismissed)} popup(s): {', '.join(dismissed)}")
            time.sleep(1)  # Let page settle
        else:
            print("    [i] No popups detected")
        
        return len(dismissed)
    
    def _dismiss_cookie_banners(self):
        """Dismiss cookie consent banners"""
        dismissed = []
        
        # Common cookie banner button selectors
        cookie_selectors = [
            # Text-based (most reliable)
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'allow')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'consent')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ok')]",
            
            # Multilingual
            "//button[contains(text(), 'Aceptar')]",  # Spanish
            "//button[contains(text(), 'Accepter')]",  # French
            "//button[contains(text(), 'Akzeptieren')]",  # German
            "//button[contains(text(), '同意')]",  # Japanese
            
            # ID/Class based
            "#onetrust-accept-btn-handler",
            ".accept-cookies",
            "#accept-cookies",
            "[data-consent='accept']",
            "[aria-label*='Accept']",
            "[aria-label*='Agree']",
        ]
        
        for selector in cookie_selectors:
            try:
                if selector.startswith('//'):
                    elements = self.driver.find_elements(By.XPATH, selector)
                elif selector.startswith('#'):
                    elements = self.driver.find_elements(By.ID, selector[1:])
                elif selector.startswith('.'):
                    elements = self.driver.find_elements(By.CLASS_NAME, selector[1:])
                else:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                
                for element in elements:
                    if element.is_displayed():
                        element.click()
                        dismissed.append("cookie-banner")
                        time.sleep(0.5)
                        break
            except:
                continue
        
        return dismissed
    
    def _dismiss_modals(self):
        """Dismiss common modal overlays"""
        dismissed = []
        
        # Common modal close button selectors
        close_selectors = [
            # Generic close buttons
            "//button[contains(@aria-label, 'Close')]",
            "//button[contains(@aria-label, 'Fermer')]",  # French
            "//button[contains(@aria-label, 'Cerrar')]",  # Spanish
            "//button[@class*='close']",
            "//button[@class*='dismiss']",
            "[data-dismiss='modal']",
            ".modal-close",
            ".close-button",
            
            # X buttons
            "//button[text()='×']",
            "//button[text()='✕']",
            "//span[text()='×']",
        ]
        
        for selector in close_selectors:
            try:
                if selector.startswith('//'):
                    elements = self.driver.find_elements(By.XPATH, selector)
                else:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                
                for element in elements:
                    if element.is_displayed():
                        element.click()
                        dismissed.append("modal")
                        time.sleep(0.5)
                        break
            except:
                continue
        
        return dismissed
    
    def _dismiss_consent_iframes(self):
        """Handle consent management iframes (like The Economist)"""
        dismissed = []
        
        try:
            # Find consent iframes
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            
            for iframe in iframes:
                src = iframe.get_attribute('src') or ''
                title = iframe.get_attribute('title') or ''
                
                # Check if it's a consent iframe
                if any(keyword in src.lower() or keyword in title.lower() 
                       for keyword in ['consent', 'privacy', 'cookie', 'gdpr']):
                    
                    # Switch to iframe
                    self.driver.switch_to.frame(iframe)
                    
                    # Try to find accept button inside
                    accept_selectors = [
                        "//button[contains(text(), 'Accept')]",
                        "//button[contains(text(), 'Agree')]",
                        "//button[@title='Accept']",
                        ".sp_choice_type_11",  # SourcePoint consent
                    ]
                    
                    for selector in accept_selectors:
                        try:
                            if selector.startswith('//'):
                                button = self.driver.find_element(By.XPATH, selector)
                            else:
                                button = self.driver.find_element(By.CSS_SELECTOR, selector)
                            
                            if button.is_displayed():
                                button.click()
                                dismissed.append("consent-iframe")
                                time.sleep(0.5)
                                break
                        except:
                            continue
                    
                    # Switch back to main content
                    self.driver.switch_to.default_content()
                    break
        
        except:
            # Make sure we're back to default content even if error
            try:
                self.driver.switch_to.default_content()
            except:
                pass
        
        return dismissed
    
    def wait_and_click_safely(self, element, max_retries=3):
        """
        Click element with popup handling
        Retries if click is intercepted by overlay
        """
        for attempt in range(max_retries):
            try:
                # Dismiss any popups first
                if attempt > 0:
                    self.dismiss_all_popups(wait_time=1)
                
                # Try to click
                element.click()
                return True
            
            except Exception as e:
                error_msg = str(e).lower()
                
                # If click intercepted, try to dismiss overlays
                if 'intercepted' in error_msg or 'clickable' in error_msg:
                    print(f"    [!] Click blocked by overlay, attempt {attempt + 1}/{max_retries}")
                    self.dismiss_all_popups(wait_time=1)
                    
                    # Last attempt: try JavaScript click
                    if attempt == max_retries - 1:
                        try:
                            self.driver.execute_script("arguments[0].click();", element)
                            print("    [+] Clicked using JavaScript")
                            return True
                        except:
                            pass
                else:
                    # Different error, don't retry
                    raise e
        
        return False


# Usage example for integration into main script
def add_popup_handling_to_audit_script():
    """
    Instructions for adding popup handling to signup_localization_audit_v2.py
    """
    
    instructions = """
# Add to SignupLocalizationAudit class:

from popup_handler import PopupHandler

class SignupLocalizationAudit:
    def __init__(self, ...):
        # ... existing code ...
        self.popup_handler = None
    
    def create_driver(self, locale=None):
        # ... existing code to create driver ...
        
        # Initialize popup handler
        self.popup_handler = PopupHandler(driver)
        
        return driver
    
    def test_page(self, page_name):
        # ... existing code ...
        
        # After page load, dismiss popups
        self.popup_handler.dismiss_all_popups()
        
        # ... rest of test ...
    
    def find_signup_button_with_llm(self):
        # ... existing code to find button ...
        
        # When clicking button, use safe click
        if signup_button:
            success = self.popup_handler.wait_and_click_safely(signup_button)
            if not success:
                print("  [X] Could not click button (blocked by overlay)")
                return None
        
        # ... rest of method ...
"""
    
    return instructions


if __name__ == "__main__":
    print(add_popup_handling_to_audit_script())
