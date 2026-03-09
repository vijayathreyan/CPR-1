"""
core/kite_auth.py
─────────────────
Zerodha Kite Connect authentication using Selenium + pyotp.

Automated login flow:
  1. Opens Kite login page in headless Chrome
  2. Fills User ID and Password from .env
  3. Generates live TOTP via pyotp (same 6-digit code as your authenticator app)
  4. Submits TOTP
  5. Captures request_token from redirect URL
  6. Exchanges it for access_token via Kite API
  7. Saves access_token back to .env for reuse

Usage:
    from core.kite_auth import get_kite_client
    kite = get_kite_client()
"""

import os
import re
import time
import logging
from pathlib import Path

import pyotp
from dotenv import load_dotenv, set_key
from kiteconnect import KiteConnect

log      = logging.getLogger(__name__)
ENV_FILE = Path(__file__).parent.parent / ".env"


def generate_totp(secret: str) -> str:
    """Generate current 6-digit TOTP from the Base32 secret key."""
    code = pyotp.TOTP(secret).now()
    log.info(f"🔑  TOTP generated: {code}")
    return code


def _selenium_login(api_key: str, user_id: str,
                    password: str, totp_secret: str) -> str:
    """
    Drive headless Chrome through the Zerodha login page.
    Returns the request_token string extracted from the redirect URL.
    """
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    from webdriver_manager.chrome import ChromeDriverManager

    kite      = KiteConnect(api_key=api_key)
    login_url = kite.login_url()

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,800")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    log.info("🌐  Launching headless Chrome for Zerodha login…")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )
    wait = WebDriverWait(driver, 20)

    try:
        driver.get(login_url)
        log.info("    Login page opened")

        # User ID
        try:
            wait.until(EC.presence_of_element_located((By.ID, "userid"))).send_keys(user_id)
        except TimeoutException:
            raise TimeoutException("User ID field not found — check login page structure")

        # Password
        try:
            driver.find_element(By.ID, "password").send_keys(password)
        except NoSuchElementException:
            raise NoSuchElementException("Password field not found")

        # Submit login
        try:
            driver.find_element(By.XPATH, '//button[@type="submit"]').click()
        except NoSuchElementException:
            raise NoSuchElementException("Submit button not found")
        log.info("    Credentials submitted")

        # Wait for TOTP input (timeout after 15 seconds)
        try:
            totp_field = wait.until(EC.presence_of_element_located((
                By.XPATH,
                '//input[@type="number" or @autocomplete="one-time-code"]'
            )))
        except TimeoutException:
            raise TimeoutException("TOTP field not found within 20 seconds — credentials may be invalid")
        
        time.sleep(0.5)  # small pause so TOTP window is definitely fresh
        totp_field.send_keys(generate_totp(totp_secret))
        log.info("    TOTP entered")

        # Submit TOTP (some Kite versions auto-submit on 6 digits)
        try:
            driver.find_element(By.XPATH, '//button[@type="submit"]').click()
        except Exception:
            pass

        # Wait for redirect and extract request_token (max 10 seconds total)
        max_wait = 10
        elapsed = 0
        while elapsed < max_wait:
            time.sleep(2)
            url = driver.current_url
            match = re.search(r"request_token=([^&]+)", url)
            if match:
                token = match.group(1)
                log.info(f"✅  request_token captured: {token[:12]}…")
                return token
            elapsed += 2

        # Final attempt
        url = driver.current_url
        raise ValueError(
            f"request_token not found after {max_wait}s redirect wait.\n"
            f"Final URL: {url}\n"
            f"Verify credentials and TOTP secret in .env"
        )

    finally:
        driver.quit()


def authenticate(force_refresh: bool = False) -> KiteConnect:
    """
    Full authentication flow.

    Fast path : reuse KITE_ACCESS_TOKEN from .env if it is still valid.
    Full path : run Selenium login → generate fresh token → save to .env.

    Args:
        force_refresh: if True, always re-login even if a token exists.

    Returns:
        Authenticated KiteConnect instance ready to call market data APIs.
    """
    load_dotenv(ENV_FILE)

    api_key      = os.getenv("KITE_API_KEY",       "")
    api_secret   = os.getenv("KITE_API_SECRET",    "")
    user_id      = os.getenv("ZERODHA_USER_ID",    "")
    password     = os.getenv("ZERODHA_PASSWORD",   "")
    totp_secret  = os.getenv("ZERODHA_TOTP_SECRET","")
    access_token = os.getenv("KITE_ACCESS_TOKEN",  "")

    if not all([api_key, api_secret, user_id, password, totp_secret]):
        raise ValueError(
            "Missing credentials in .env — please set:\n"
            "  KITE_API_KEY, KITE_API_SECRET, ZERODHA_USER_ID,\n"
            "  ZERODHA_PASSWORD, ZERODHA_TOTP_SECRET"
        )

    kite = KiteConnect(api_key=api_key)

    # Fast path
    if access_token and not force_refresh:
        kite.set_access_token(access_token)
        try:
            profile = kite.profile()
            log.info(f"✅  Reusing saved token for: {profile.get('user_name')}")
            return kite
        except Exception as e:
            log.warning(f"⚠  Saved token is expired ({type(e).__name__}) — re-logging in…")

    # Full Selenium login with retries
    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            log.info(f"🔐  Starting automated Zerodha login (attempt {attempt}/{max_retries})…")
            request_token = _selenium_login(api_key, user_id, password, totp_secret)
            data          = kite.generate_session(request_token, api_secret=api_secret)
            new_token     = data["access_token"]

            if not ENV_FILE.exists():
                ENV_FILE.write_text("")
            set_key(str(ENV_FILE), "KITE_ACCESS_TOKEN", new_token)
            log.info("✅  New access_token saved to .env")

            kite.set_access_token(new_token)
            profile = kite.profile()
            log.info(f"✅  Logged in as: {profile.get('user_name')} ({profile.get('user_id')})")
            return kite
        
        except Exception as e:
            if attempt < max_retries:
                log.warning(f"❌  Login attempt {attempt} failed: {e}")
                time.sleep(2)  # Wait before retry
            else:
                log.error(f"❌  Login failed after {max_retries} attempts: {e}")
                raise


def get_kite_client(force_refresh: bool = False) -> KiteConnect:
    """Public entry point — returns authenticated KiteConnect instance."""
    return authenticate(force_refresh=force_refresh)
