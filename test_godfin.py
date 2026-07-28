#!/usr/bin/env python3
"""Test GODFIN app to identify and fix errors."""

from playwright.sync_api import sync_playwright
import sys

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Capture console messages
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))

        # Navigate to the app
        print("Navigating to http://localhost:5204...")
        page.goto('http://localhost:5204')
        page.wait_for_load_state('networkidle')

        # Take screenshot
        page.screenshot(path='/tmp/godfin_home.png', full_page=True)
        print("Screenshot saved to /tmp/godfin_home.png")

        # Check page title/content
        print(f"Page title: {page.title()}")
        content = page.content()
        print(f"Page has content length: {len(content)}")

        # Print console messages
        print("\n--- Console Messages ---")
        for msg in console_messages:
            print(msg)

        browser.close()
        print("\nDone!")

if __name__ == "__main__":
    main()
