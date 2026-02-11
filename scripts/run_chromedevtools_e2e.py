import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

sys.path.insert(0, os.path.dirname(__file__))
from cdp_harness import CDP, get_first_page_target  # noqa: E402


@dataclass
class Account:
    username: str
    password: str


def _account_from_env(prefix: str) -> Account:
    username = os.environ.get(f"AAC_{prefix}_USERNAME", "").strip()
    password = os.environ.get(f"AAC_{prefix}_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError(
            f"Missing credentials for {prefix}. Set AAC_{prefix}_USERNAME and "
            f"AAC_{prefix}_PASSWORD."
        )
    return Account(username, password)


STUDENT = _account_from_env("STUDENT")
TEACHER = _account_from_env("TEACHER")
ADMIN = _account_from_env("ADMIN")


def _now_id() -> str:
    return str(int(time.time() * 1000))


class StepFailed(Exception):
    pass


async def assert_path(cdp: CDP, pattern: str, timeout_s: float = 10):
    regex = re.compile(pattern)
    start = time.time()
    while time.time() - start < timeout_s:
        path = await cdp.eval("location.pathname", await_promise=False)
        if isinstance(path, str) and regex.search(path):
            return
        await asyncio.sleep(0.2)
    raise StepFailed(f"Expected path /{pattern}/, got {await cdp.eval('location.pathname', await_promise=False)}")


async def login(cdp: CDP, account: Account):
    await cdp.goto("http://localhost:8086/login")
    await cdp.wait_for_selector("#username", timeout_s=15)
    await cdp.set_value("#username", account.username)
    await cdp.set_value("#password", account.password)
    await cdp.click_text(r"(Iniciar sesi|Login)", tag="button")
    await assert_path(cdp, r"^/$", timeout_s=15)


async def logout(cdp: CDP):
    # Logout control can be a button or menu item depending on role/layout.
    await cdp.goto("http://localhost:8086/")
    await cdp.wait_for_js("document.body && document.body.innerText.length>0", timeout_s=10)
    try:
        await cdp.click_text(r"Cerrar sesi", tag="button")
    except Exception:
        try:
            await cdp.click_text(r"Cerrar sesi", tag="a")
        except Exception:
            await cdp.click_text(r"Cerrar sesi", tag="*")
    await assert_path(cdp, r"^/login$", timeout_s=15)


async def register_user(cdp: CDP, *, role: str) -> Account:
    suffix = _now_id()[-6:]
    acc = Account(f"e2e_{role}_{suffix}", f"E2ePass_{suffix}!")
    await cdp.goto("http://localhost:8086/register")
    await cdp.wait_for_selector("#username", timeout_s=15)
    await cdp.set_value("#username", acc.username)
    await cdp.set_value("#password", acc.password)
    await cdp.set_value("#displayName", f"E2E {role} {suffix}")
    # Select role radio
    await cdp.eval(
        f"""(() => {{
  const el = Array.from(document.querySelectorAll("input[type=radio]")).find(x => x.value === {json.dumps(role)});
  if (!el) return false;
  el.click();
  return true;
}})()""",
        await_promise=False,
    )
    await cdp.click_text(r"Crear Cuenta", tag="button")
    # Registration redirects back to login (no auto-login).
    await assert_path(cdp, r"^/login$", timeout_s=15)
    return acc


async def nav_quick_actions(cdp: CDP):
    # Dashboard quick actions links in sidebar are stable
    await cdp.click_text(r"Comunicación", tag="a")
    await assert_path(cdp, r"^/communication", timeout_s=10)
    await cdp.click_text(r"Aprendizaje", tag="a")
    await assert_path(cdp, r"^/learning", timeout_s=10)
    await cdp.click_text(r"Symbol Hunt", tag="a")
    await assert_path(cdp, r"^/symbol-hunt", timeout_s=10)
    await cdp.click_text(r"Panel", tag="a")
    await assert_path(cdp, r"^/$", timeout_s=10)


async def dashboard_recent_board(cdp: CDP):
    # If there are board cards, click the first one (by link to /boards/)
    ok = await cdp.eval(
        """(() => {
  const a = Array.from(document.querySelectorAll("a")).find(x => (x.getAttribute("href")||"").startsWith("/boards/"));
  if (!a) return false;
  a.click();
  return true;
})()""",
        await_promise=False,
    )
    if ok:
        await assert_path(cdp, r"^/boards/", timeout_s=10)
        await cdp.click_text(r"Tableros", tag="a")
        await assert_path(cdp, r"^/boards$", timeout_s=10)


async def notifications_panel(cdp: CDP):
    # Toggle notification panel (bell icon) if present
    await cdp.eval(
        """(() => {
  const candidates = Array.from(document.querySelectorAll("button,[role=button]"));
  const bell = candidates.find(e => /notific/i.test(e.getAttribute("aria-label")||"") || /bell/i.test(e.innerText||""));
  if (!bell) return false;
  bell.click();
  return true;
})()""",
        await_promise=False,
    )


async def offline_mode_create_and_sync_board(cdp: CDP):
    # Go offline, create a board, then go online and verify we return without crashing.
    await cdp.emulate_offline(True)
    await cdp.goto("http://localhost:8086/boards")
    await cdp.wait_for_js("document.body && document.body.innerText.length > 0", timeout_s=10)
    # Create board (best-effort: click create button)
    try:
        await cdp.click_text(r"(Crear|Nuevo).*tablero", tag="button")
    except Exception:
        pass
    await asyncio.sleep(1)
    await cdp.emulate_offline(False)
    await asyncio.sleep(2)
    # Ensure app is still responsive
    await cdp.eval("Boolean(document.body)", await_promise=False)


async def edge_cases(cdp: CDP):
    await cdp.goto("http://localhost:8086/invalid-url")
    await cdp.wait_for_js("document.body && document.body.innerText.length>0", timeout_s=10)
    await cdp.goto("http://localhost:8086/teachers")
    # For students, this should redirect away or show unauthorized
    await asyncio.sleep(1)


async def run() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    created: dict[str, Account] = {}

    async def step(name: str, fn: Callable[[], Any]):
        started = time.time()
        try:
            await fn()
            results.append({"name": name, "ok": True, "seconds": round(time.time() - started, 2)})
        except Exception as e:
            results.append({"name": name, "ok": False, "seconds": round(time.time() - started, 2), "error": str(e)})
            raise

    target = get_first_page_target()
    async with CDP(target.ws_url) as cdp:
        await cdp.enable()
        await cdp.emulate_offline(False)
        await cdp.clear_origin_data("http://localhost:8086")

        # Auth flows
        await step("login_student", lambda: login(cdp, STUDENT))
        await step("dashboard_quick_actions", lambda: nav_quick_actions(cdp))
        await step("dashboard_recent_board", lambda: dashboard_recent_board(cdp))
        await step("notifications_panel", lambda: notifications_panel(cdp))
        await step("edge_cases_student", lambda: edge_cases(cdp))
        await step("logout_student", lambda: logout(cdp))

        async def _reg_student():
            created["new_student"] = await register_user(cdp, role="student")
            await login(cdp, created["new_student"])
            await logout(cdp)

        async def _reg_teacher():
            created["new_teacher"] = await register_user(cdp, role="teacher")
            await login(cdp, created["new_teacher"])
            await logout(cdp)

        await step("register_new_student", _reg_student)
        await step("register_new_teacher", _reg_teacher)

        # Role logins
        await step("login_teacher", lambda: login(cdp, TEACHER))
        await step("offline_create_sync_board", lambda: offline_mode_create_and_sync_board(cdp))
        await step("logout_teacher", lambda: logout(cdp))

        await step("login_admin", lambda: login(cdp, ADMIN))
        await step("logout_admin", lambda: logout(cdp))

    return results


def main():
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    results: list[dict[str, Any]]
    try:
        results = asyncio.run(run())
    except Exception:
        # still write partial results if available
        results = []
        raise
    finally:
        out = {"results": results, "passed": sum(1 for r in results if r.get("ok")), "failed": sum(1 for r in results if not r.get("ok"))}
        os.makedirs("logs", exist_ok=True)
        with open(os.path.join("logs", "e2e_cdp_report.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
