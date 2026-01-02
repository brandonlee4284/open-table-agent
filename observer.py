import json
from typing import Dict, List, Any, Optional
from playwright.sync_api import Page, ElementHandle
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DOMObserver:
    """Observes and extracts interactive elements from the DOM."""
    
    def __init__(self, page: Page):
        """
        Initialize the DOM Observer.
        
        Args:
            page: Playwright Page object
        """
        self.page = page
        
    def observe(self) -> Dict[str, Any]:
        """
        Main observation method that extracts the complete page state.
        
        Returns:
            Dictionary containing all observable page state information
        """
        logger.info("Starting DOM observation...")
        
        page_state = {
            "url": self.page.url,
            "title": self.page.title(),
            "buttons": self._extract_buttons(),
            "text_inputs": self._extract_text_inputs(),
            "select_dropdowns": self._extract_dropdowns(),
            "links": self._extract_links(),
            "clickable_elements": self._extract_clickable_elements(),
            "form_elements": self._extract_forms(),
            "visible_text": self._extract_visible_text(),
            "timestamp": self._get_timestamp()
        }
        
        logger.info(f"Observation complete. Found {len(page_state['buttons'])} buttons, "
                   f"{len(page_state['text_inputs'])} inputs, "
                   f"{len(page_state['links'])} links")
        
        return page_state
    
    def _extract_buttons(self) -> List[Dict[str, Any]]:
        """Extract all button elements from the page."""
        buttons = []
        
        # JavaScript to extract button information
        js_code = """
        () => {
            const buttons = [];
            const selectors = [
                'button',
                'input[type="button"]',
                'input[type="submit"]',
                '[role="button"]',
                'a.btn', 
                '.button'
            ];
            
            const elements = document.querySelectorAll(selectors.join(','));
            
            elements.forEach((el, index) => {
                if (el.offsetParent !== null) { // Check if visible
                    const rect = el.getBoundingClientRect();
                    buttons.push({
                        index: index,
                        tag: el.tagName.toLowerCase(),
                        text: el.innerText?.trim() || el.value || '',
                        id: el.id || null,
                        class: el.className || null,
                        name: el.name || null,
                        type: el.type || null,
                        aria_label: el.getAttribute('aria-label') || null,
                        data_attributes: Array.from(el.attributes)
                            .filter(attr => attr.name.startsWith('data-'))
                            .reduce((acc, attr) => {
                                acc[attr.name] = attr.value;
                                return acc;
                            }, {}),
                        is_visible: true,
                        is_enabled: !el.disabled,
                        position: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        },
                        selector: generateSelector(el)
                    });
                }
            });
            
            function generateSelector(el) {
                if (el.id) return `#${el.id}`;
                if (el.name) return `[name="${el.name}"]`;
                
                let path = [];
                while (el.parentElement) {
                    let selector = el.tagName.toLowerCase();
                    if (el.className) {
                        selector += '.' + el.className.trim().split(/\\s+/).join('.');
                    }
                    path.unshift(selector);
                    el = el.parentElement;
                    if (path.length > 3) break; // Limit depth
                }
                return path.join(' > ');
            }
            
            return buttons;
        }
        """
        
        try:
            buttons = self.page.evaluate(js_code)
        except Exception as e:
            logger.error(f"Error extracting buttons: {e}")
            buttons = []
            
        return buttons
    
    def _extract_text_inputs(self) -> List[Dict[str, Any]]:
        """Extract all text input elements from the page."""
        js_code = """
        () => {
            const inputs = [];
            const selectors = [
                'input[type="text"]',
                'input[type="email"]',
                'input[type="tel"]',
                'input[type="number"]',
                'input[type="search"]',
                'input[type="date"]',
                'input[type="time"]',
                'input:not([type])',
                'textarea'
            ];
            
            const elements = document.querySelectorAll(selectors.join(','));
            
            elements.forEach((el, index) => {
                if (el.offsetParent !== null) {
                    const rect = el.getBoundingClientRect();
                    inputs.push({
                        index: index,
                        tag: el.tagName.toLowerCase(),
                        type: el.type || 'text',
                        id: el.id || null,
                        name: el.name || null,
                        placeholder: el.placeholder || null,
                        value: el.value || '',
                        class: el.className || null,
                        aria_label: el.getAttribute('aria-label') || null,
                        label: findLabel(el),
                        is_required: el.required || false,
                        is_enabled: !el.disabled,
                        max_length: el.maxLength > 0 ? el.maxLength : null,
                        pattern: el.pattern || null,
                        position: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        },
                        selector: generateSelector(el)
                    });
                }
            });
            
            function findLabel(el) {
                // Try to find associated label
                if (el.id) {
                    const label = document.querySelector(`label[for="${el.id}"]`);
                    if (label) return label.innerText.trim();
                }
                
                // Check if input is inside a label
                const parentLabel = el.closest('label');
                if (parentLabel) return parentLabel.innerText.trim();
                
                return null;
            }
            
            function generateSelector(el) {
                if (el.id) return `#${el.id}`;
                if (el.name) return `[name="${el.name}"]`;
                
                let path = [];
                let current = el;
                while (current.parentElement) {
                    let selector = current.tagName.toLowerCase();
                    if (current.className) {
                        selector += '.' + current.className.trim().split(/\\s+/).join('.');
                    }
                    path.unshift(selector);
                    current = current.parentElement;
                    if (path.length > 3) break;
                }
                return path.join(' > ');
            }
            
            return inputs;
        }
        """
        
        try:
            inputs = self.page.evaluate(js_code)
        except Exception as e:
            logger.error(f"Error extracting text inputs: {e}")
            inputs = []
            
        return inputs
    
    def _extract_dropdowns(self) -> List[Dict[str, Any]]:
        """Extract all select dropdown elements from the page."""
        js_code = """
        () => {
            const dropdowns = [];
            const selects = document.querySelectorAll('select');
            
            selects.forEach((el, index) => {
                if (el.offsetParent !== null) {
                    const rect = el.getBoundingClientRect();
                    const options = Array.from(el.options).map(opt => ({
                        text: opt.text,
                        value: opt.value,
                        selected: opt.selected
                    }));
                    
                    dropdowns.push({
                        index: index,
                        id: el.id || null,
                        name: el.name || null,
                        class: el.className || null,
                        label: findLabel(el),
                        current_value: el.value,
                        options: options,
                        is_multiple: el.multiple,
                        is_enabled: !el.disabled,
                        position: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        },
                        selector: generateSelector(el)
                    });
                }
            });
            
            function findLabel(el) {
                if (el.id) {
                    const label = document.querySelector(`label[for="${el.id}"]`);
                    if (label) return label.innerText.trim();
                }
                const parentLabel = el.closest('label');
                if (parentLabel) return parentLabel.innerText.trim();
                return null;
            }
            
            function generateSelector(el) {
                if (el.id) return `#${el.id}`;
                if (el.name) return `[name="${el.name}"]`;
                return `select:nth-of-type(${index + 1})`;
            }
            
            return dropdowns;
        }
        """
        
        try:
            dropdowns = self.page.evaluate(js_code)
        except Exception as e:
            logger.error(f"Error extracting dropdowns: {e}")
            dropdowns = []
            
        return dropdowns
    
    def _extract_links(self) -> List[Dict[str, Any]]:
        """Extract all link elements from the page."""
        js_code = """
        () => {
            const links = [];
            const elements = document.querySelectorAll('a[href]');
            
            elements.forEach((el, index) => {
                if (el.offsetParent !== null) {
                    const rect = el.getBoundingClientRect();
                    links.push({
                        index: index,
                        text: el.innerText?.trim() || '',
                        href: el.href,
                        id: el.id || null,
                        class: el.className || null,
                        aria_label: el.getAttribute('aria-label') || null,
                        target: el.target || null,
                        position: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        },
                        selector: generateSelector(el)
                    });
                }
            });
            
            function generateSelector(el) {
                if (el.id) return `#${el.id}`;
                return `a[href="${el.getAttribute('href')}"]`;
            }
            
            return links;
        }
        """
        
        try:
            links = self.page.evaluate(js_code)
        except Exception as e:
            logger.error(f"Error extracting links: {e}")
            links = []
            
        return links
    
    def _extract_clickable_elements(self) -> List[Dict[str, Any]]:
        """Extract other clickable elements (divs, spans with onclick, etc.)."""
        js_code = """
        () => {
            const clickables = [];
            const elements = document.querySelectorAll('[onclick], [role="tab"], [role="menuitem"]');
            
            elements.forEach((el, index) => {
                if (el.offsetParent !== null && el.tagName !== 'BUTTON' && el.tagName !== 'A') {
                    const rect = el.getBoundingClientRect();
                    clickables.push({
                        index: index,
                        tag: el.tagName.toLowerCase(),
                        text: el.innerText?.trim() || '',
                        id: el.id || null,
                        class: el.className || null,
                        role: el.getAttribute('role') || null,
                        aria_label: el.getAttribute('aria-label') || null,
                        has_onclick: el.hasAttribute('onclick'),
                        position: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        },
                        selector: generateSelector(el)
                    });
                }
            });
            
            function generateSelector(el) {
                if (el.id) return `#${el.id}`;
                let selector = el.tagName.toLowerCase();
                if (el.className) {
                    selector += '.' + el.className.trim().split(/\\s+/).join('.');
                }
                return selector;
            }
            
            return clickables;
        }
        """
        
        try:
            clickables = self.page.evaluate(js_code)
        except Exception as e:
            logger.error(f"Error extracting clickable elements: {e}")
            clickables = []
            
        return clickables
    
    def _extract_forms(self) -> List[Dict[str, Any]]:
        """Extract form elements and their structure."""
        js_code = """
        () => {
            const forms = [];
            const formElements = document.querySelectorAll('form');
            
            formElements.forEach((form, index) => {
                const inputs = Array.from(form.querySelectorAll('input, textarea, select')).map(el => ({
                    type: el.type || el.tagName.toLowerCase(),
                    name: el.name,
                    id: el.id,
                    required: el.required
                }));
                
                forms.push({
                    index: index,
                    id: form.id || null,
                    name: form.name || null,
                    action: form.action || null,
                    method: form.method || null,
                    inputs: inputs,
                    selector: form.id ? `#${form.id}` : `form:nth-of-type(${index + 1})`
                });
            });
            
            return forms;
        }
        """
        
        try:
            forms = self.page.evaluate(js_code)
        except Exception as e:
            logger.error(f"Error extracting forms: {e}")
            forms = []
            
        return forms
    
    def _extract_visible_text(self) -> str:
        """Extract main visible text content from the page."""
        js_code = """
        () => {
            // Get text from main content areas, excluding scripts, styles, etc.
            const body = document.body;
            const clone = body.cloneNode(true);
            
            // Remove script, style, and other non-content elements
            const toRemove = clone.querySelectorAll('script, style, noscript, iframe');
            toRemove.forEach(el => el.remove());
            
            return clone.innerText?.trim().substring(0, 5000) || ''; // Limit to 5000 chars
        }
        """
        
        try:
            text = self.page.evaluate(js_code)
        except Exception as e:
            logger.error(f"Error extracting visible text: {e}")
            text = ""
            
        return text
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def save_state(self, filepath: str = "page_state.json") -> None:
        """
        Observe the current state and save it to a JSON file.
        
        Args:
            filepath: Path where the JSON file should be saved
        """
        state = self.observe()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Page state saved to {filepath}")
    
    def get_state_summary(self) -> str:
        """
        Get a human-readable summary of the current page state.
        
        Returns:
            String summary of the page state
        """
        state = self.observe()
        
        summary = f"""
Page State Summary
==================
URL: {state['url']}
Title: {state['title']}

Interactive Elements:
- Buttons: {len(state['buttons'])}
- Text Inputs: {len(state['text_inputs'])}
- Dropdowns: {len(state['select_dropdowns'])}
- Links: {len(state['links'])}
- Other Clickable: {len(state['clickable_elements'])}
- Forms: {len(state['form_elements'])}

Timestamp: {state['timestamp']}
"""
        return summary


# Example usage
if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Navigate to OpenTable (example)
        page.goto("https://www.opentable.com")
        page.wait_for_load_state("networkidle")
        
        # Create observer and extract state
        observer = DOMObserver(page)
        
        # Print summary
        print(observer.get_state_summary())
        
        # Save full state to JSON
        observer.save_state("opentable_state.json")
        
        browser.close()