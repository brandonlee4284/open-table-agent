# OpenTable Reservation Bot

An agentic browser automation system that autonomously books restaurant reservations on OpenTable using a multi-agent architecture with LLM-powered planning.

## Overview

This system demonstrates a modular agentic architecture for web automation. The bot takes a natural language task (e.g., "Book me a table at Ruth's Chris for 7pm for 2 people") and autonomously navigates OpenTable's website to reach the booking review page—stopping just before final confirmation.

### Architecture

The system follows a continuous observe-plan-execute-verify loop:


---

## Agents

### 1. Observer (`observer.py`)

**Responsibilities:**
- Analyzes the current DOM state using JavaScript and Playwright
- Extracts all interactive elements (buttons, inputs, dropdowns, links, forms)
- Captures element metadata (IDs, labels, aria-labels, selectors, visibility, position)
- Extracts visible page text for context
- Generates structured JSON representation of page state

**Expected Output:**
```json
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
```

---

### 2. Planner (`planner.py`)

**Responsibilities:**
- Receives page state from Observer and user task
- Uses Google Gemini LLM (1.5 Flash/Pro) to analyze current state
- Generates 2-4 candidate actions with scoring metrics
- Scores each candidate on: goal_progress, safety, robustness, success (0-5 each)
- Selects the highest-scoring action as the chosen action
- Enforces safety constraints (never finalizes bookings, stays on OpenTable domain)
- Decides whether to: act (perform action), ask (need info), or stop (reached goal)

**Expected Output:**
```json
{
  "decision": "act",
  "reason": "Need to search for Ruth's Chris restaurant. The search input is visible and ready to be filled.",
  "candidates": [
    {
      "action": {
        "type": "fill",
        "target": {
          "strategy": "id",
          "value": "restaurant-search"
        },
        "value": "Ruth's Chris Steak House"
      },
      "scores": {
        "goal_progress": 5,
        "safety": 5,
        "robustness": 4,
        "success": 5,
        "total": 19
      },
      "why": "Filling the search box with restaurant name directly advances the booking goal"
    },
    {
      "action": {
        "type": "click",
        "target": {
          "strategy": "text",
          "value": "Find a Table"
        }
      },
      "scores": {
        "goal_progress": 3,
        "safety": 5,
        "robustness": 3,
        "success": 4,
        "total": 15
      },
      "why": "Clicking the main CTA would start the flow but requires more steps"
    }
  ],
  "chosen_action": {
    "type": "fill",
    "target": {
      "strategy": "id",
      "value": "restaurant-search"
    },
    "value": "Ruth's Chris Steak House",
    "expect": {
      "signals": ["input_filled"],
      "timeout_ms": 2000
    }
  }
}
```

**Alternative Decisions:**

If decision is `"ask"`:
```json
{
  "decision": "ask",
  "reason": "Missing required information to proceed",
  "question": {
    "text": "What city or location should I search in?",
    "fields_needed": ["location"]
  }
}
```

If decision is `"stop"`:
```json
{
  "decision": "stop",
  "reason": "Reached booking review page with 'Complete Reservation' button",
  "stop_state": {
    "status": "ready_to_book",
    "summary": {
      "restaurant": "Ruth's Chris Steak House",
      "date": "2025-12-31",
      "time": "7:00 PM",
      "party_size": 2
    }
  }
}
```

---

### 3. Executor (`executor.py`)

**Responsibilities:**
- Receives action from Planner and executes it using Playwright
- Performs NO decision-making—pure execution only
- Supports action types: `click`, `fill`, `select`, `navigate`, `scroll`, `wait`
- Finds elements using multiple strategies: id, css, text, aria-label, role
- Captures pre/post URLs and detects signals (url_changed, network_idle)
- Takes screenshot after execution for debugging
- Returns structured success/failure result

**Expected Output:**
```json
{
  "ok": true,
  "action": {
    "type": "fill",
    "target": {
      "strategy": "id",
      "value": "restaurant-search"
    },
    "value": "Ruth's Chris Steak House"
  },
  "pre_url": "https://www.opentable.com",
  "post_url": "https://www.opentable.com/search",
  "signals_seen": ["url_changed", "network_idle"],
  "screenshot_after": "iVBORw0KGgoAAAANSUhEUgAA..." 
}
```

**Failure ouput:**
```json
{
  "ok": false,
  "action": {...},
  "pre_url": "https://www.opentable.com/search",
  "post_url": "https://www.opentable.com/search",
  "signals_seen": [],
  "screenshot_after": "...",
  "error": "Element not found: #non-existent-button"
}
```

---

### 4. Verifier (`verifier.py`)

**Responsibilities:**
- Analyzes execution result and current page state
- Detects end state by checking for final booking buttons ("Complete Reservation", "Confirm Reservation", etc.)
- Identifies blocked/error states (404s, error messages, access denied)
- Decides whether to: continue (loop back), finish (success), or pause (error/intervention needed)
- Provides reasoning for each decision

**Expected Output:**
```json
{
  "status": "continue",
  "reason": "Progress made, continuing to next step",
  "should_continue": true,
  "current_url": "https://www.opentable.com/booking/details",
  "end_state_detected": false,
  "details": {
    "url_changed": true,
    "signals": ["url_changed", "network_idle"]
  }
}
```

**End state**
```json
{
  "status": "finish",
  "reason": "Reached booking review page - 'Complete Reservation' button detected",
  "should_continue": false,
  "current_url": "https://www.opentable.com/booking/review",
  "end_state_detected": true,
  "details": {
    "end_button_text": "Complete Reservation",
    "booking_ready": true
  }
}
```

**Pause state:**
```json
{
  "status": "pause",
  "reason": "Execution failed: Element not found",
  "should_continue": false,
  "current_url": "https://www.opentable.com/booking",
  "end_state_detected": false,
  "details": {
    "error": "Element not found: #submit-button"
  }
}
```

---

## Installation

### Prerequisites
- Python 3.8+
- Google AI Studio API key (free from [makersuite.google.com](https://makersuite.google.com/app/apikey))

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd open-table-agent
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers**
   ```bash
   playwright install chromium
   ```

4. **Set API key**
   ```bash
   export GEMINI_API_KEY="your-api-key-here"
   ```

---

## Usage

### Basic Usage
```bash
python main.py
```

This will use the default task: *"Book me a reservation for Ruth's Chris Steak House at 7pm for 2 people"*

### What to Expect

The bot will:
1. Open a browser window (non-headless by default)
2. Navigate to OpenTable
3. Loop through observe → plan → execute → verify cycles
4. Print progress to console
5. Save detailed logs to `bot_output/` directory
6. **Stop at the booking review page** (before clicking "Complete Reservation")
7. Keep browser open for inspection

### Output Files

The system saves detailed logs for each iteration in `output/`:

```
output/
├── state_000.json           # Page state observations
├── plan_000.json            # LLM plans with candidates
├── execution_000.json       # Execution results
├── verification_000.json    # Verification decisions
├── screenshot_000.png       # Screenshots after each action
├── state_001.json
├── plan_001.json
...
└── memory.json              # Complete action history
```

---

## Configuration

### Model Selection
Change the LLM model in `main.py`:
```python
planner = Planner(model_name="gemini-flash-latest")  # or "gemini-pro-latest"
```

### Headless Mode
Run without GUI:
```python
browser = p.chromium.launch(headless=True)
```

### Max Iterations
Adjust safety limit in `main.py`:
```python
max_iterations = 15  # Default
```

---
