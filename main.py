"""
main.py - Full pipeline with Observer → Planner → Executor → Verifier loop

Runs the complete automation loop until end state is reached.
"""

import json
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from observer import DOMObserver
from planner import Planner
from executor import Executor
from verifier import Verifier


def main():
    """Run the complete automation pipeline with loop."""
    
    # Check for API key
    if not os.getenv("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY not set")
        print("Get your key from: https://makersuite.google.com/app/apikey")
        print("Then run: export GEMINI_API_KEY='your-key-here'")
        sys.exit(1)
    
    # Get task from command line or use default
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else \
           "Book me a reservation for Fleming's Steakhouse at 7pm for 2 people on January 2"
    
    # Create output directory
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    print(f"\n{'='*70}")
    print(f"OpenTable Reservation Bot")
    print(f"{'='*70}")
    print(f"Task: {task}")
    print(f"Output: {output_dir}/")
    print(f"{'='*70}\n")
    
    # Start browser
    print("Starting browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://www.opentable.com", wait_until="networkidle")
        print("✓ Browser ready\n")
        
        # Initialize components
        observer = DOMObserver(page)
        planner = Planner(model_name="gemini-flash-latest")
        executor = Executor(page)
        verifier = Verifier(page)
        
        # Main loop
        iteration = 0
        max_iterations = 15
        
        while iteration < max_iterations:
            print(f"{'='*70}")
            print(f"ITERATION {iteration + 1}")
            print(f"{'='*70}\n")
            
            # STEP 1: OBSERVE (TO DO)
            print(f"[{iteration + 1}] Observing page state...")
            page_state = observer.observe()
            print(f"    ✓ Found {len(page_state['buttons'])} buttons, "
                  f"{len(page_state['text_inputs'])} inputs")
            
            # Save state
            state_file = output_dir / f"state_{iteration:03d}.json"
            with open(state_file, "w") as f:
                json.dump(page_state, f, indent=2)
            
            # STEP 2: PLAN
            print(f"[{iteration + 1}] Generating plan...")
            plan = planner.plan(task=task, page_state=page_state)
            print(f"    ✓ Decision: {plan['decision']}")
            print(f"    ✓ Reason: {plan['reason'][:80]}...")
            
            # Save plan
            plan_file = output_dir / f"plan_{iteration:03d}.json"
            with open(plan_file, "w") as f:
                json.dump(plan, f, indent=2)
            
            # Handle decision
            if plan['decision'] == 'stop':
                print(f"\n{'='*70}")
                print("STOPPING: Planner decided to stop")
                print(f"{'='*70}")
                print(f"Status: {plan['stop_state']['status']}")
                print(f"Summary: {plan['stop_state'].get('summary', {})}")
                break
            
            elif plan['decision'] == 'ask':
                print(f"\n{'='*70}")
                print("PAUSING: Need more information")
                print(f"{'='*70}")
                print(f"Question: {plan['question']['text']}")
                print(f"Fields needed: {', '.join(plan['question']['fields_needed'])}")
                break
            
            elif plan['decision'] == 'act':
                action = plan['chosen_action']
                print(f"    ✓ Action: {action['type']} on {action['target']['strategy']}={action['target']['value'][:50]}")
                
                # STEP 3: EXECUTE
                print(f"[{iteration + 1}] Executing action...")
                result = executor.execute(action)
                
                if result['ok']:
                    print(f"    ✓ Success")
                    if result['signals_seen']:
                        print(f"    ✓ Signals: {', '.join(result['signals_seen'])}")
                else:
                    print(f"    ✗ Failed: {result.get('error', 'Unknown error')}")
                
                # Save execution result
                exec_file = output_dir / f"execution_{iteration:03d}.json"
                with open(exec_file, "w") as f:
                    json.dump({
                        **result,
                        "screenshot_after": f"<{len(result['screenshot_after'])} chars>"
                    }, f, indent=2)
                
                # Save screenshot
                if result['screenshot_after']:
                    import base64
                    screenshot_data = base64.b64decode(result['screenshot_after'])
                    screenshot_file = output_dir / f"screenshot_{iteration:03d}.png"
                    with open(screenshot_file, "wb") as f:
                        f.write(screenshot_data)
                
                # STEP 4: VERIFY
                print(f"[{iteration + 1}] Verifying state...")
                verification = verifier.verify(result)
                print(f"    ✓ Status: {verification['status']}")
                print(f"    ✓ Reason: {verification['reason'][:80]}...")
                
                # Save verification
                verify_file = output_dir / f"verification_{iteration:03d}.json"
                with open(verify_file, "w") as f:
                    json.dump(verification, f, indent=2)
                
                # Check verification status
                if verification['status'] == 'finish':
                    print(f"\n{'='*70}")
                    print("✓ SUCCESS: Reached booking review page!")
                    print(f"{'='*70}")
                    print(f"End button detected: {verification['details'].get('end_button_text')}")
                    print(f"Current URL: {verification['current_url']}")
                    print("\nStopping before final confirmation (as designed)")
                    break
                
                elif verification['status'] == 'pause':
                    print(f"\n{'='*70}")
                    print("⚠ PAUSED: Issue detected")
                    print(f"{'='*70}")
                    print(f"Reason: {verification['reason']}")
                    break
                
                elif verification['status'] == 'continue':
                    print(f"    ✓ Continuing to next iteration...\n")
                    iteration += 1
                    continue
            
            else:
                print(f"\n✗ Unknown decision: {plan['decision']}")
                break
        
        # Check if max iterations reached
        if iteration >= max_iterations:
            print(f"\n{'='*70}")
            print(f"⚠ WARNING: Maximum iterations ({max_iterations}) reached")
            print(f"{'='*70}\n")
        
        # Final summary
        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        print(f"Total iterations: {iteration + 1}")
        print(f"Final URL: {page.url}")
        print(f"Output directory: {output_dir}/")
        print(f"{'='*70}\n")
        
        # Keep browser open for review
        input("Press Enter to close browser...")
        browser.close()


if __name__ == "__main__":
    main()