"""
executor.py - Action Executor Module

Executes actions returned by the planner using Playwright.
No thinking - just execution.
"""

import logging
import time
import base64
from typing import Dict, Any, List
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Executor:
    """Executes actions on a page using Playwright."""
    
    def __init__(self, page: Page):
        """
        Initialize the Executor.
        
        Args:
            page: Playwright Page object
        """
        self.page = page
    
    def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single action and return the result.
        
        Args:
            action: Action dict from planner with structure:
                {
                    "type": "click" | "fill" | "select" | "navigate" | "scroll" | "wait",
                    "target": {...},
                    "value": str?,
                    "expect": {...}?
                }
        
        Returns:
            Result dict with:
                {
                    "ok": bool,
                    "action": {...},
                    "pre_url": str,
                    "post_url": str,
                    "signals_seen": List[str],
                    "screenshot_after": str (base64),
                    "error": str?
                }
        """
        pre_url = self.page.url
        signals_seen = []
        error_msg = None
        
        logger.info(f"Executing action: {action['type']}")
        
        try:
            # Execute the action based on type
            action_type = action["type"]
            
            if action_type == "click":
                self._execute_click(action)
            elif action_type == "fill":
                self._execute_fill(action)
            elif action_type == "select":
                self._execute_select(action)
            elif action_type == "navigate":
                self._execute_navigate(action)
            elif action_type == "scroll":
                self._execute_scroll(action)
            elif action_type == "wait":
                self._execute_wait(action)
            else:
                raise ValueError(f"Unknown action type: {action_type}")
            
            # Wait for page to stabilize
            time.sleep(1)
            
            # Check for expected signals
            if "expect" in action and "timeout_ms" in action["expect"]:
                wait_time = action["expect"]["timeout_ms"] / 1000
                time.sleep(wait_time)
            
            post_url = self.page.url
            
            # Detect signals
            if post_url != pre_url:
                signals_seen.append("url_changed")
            
            # Try to detect network activity or DOM changes
            # (simplified - in production you'd use page.wait_for_load_state)
            try:
                self.page.wait_for_load_state("networkidle", timeout=3000)
                signals_seen.append("network_idle")
            except PlaywrightTimeoutError:
                pass
            
            # Take screenshot
            screenshot_bytes = self.page.screenshot()
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            logger.info("Action executed successfully")
            
            return {
                "ok": True,
                "action": action,
                "pre_url": pre_url,
                "post_url": post_url,
                "signals_seen": signals_seen,
                "screenshot_after": screenshot_b64
            }
            
        except Exception as e:
            logger.error(f"Error executing action: {e}")
            error_msg = str(e)
            
            # Still try to capture post-state
            post_url = self.page.url
            
            try:
                screenshot_bytes = self.page.screenshot()
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            except:
                screenshot_b64 = ""
            
            return {
                "ok": False,
                "action": action,
                "pre_url": pre_url,
                "post_url": post_url,
                "signals_seen": signals_seen,
                "screenshot_after": screenshot_b64,
                "error": error_msg
            }
    
    def _execute_click(self, action: Dict[str, Any]) -> None:
        """Execute a click action."""
        target = action["target"]
        element = self._find_element(target)
        
        if not element:
            raise Exception(f"Element not found: {target}")
        
        # Wait for element to be visible and enabled
        element.wait_for(state="visible", timeout=5000)
        
        # Scroll into view if needed
        element.scroll_into_view_if_needed()
        
        # Click
        element.click()
        logger.info(f"Clicked element: {target}")
    
    def _execute_fill(self, action: Dict[str, Any]) -> None:
        """Execute a fill action."""
        target = action["target"]
        value = action.get("value", "")
        
        element = self._find_element(target)
        
        if not element:
            raise Exception(f"Element not found: {target}")
        
        # Wait for element to be visible and enabled
        element.wait_for(state="visible", timeout=5000)
        
        # Clear and fill
        element.clear()
        element.fill(value)
        logger.info(f"Filled element with value: {value[:50]}...")
    
    def _execute_select(self, action: Dict[str, Any]) -> None:
        """Execute a select dropdown action."""
        target = action["target"]
        value = action.get("value", "")
        
        element = self._find_element(target)
        
        if not element:
            raise Exception(f"Element not found: {target}")
        
        # Wait for element to be visible and enabled
        element.wait_for(state="visible", timeout=5000)
        
        # Select option
        element.select_option(value)
        logger.info(f"Selected option: {value}")
    
    def _execute_navigate(self, action: Dict[str, Any]) -> None:
        """Execute a navigation action."""
        url = action.get("value", "")
        
        if not url:
            raise Exception("Navigate action requires a URL value")
        
        self.page.goto(url, wait_until="networkidle")
        logger.info(f"Navigated to: {url}")
    
    def _execute_scroll(self, action: Dict[str, Any]) -> None:
        """Execute a scroll action."""
        target = action.get("target", {})
        value = target.get("value", "")
        
        if value == "bottom":
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            logger.info("Scrolled to bottom")
        elif value == "top":
            self.page.evaluate("window.scrollTo(0, 0)")
            logger.info("Scrolled to top")
        else:
            # Try to find and scroll to element
            element = self._find_element(target)
            if element:
                element.scroll_into_view_if_needed()
                logger.info("Scrolled to element")
            else:
                # Default to page down
                self.page.keyboard.press("PageDown")
                logger.info("Scrolled down one page")
    
    def _execute_wait(self, action: Dict[str, Any]) -> None:
        """Execute a wait action."""
        wait_time = action.get("expect", {}).get("timeout_ms", 2000) / 1000
        time.sleep(wait_time)
        logger.info(f"Waited for {wait_time} seconds")
    
    def _find_element(self, target: Dict[str, Any]):
        """
        Find an element based on the target strategy.
        
        Args:
            target: Target dict with strategy and value
        
        Returns:
            Playwright Locator or None
        """
        strategy = target.get("strategy", "")
        value = target.get("value", "")
        
        try:
            if strategy == "id":
                return self.page.locator(f"#{value}")
            
            elif strategy == "css":
                return self.page.locator(value)
            
            elif strategy == "text":
                return self.page.get_by_text(value, exact=False)
            
            elif strategy == "aria":
                return self.page.get_by_label(value)
            
            elif strategy == "role":
                role = target.get("role", "button")
                name = target.get("name")
                if name:
                    return self.page.get_by_role(role, name=name)
                else:
                    # Find by role and value as name
                    return self.page.get_by_role(role, name=value)
            
            elif strategy == "eid":
                # Custom element ID strategy - fallback to id
                return self.page.locator(f"#{value}")
            
            else:
                # Default fallback to CSS selector
                logger.warning(f"Unknown strategy '{strategy}', trying as CSS selector")
                return self.page.locator(value)
                
        except Exception as e:
            logger.error(f"Error finding element with strategy {strategy}: {e}")
            return None


# Example usage
if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    import json
    
    # Example action to execute
    example_action = {
        "type": "click",
        "target": {
            "strategy": "text",
            "value": "Sign up"
        },
        "expect": {
            "signals": ["url_changed"],
            "timeout_ms": 2000
        }
    }
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.opentable.com")
        
        # Create executor
        executor = Executor(page)
        
        # Execute action
        result = executor.execute(example_action)
        
        # Print result
        print("\nExecution Result:")
        print(json.dumps({
            **result,
            "screenshot_after": f"<base64 data: {len(result['screenshot_after'])} chars>"
        }, indent=2))
        
        input("\nPress Enter to close browser...")
        browser.close()