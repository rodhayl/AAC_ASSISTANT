import os
import sys

from playwright.sync_api import sync_playwright

STUDENT_USERNAME = os.environ.get("AAC_STUDENT_USERNAME", "").strip()
STUDENT_PASSWORD = os.environ.get("AAC_STUDENT_PASSWORD", "").strip()
ADMIN_USERNAME = os.environ.get("AAC_ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD = os.environ.get("AAC_ADMIN_PASSWORD", "").strip()

if not STUDENT_USERNAME or not STUDENT_PASSWORD or not ADMIN_USERNAME or not ADMIN_PASSWORD:
    raise SystemExit(
        "Set AAC_STUDENT_USERNAME, AAC_STUDENT_PASSWORD, AAC_ADMIN_USERNAME, "
        "and AAC_ADMIN_PASSWORD before running this script."
    )


def verify_rbac():
    print("Starting RBAC Verification...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Capture console logs
        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))
        page.on("pageerror", lambda exc: print(f"BROWSER ERROR: {exc}"))

        try:
            # Test 1: Student Login (Should NOT see 'Students' or 'Symbols')
            print("\n--- Testing Student Role ---")
            page.goto("http://localhost:5176/login")
            print(f"Logging in as {STUDENT_USERNAME}...")
            page.fill("input[type='text']", STUDENT_USERNAME)
            page.fill("input[type='password']", STUDENT_PASSWORD)
            page.click("button[type='submit']")

            # Increase timeout significantly for first login/warmup
            try:
                page.wait_for_url("**/", timeout=60000)
                print(f"Logged in as {STUDENT_USERNAME}.")
            except Exception as e:
                print(f"Timeout waiting for login. Current URL: {page.url}")
                # Screenshot for debugging (optional, requires path)
                # page.screenshot(path="login_timeout.png")
                print(f"Page content snippet: {page.content()[:500]}")
                raise e

            # Wait for sidebar
            page.wait_for_selector("nav", timeout=30000)

            # Check links
            sidebar_text = page.locator("nav").text_content()
            print(f"Sidebar links visible: {sidebar_text}")

            if "Students" in sidebar_text or "Estudiantes" in sidebar_text:
                print("❌ FAILED: Student can see 'Students' link.")
                sys.exit(1)
            else:
                print("✅ PASSED: 'Students' link hidden for student.")

            if "Symbols" in sidebar_text or "Símbolos" in sidebar_text:
                print("❌ FAILED: Student can see 'Symbols' link.")
                sys.exit(1)
            else:
                print("✅ PASSED: 'Symbols' link hidden for student.")

            # Logout
            print("Logging out...")
            # Try to click the logout button (looking for Spanish or English text)
            try:
                page.locator(
                    "button:has-text('Cerrar sesión'), button:has-text('Sign Out')"
                ).click()
            except Exception:
                # Fallback: click the last button which is likely the logout button
                print("Could not find logout button by text, trying last button...")
                page.locator("button").last.click()

            page.wait_for_url("**/login")

            # Test 2: Admin Login (Should see ALL)
            print("\n--- Testing Admin Role ---")
            page.fill("input[type='text']", ADMIN_USERNAME)
            page.fill("input[type='password']", ADMIN_PASSWORD)
            page.click("button[type='submit']")
            page.wait_for_url("**/", timeout=30000)
            print(f"Logged in as {ADMIN_USERNAME}.")

            page.wait_for_selector("nav")
            sidebar_text = page.locator("nav").text_content()

            # Check for Students link (English or Spanish)
            if "Students" in sidebar_text or "Estudiantes" in sidebar_text:
                print("✅ PASSED: Admin can see 'Students' link.")
            else:
                print("❌ FAILED: Admin cannot see 'Students' link.")
                print(f"Visible links: {sidebar_text}")
                sys.exit(1)

            # Check for Symbols link
            if "Symbols" in sidebar_text or "Símbolos" in sidebar_text:
                print("✅ PASSED: Admin can see 'Symbols' link.")
            else:
                print("❌ FAILED: Admin cannot see 'Symbols' link.")
                print(f"Visible links: {sidebar_text}")
                sys.exit(1)

            print("\nRBAC Verification Complete.")

        except Exception as e:
            print(f"\n❌ EXCEPTION: {str(e)}")
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    verify_rbac()
