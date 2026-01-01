"""
verifier.py - State Verifier Module

Checks if we've reached the end state or should continue the loop.
"""

import logging
from typing import Dict, Any, Literal
from playwright.sync_api import Page

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


VerificationStatus = Literal["continue", "finish", "pause"]


class Verifier:
    """Verifies the current state and decides next action."""
    
    # End state indicators (buttons that should NOT be clicked)
    END_STATE_BUTTONS = [
        "Complete reservation",
        "Complete Reservation", 
        "Confirm reservation",
        "Confirm Reservation",
        "Complete booking",
        "Complete Booking",
        "Confirm booking",
        "Confirm Booking",
        "Book now",
        "Book Now",
        "Reserve now",
        "Reserve Now"
    ]
    
    def __init__(self, page: Page):
        """
        Initialize the Verifier.
        
        Args:
            page: Playwright Page object
        """
        self.page = page
    
    def verify(self, execution_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verify the current state after an execution.
        
        Args:
            execution_result: Result from executor with ok, pre_url, post_url, etc.
        
        Returns:
            Verification result:
            {
                "status": "continue" | "finish" | "pause",
                "reason": str,
                "should_continue": bool,
                "current_url": str,
                "end_state_detected": bool,
                "details": {...}
            }
        """
        logger.info("Verifying current state...")
        
        current_url = self.page.url
        
        # Check if execution failed
        if not execution_result.get("ok", False):
            logger.warning("Execution failed, pausing for review")
            return {
                "status": "pause",
                "reason": f"Execution failed: {execution_result.get('error', 'Unknown error')}",
                "should_continue": False,
                "current_url": current_url,
                "end_state_detected": False,
                "details": {
                    "error": execution_result.get("error")
                }
            }
        
        # Check for end state indicators
        end_state_detected, button_text = self._check_end_state()
        
        if end_state_detected:
            logger.info(f"End state detected: '{button_text}' button found")
            return {
                "status": "finish",
                "reason": f"Reached booking review page - '{button_text}' button detected",
                "should_continue": False,
                "current_url": current_url,
                "end_state_detected": True,
                "details": {
                    "end_button_text": button_text,
                    "booking_ready": True
                }
            }
        
        # Check if URL changed (progress was made)
        url_changed = execution_result.get("post_url") != execution_result.get("pre_url")
        
        # Check for common error/block indicators
        if self._check_blocked_state():
            logger.warning("Blocked state detected")
            return {
                "status": "pause",
                "reason": "Page appears blocked or showing error message",
                "should_continue": False,
                "current_url": current_url,
                "end_state_detected": False,
                "details": {
                    "blocked": True
                }
            }
        
        # Default: continue
        logger.info("No end state detected, continuing...")
        return {
            "status": "continue",
            "reason": "Progress made, continuing to next step",
            "should_continue": True,
            "current_url": current_url,
            "end_state_detected": False,
            "details": {
                "url_changed": url_changed,
                "signals": execution_result.get("signals_seen", [])
            }
        }
    
    def _check_end_state(self) -> tuple[bool, str]:
        """
        Check if any end state button is present in the DOM.
        
        Returns:
            Tuple of (end_state_detected, button_text)
        """
        for button_text in self.END_STATE_BUTTONS:
            try:
                # Check if button with this text exists and is visible
                locator = self.page.get_by_text(button_text, exact=False)
                if locator.count() > 0:
                    # Check if at least one is visible
                    for i in range(locator.count()):
                        if locator.nth(i).is_visible():
                            logger.info(f"Found end state button: '{button_text}'")
                            return True, button_text
            except Exception as e:
                logger.debug(f"Error checking for button '{button_text}': {e}")
                continue
        
        return False, ""
    
    def _check_blocked_state(self) -> bool:
        """
        Check if the page is in a blocked or error state.
        
        Returns:
            True if blocked/error state detected
        """
        # Common error indicators
        error_indicators = [
            "error occurred",
            "something went wrong",
            "try again",
            "page not found",
            "404",
            "access denied",
            "blocked"
        ]
        
        try:
            # Get visible text
            body_text = self.page.locator("body").inner_text().lower()
            
            for indicator in error_indicators:
                if indicator in body_text:
                    logger.warning(f"Blocked state indicator found: '{indicator}'")
                    return True
                    
        except Exception as e:
            logger.debug(f"Error checking blocked state: {e}")
        
        return False
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current page state for verification.
        
        Returns:
            Summary dict with URL, title, and key elements
        """
        try:
            return {
                "url": self.page.url,
                "title": self.page.title(),
                "has_forms": self.page.locator("form").count() > 0,
                "button_count": self.page.locator("button").count(),
                "input_count": self.page.locator("input").count()
            }
        except Exception as e:
            logger.error(f"Error getting summary: {e}")
            return {
                "url": "unknown",
                "title": "unknown",
                "error": str(e)
            }


# Example usage
if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    import json
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Navigate to a test page
        page.goto("https://www.opentable.com")
        
        # Create verifier
        verifier = Verifier(page)
        
        # Mock execution result
        mock_execution = {
            "ok": True,
            "pre_url": "https://www.opentable.com",
            "post_url": "https://www.opentable.com/search",
            "signals_seen": ["url_changed"]
        }
        
        # Verify
        result = verifier.verify(mock_execution)
        
        print("\nVerification Result:")
        print(json.dumps(result, indent=2))
        
        # Get summary
        summary = verifier.get_summary()
        print("\nPage Summary:")
        print(json.dumps(summary, indent=2))
        
        input("\nPress Enter to close browser...")
        browser.close()