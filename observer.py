"""
observer.py - DOM State Observer Module

This module observes the current DOM state and extracts all interactive elements
that can be used by the planner to create action plans.

expected output (format):
{
  "url": "https://www.opentable.com",
  "title": "OpenTable: Find Restaurants",
  "buttons": [
    {
      "index": 0,
      "tag": "button",
      "text": "Search",
      "id": "search-btn",
      "class": "btn-primary",
      "aria_label": "Search restaurants",
      "is_visible": true,
      "is_enabled": true,
      "position": {"x": 100, "y": 200, "width": 80, "height": 40},
      "selector": "#search-btn"
    }
  ],
  "text_inputs": [...],
  "select_dropdowns": [...],
  "links": [...],
  "clickable_elements": [...],
  "form_elements": [...],
  "visible_text": "Welcome to OpenTable...",
  "timestamp": "2025-12-31T10:30:00"
}
"""
