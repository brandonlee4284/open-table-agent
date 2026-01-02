# observer.py
# DOM State Observer Module
#
# This module observes the current DOM state and extracts interactive elements
# that can be used by the planner to create action plans.

from __future__ import annotations

import datetime as dt
from typing import Any, Dict


def _utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


async def observe_dom_state(page) -> Dict[str, Any]:
    """
    Return a JSON-serializable snapshot of the current page DOM state.

    Expected output keys:
      url, title, buttons, text_inputs, select_dropdowns, links,
      clickable_elements, form_elements, visible_text, timestamp
    """
    url = page.url
    title = await page.title()
    timestamp = _utc_iso()

    dom_snapshot = await page.evaluate(
        """
        () => {
          // Helpers
          const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            if (style.visibility === 'hidden' || style.display === 'none') return false;
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          };

          const isEnabled = (el) => {
            if (!el) return false;
            if (el.hasAttribute('disabled')) return false;
            const ariaDisabled = el.getAttribute('aria-disabled');
            if (ariaDisabled && ariaDisabled.toLowerCase() === 'true') return false;
            return true;
          };

          const safeText = (el) => {
            const t = (el.innerText || el.textContent || '').trim();
            return t.replace(/\\s+/g, ' ').trim();
          };

          const getAriaLabel = (el) => {
            return (el.getAttribute('aria-label') || '').trim() || null;
          };

          const getSelector = (el) => {
            if (el.id) return `#${CSS.escape(el.id)}`;

            const testId =
              el.getAttribute('data-testid') ||
              el.getAttribute('data-test') ||
              el.getAttribute('data-qa');

            if (testId) {
              // Return a selector that can match any of these attrs if present
              return `[data-testid="${testId}"],[data-test="${testId}"],[data-qa="${testId}"]`;
            }

            // nth-of-type fallback (brittle but usable)
            const tag = el.tagName.toLowerCase();
            let i = 1;
            let sib = el;
            while ((sib = sib.previousElementSibling) != null) {
              if (sib.tagName.toLowerCase() === tag) i++;
            }
            return `${tag}:nth-of-type(${i})`;
          };

          const getPosition = (el) => {
            const r = el.getBoundingClientRect();
            return {
              x: Math.round(r.x),
              y: Math.round(r.y),
              width: Math.round(r.width),
              height: Math.round(r.height)
            };
          };

          const elementToRecord = (el, index) => {
            const tag = el.tagName.toLowerCase();
            return {
              index,
              tag,
              text: safeText(el) || null,
              id: el.id || null,
              class: (el.className && typeof el.className === 'string') ? el.className : null,
              aria_label: getAriaLabel(el),
              is_visible: isVisible(el),
              is_enabled: isEnabled(el),
              position: getPosition(el),
              selector: getSelector(el)
            };
          };

          // Collect categories
          const buttons = Array.from(document.querySelectorAll('button, [role="button"]'))
            .map((el, idx) => elementToRecord(el, idx))
            .filter(r => r.is_visible);

          const text_inputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type]), input[type="search"], textarea'))
            .map((el, idx) => {
              const base = elementToRecord(el, idx);
              const inputEl = el;
              base.placeholder = (inputEl.getAttribute('placeholder') || '').trim() || null;
              base.value = (inputEl.value || '').toString();
              base.type = (inputEl.getAttribute('type') || (inputEl.tagName.toLowerCase() === 'textarea' ? 'textarea' : 'text'));

              // Best-effort label extraction
              const labelId = inputEl.getAttribute('aria-labelledby');
              let labelText = null;
              if (labelId) {
                const labelNode = document.getElementById(labelId);
                if (labelNode) labelText = safeText(labelNode);
              }
              base.label = labelText || base.aria_label || null;
              return base;
            })
            .filter(r => r.is_visible);

          const select_dropdowns = Array.from(document.querySelectorAll('select'))
            .map((el, idx) => {
              const base = elementToRecord(el, idx);
              base.value = el.value || null;
              base.options = Array.from(el.options).slice(0, 50).map(o => ({
                value: o.value,
                text: (o.textContent || '').trim()
              }));
              return base;
            })
            .filter(r => r.is_visible);

          const links = Array.from(document.querySelectorAll('a[href]'))
            .map((el, idx) => {
              const base = elementToRecord(el, idx);
              base.href = el.getAttribute('href');
              return base;
            })
            .filter(r => r.is_visible);

          const clickable_elements = Array.from(document.querySelectorAll('[onclick], [role="link"], [tabindex]'))
            .map((el, idx) => elementToRecord(el, idx))
            .filter(r => r.is_visible);

          const form_elements = Array.from(document.querySelectorAll('form'))
            .map((el, idx) => {
              const base = elementToRecord(el, idx);
              base.action = el.getAttribute('action');
              base.method = el.getAttribute('method');
              return base;
            })
            .filter(r => r.is_visible);

          // Visible text (trim to avoid huge snapshots)
          const visible_text = (document.body && document.body.innerText)
            ? document.body.innerText.replace(/\\s+/g, ' ').trim().slice(0, 2000)
            : '';

          return {
            buttons,
            text_inputs,
            select_dropdowns,
            links,
            clickable_elements,
            form_elements,
            visible_text
          };
        }
        """
    )

    return {
        "url": url,
        "title": title,
        "buttons": dom_snapshot["buttons"],
        "text_inputs": dom_snapshot["text_inputs"],
        "select_dropdowns": dom_snapshot["select_dropdowns"],
        "links": dom_snapshot["links"],
        "clickable_elements": dom_snapshot["clickable_elements"],
        "form_elements": dom_snapshot["form_elements"],
        "visible_text": dom_snapshot["visible_text"],
        "timestamp": timestamp,
    }
