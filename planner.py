"""
planner.py - Planning Agent for Browser Automation

This module uses an LLM to plan the next action based on the current page state.
"""

import json
import logging
from typing import Dict, Any, Optional, List
import google.generativeai as genai
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Planner:
    """Plans the next action using an LLM based on page state."""
    
    # Hard-coded constraints
    CONSTRAINTS = {
        "allowed_domains": ["opentable.com"],
        "forbidden_actions": [
            "finalize_booking",
            "complete_reservation", 
            "confirm_payment",
            "login",
            "signup",
            "message_restaurant"
        ],
        "stop_at_review": True
    }
    
    SYSTEM_PROMPT = """You are the PLANNER for a browser automation system. Your job is to decide the NEXT best action to accomplish the user's task given the current PageState from an observer.

You must follow these rules:
- Output MUST be valid JSON and MUST match the schema below exactly. No extra keys. No extra text.
- Choose exactly ONE of: decision = "act" | "ask" | "stop".
- If decision="act", you MUST generate 2–4 candidate actions and then select exactly ONE chosen_action.
- Candidates MUST reference only targets that exist in page_state.elements. Do not invent selectors, text, or elements.
- Obey all constraints. Never propose forbidden actions.
- This agent must STOP at the PRE-BOOKING REVIEW state: a screen where the next click would finalize the reservation (e.g., a primary CTA like "Complete reservation/Confirm" plus a visible summary of restaurant/date/time/party size). In that state, decision MUST be "stop".
- Never click the final booking/confirmation button. Never pay. Never message. Never log in unless explicitly allowed.
- Prefer robust target strategies in this order: "eid" (if provided) > role+name > aria-label > exact visible text > css (only if observer provides stable css).
- If required information to proceed is missing (e.g., location, date, time, party size, restaurant name), decide="ask" and ask ONE concise question.
- If the page is blocked, erroring, or ambiguous and you cannot safely proceed using existing elements, decide="ask" (do not guess).

Scoring requirements for candidates:
- For each candidate, score 0–5 (integers) for:
  - goal_progress: how much this advances the task
  - safety: how well it avoids irreversible or forbidden actions
  - robustness: how likely it is to work across UI variants (avoid brittle selectors)
  - success: how likely it is to succeed given the current page_state (element visible/enabled, no blockers)
- Total score = sum of the four scores.
- Choose the candidate with the highest total score as chosen_action.
- If there is a tie, prefer higher safety, then robustness.

JSON SCHEMA (output must conform exactly):
{
  "decision": "act" | "ask" | "stop",
  "reason": string,
  "candidates": [
    {
      "action": {
        "type": "click" | "fill" | "select" | "navigate" | "scroll" | "wait",
        "target": {
          "strategy": "eid" | "role" | "aria" | "text" | "css" | "id",
          "value": string,
          "role": string?,
          "name": string?
        },
        "value": string?,
        "expect": {
          "signals": string[],
          "timeout_ms": number?
        }?
      },
      "scores": {
        "goal_progress": 0|1|2|3|4|5,
        "safety": 0|1|2|3|4|5,
        "robustness": 0|1|2|3|4|5,
        "success": 0|1|2|3|4|5,
        "total": number
      },
      "why": string
    }
  ],
  "chosen_action": {
    "type": "click" | "fill" | "select" | "navigate" | "scroll" | "wait",
    "target": {
      "strategy": "eid" | "role" | "aria" | "text" | "css" | "id",
      "value": string,
      "role": string?,
      "name": string?
    },
    "value": string?,
    "expect": {
      "signals": string[],
      "timeout_ms": number?
    }?
  }?,
  "question": {
    "text": string,
    "fields_needed": string[]
  }?,
  "stop_state": {
    "status": "ready_to_book" | "done" | "blocked",
    "summary": object
  }?
}

Important:
* If decision="ask", output ONLY: decision, reason, question. Do NOT include candidates or chosen_action.
* If decision="stop", output ONLY: decision, reason, stop_state. Do NOT include candidates or chosen_action.
* If decision="act", include: decision, reason, candidates (2–4 items), chosen_action.
* candidates must be 2–4 entries; no more, no fewer.
* Always compute and include scores.total.
* Never output null values. Omit optional objects/fields entirely if not used.
* Only output valid JSON, no markdown formatting or code blocks."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-flash-latest"):
        """
        Initialize the Planner with Gemini API.
        
        Args:
            api_key: Google AI Studio API key (or set GEMINI_API_KEY env var)
            model_name: Model to use (gemini-1.5-flash or gemini-1.5-pro)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be provided or set as environment variable")
        
        genai.configure(api_key=self.api_key)
        self.model_name = model_name
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": 0.1,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
            }
        )
        self.memory: List[Dict[str, Any]] = []
        
        logger.info(f"Planner initialized with model: {model_name}")
    
    def plan(
        self,
        task: str,
        page_state: Dict[str, Any],
        custom_constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a plan for the next action.
        
        Args:
            task: User's goal (e.g., "Book a table at Ruth's Chris for 7pm")
            page_state: Current page state from observer
            custom_constraints: Optional custom constraints (merged with defaults)
            
        Returns:
            Plan dictionary matching the JSON schema
        """
        # Merge constraints
        constraints = {**self.CONSTRAINTS}
        if custom_constraints:
            constraints.update(custom_constraints)
        
        # Build the input payload
        planner_input = {
            "task": task,
            "constraints": constraints,
            "memory": self._get_memory_summary(),
            "page_state": self._simplify_page_state(page_state)
        }
        
        # Create the prompt
        user_prompt = f"""USER INPUT:
{json.dumps(planner_input, indent=2)}

Analyze the current page state and decide the next action. Output ONLY valid JSON matching the schema."""
        
        # Call the LLM
        try:
            logger.info("Sending request to Gemini API...")
            response = self.model.generate_content([
                self.SYSTEM_PROMPT,
                user_prompt
            ])
            
            # Extract and parse the response
            response_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith("```json"):
                response_text = response_text.split("```json")[1]
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
            if response_text.endswith("```"):
                response_text = response_text.rsplit("```", 1)[0]
            
            response_text = response_text.strip()
            
            # Parse JSON
            plan = json.loads(response_text)
            
            # Validate the plan
            self._validate_plan(plan)
            
            # Store in memory if it's an action
            if plan.get("decision") == "act" and plan.get("chosen_action"):
                self.memory.append({
                    "action": plan["chosen_action"],
                    "reason": plan["reason"],
                    "page_url": page_state.get("url", "unknown")
                })
            
            logger.info(f"Plan generated: decision={plan['decision']}, reason={plan['reason'][:100]}...")
            return plan
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response text: {response_text}")
            raise ValueError(f"LLM returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Error generating plan: {e}")
            raise
    
    def _simplify_page_state(self, page_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simplify page state to reduce token usage while keeping essential info.
        """
        simplified = {
            "url": page_state.get("url", ""),
            "title": page_state.get("title", ""),
            "elements": {
                "buttons": [],
                "text_inputs": [],
                "select_dropdowns": [],
                "links": []
            }
        }
        
        # Simplify buttons - keep only essential fields
        for btn in page_state.get("buttons", [])[:20]:  # Limit to 20 most relevant
            simplified["elements"]["buttons"].append({
                "text": btn.get("text", ""),
                "id": btn.get("id"),
                "aria_label": btn.get("aria_label"),
                "selector": btn.get("selector"),
                "is_enabled": btn.get("is_enabled", True),
                "class": btn.get("class")
            })
        
        # Simplify text inputs
        for inp in page_state.get("text_inputs", [])[:15]:
            simplified["elements"]["text_inputs"].append({
                "type": inp.get("type", "text"),
                "id": inp.get("id"),
                "name": inp.get("name"),
                "placeholder": inp.get("placeholder"),
                "label": inp.get("label"),
                "selector": inp.get("selector"),
                "is_enabled": inp.get("is_enabled", True)
            })
        
        # Simplify dropdowns
        for dd in page_state.get("select_dropdowns", [])[:10]:
            simplified["elements"]["select_dropdowns"].append({
                "id": dd.get("id"),
                "name": dd.get("name"),
                "label": dd.get("label"),
                "options": dd.get("options", [])[:20],  # Limit options
                "selector": dd.get("selector"),
                "current_value": dd.get("current_value")
            })
        
        # Simplify links - focus on navigation-relevant ones
        for link in page_state.get("links", [])[:15]:
            if link.get("text"):  # Only include links with text
                simplified["elements"]["links"].append({
                    "text": link.get("text", ""),
                    "href": link.get("href", ""),
                    "selector": link.get("selector")
                })
        
        # Add visible text snippet for context
        visible_text = page_state.get("visible_text", "")
        if visible_text:
            simplified["visible_text_snippet"] = visible_text[:1000]
        
        return simplified
    
    def _get_memory_summary(self) -> Dict[str, Any]:
        """Get a summary of past actions."""
        return {
            "action_count": len(self.memory),
            "recent_actions": self.memory[-5:] if self.memory else []
        }
    
    def _validate_plan(self, plan: Dict[str, Any]) -> None:
        """Validate that the plan matches the required schema."""
        if "decision" not in plan:
            raise ValueError("Plan missing 'decision' field")
        
        decision = plan["decision"]
        if decision not in ["act", "ask", "stop"]:
            raise ValueError(f"Invalid decision: {decision}")
        
        if decision == "act":
            if "candidates" not in plan:
                raise ValueError("decision='act' requires 'candidates'")
            if not (2 <= len(plan["candidates"]) <= 4):
                raise ValueError(f"candidates must have 2-4 items, got {len(plan['candidates'])}")
            if "chosen_action" not in plan:
                raise ValueError("decision='act' requires 'chosen_action'")
        
        if decision == "ask":
            if "question" not in plan:
                raise ValueError("decision='ask' requires 'question'")
        
        if decision == "stop":
            if "stop_state" not in plan:
                raise ValueError("decision='stop' requires 'stop_state'")
    
    def clear_memory(self) -> None:
        """Clear the action memory."""
        self.memory = []
        logger.info("Memory cleared")
    
    def get_memory(self) -> List[Dict[str, Any]]:
        """Get the full action memory."""
        return self.memory.copy()
    
    def save_memory(self, filepath: str = "planner_memory.json") -> None:
        """Save memory to a JSON file."""
        with open(filepath, 'w') as f:
            json.dump(self.memory, f, indent=2)
        logger.info(f"Memory saved to {filepath}")
    
    def load_memory(self, filepath: str = "planner_memory.json") -> None:
        """Load memory from a JSON file."""
        try:
            with open(filepath, 'r') as f:
                self.memory = json.load(f)
            logger.info(f"Memory loaded from {filepath}")
        except FileNotFoundError:
            logger.warning(f"Memory file not found: {filepath}")


# Example usage
if __name__ == "__main__":
    import sys
    
    # Example: Load a page state and generate a plan
    if len(sys.argv) < 2:
        print("Usage: python planner.py <page_state.json>")
        sys.exit(1)
    
    # Load page state from observer output
    with open(sys.argv[1], 'r') as f:
        page_state = json.load(f)
    
    # Initialize planner
    planner = Planner(model_name="gemini-flash-latest")
    
    # Example task
    task = "Book me a reservation for Ruth's Chris Steak House at 7pm for 2 people"
    
    # Generate plan
    plan = planner.plan(task=task, page_state=page_state)
    
    # Print the plan
    print("\nGenerated Plan:")
    print(json.dumps(plan, indent=2))
    
    # Show decision
    print(f"\nDecision: {plan['decision']}")
    print(f"Reason: {plan['reason']}")
    
    if plan['decision'] == 'act':
        print(f"\nChosen Action: {plan['chosen_action']['type']}")
        print(f"Target: {plan['chosen_action']['target']}")