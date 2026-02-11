import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import requests

sys.path.insert(0, os.path.dirname(__file__))
from cdp_harness import CDP, get_page_target  # noqa: E402


@dataclass(frozen=True)
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


BASE_URL = os.environ.get("AAC_BASE_URL", "http://localhost:8086").rstrip("/")
API_BASE = f"{BASE_URL}/api"


class StepFailed(Exception):
    pass


def _now_id() -> str:
    return str(int(time.time() * 1000))


def _api_token(acc: Account) -> str:
    r = requests.post(
        f"{API_BASE}/auth/token",
        data={"username": acc.username, "password": acc.password},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    return data["access_token"]


def _api_get(path: str, *, token: str, params: Optional[dict[str, Any]] = None) -> Any:
    r = requests.get(
        f"{API_BASE}{path}",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _api_post(
    path: str,
    *,
    token: str,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
) -> Any:
    r = requests.post(
        f"{API_BASE}{path}",
        params=params,
        json=json_body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _api_put(
    path: str,
    *,
    token: str,
    params: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
) -> Any:
    r = requests.put(
        f"{API_BASE}{path}",
        params=params,
        json=json_body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _api_delete(path: str, *, token: str) -> None:
    r = requests.delete(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()


async def ensure_ai_settings_configured() -> None:
    token = await asyncio.to_thread(_api_token, ADMIN)
    model = os.environ.get("AAC_TEST_OLLAMA_MODEL", "qwen:7b-q4_0")
    await asyncio.to_thread(
        _api_put,
        "/settings/ai",
        token=token,
        json_body={"provider": "ollama", "ollama_model": model},
    )
    await asyncio.to_thread(
        _api_put,
        "/settings/ai/fallback",
        token=token,
        json_body={"provider": "ollama", "ollama_model": model},
    )


def _ensure_dir_empty(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    for name in os.listdir(path):
        try:
            os.remove(os.path.join(path, name))
        except OSError:
            pass


async def assert_path(cdp: CDP, pattern: str, timeout_s: float = 15):
    regex = re.compile(pattern)
    start = time.time()
    while time.time() - start < timeout_s:
        path = await cdp.eval("location.pathname", await_promise=False)
        if isinstance(path, str) and regex.search(path):
            return
        await asyncio.sleep(0.2)
    raise StepFailed(
        f"Expected path /{pattern}/, got {await cdp.eval('location.pathname', await_promise=False)}"
    )


async def wait_text(cdp: CDP, needle_regex: str, timeout_s: float = 15):
    pat = re.compile(needle_regex, re.I)
    start = time.time()
    while time.time() - start < timeout_s:
        txt = await cdp.eval("document.body ? document.body.innerText : ''", await_promise=False)
        if isinstance(txt, str) and pat.search(txt):
            return
        await asyncio.sleep(0.2)
    raise StepFailed(f"Did not find text /{needle_regex}/ on page")


async def require_js(cdp: CDP, js_predicate: str, *, timeout_s: float = 15, error: str):
    ok = await cdp.wait_for_js(js_predicate, timeout_s=timeout_s)
    if not ok:
        raise StepFailed(error)


async def set_value_by_label(cdp: CDP, label_regex: str, value: str):
    pat = json.dumps(label_regex)
    val = json.dumps(value)
    ok = await cdp.eval(
        f"""(() => {{
  const r = new RegExp({pat}, "i");
  const labels = Array.from(document.querySelectorAll("label"));
  const label = labels.find(l => r.test((l.textContent||"").trim()));
  if (!label) return false;
  const container = label.parentElement;
  if (!container) return false;
  const input = container.querySelector("input,textarea,select");
  if (!input) return false;
  input.focus();
  if (input.tagName === "SELECT") {{
    input.value = {val};
    input.dispatchEvent(new Event("input", {{ bubbles: true }}));
    input.dispatchEvent(new Event("change", {{ bubbles: true }}));
    return true;
  }}
  const proto =
    input.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const desc = Object.getOwnPropertyDescriptor(proto, "value");
  if (desc && desc.set) desc.set.call(input, {val});
  else input.value = {val};
  input.dispatchEvent(new Event("input", {{ bubbles: true }}));
  input.dispatchEvent(new Event("change", {{ bubbles: true }}));
  return true;
}})()""",
        await_promise=False,
    )
    if not ok:
        raise StepFailed(f"Could not set field for label /{label_regex}/")


async def set_range_by_text(cdp: CDP, container_regex: str, value: str):
    pat = json.dumps(container_regex)
    val = json.dumps(value)
    ok = await cdp.eval(
        f"""(() => {{
  const r = new RegExp({pat}, "i");
  const textEls = Array.from(document.querySelectorAll("p,label,span"));
  const hit = textEls.find(el => r.test((el.textContent || "").trim()));
  if (!hit) return false;
  let container = hit;
  for (let i = 0; i < 8 && container; i++) {{
    const maybe = container.querySelector?.("input[type=range]");
    if (maybe) {{
      container = maybe;
      break;
    }}
    container = container.parentElement;
  }}
  const input = container && container.tagName === "INPUT" ? container : null;
  if (!input) return false;
  input.focus();
  const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  if (desc && desc.set) desc.set.call(input, {val});
  else input.value = {val};
  input.dispatchEvent(new Event("input", {{ bubbles: true }}));
  input.dispatchEvent(new Event("change", {{ bubbles: true }}));
  return true;
}})()""",
        await_promise=False,
    )
    if not ok:
        raise StepFailed(f"Could not set range for section /{container_regex}/")


async def clear_session(cdp: CDP):
    await cdp.clear_origin_data(BASE_URL)
    await cdp.emulate_offline(False)
    await cdp.eval("try{window.dispatchEvent(new Event('online'))}catch(e){}", await_promise=False)


async def login(cdp: CDP, account: Account):
    await cdp.goto(f"{BASE_URL}/login")
    await cdp.wait_for_selector("#username", timeout_s=20)
    await cdp.set_value("#username", account.username)
    await cdp.set_value("#password", account.password)
    await cdp.click_text(r"^(Login|Iniciar sesi)", tag="button")
    await assert_path(cdp, r"^/$", timeout_s=20)


async def logout(cdp: CDP):
    await cdp.goto(f"{BASE_URL}/")
    await cdp.wait_for_js("document.body && document.body.innerText.length>0", timeout_s=15)
    for regex, tag in [
        (r"Cerrar sesi", "button"),
        (r"Sign Out", "button"),
        (r"Logout", "button"),
        (r"Cerrar sesi", "a"),
        (r"Sign Out", "a"),
        (r"Logout", "a"),
        (r"Cerrar sesi", "*"),
        (r"Sign Out", "*"),
        (r"Logout", "*"),
    ]:
        try:
            await cdp.click_text(regex, tag=tag)
            break
        except Exception:
            continue
    await assert_path(cdp, r"^/login$", timeout_s=20)


async def ensure_student1_setup() -> dict[str, Any]:
    token = await asyncio.to_thread(_api_token, ADMIN)
    me = await asyncio.to_thread(_api_get, "/auth/me", token=token)
    admin_id = int(me["id"])

    users = await asyncio.to_thread(
        _api_get,
        "/auth/users",
        token=token,
        params={"limit": 2000, "user_type": "student"},
    )
    student = next((u for u in users if u.get("username") == STUDENT.username), None)
    if not student:
        raise StepFailed("student1 not found in /auth/users")
    student_id = int(student["id"])

    teachers = await asyncio.to_thread(
        _api_get,
        "/auth/users",
        token=token,
        params={"limit": 2000, "user_type": "teacher"},
    )
    teacher = next((u for u in teachers if u.get("username") == TEACHER.username), None)
    if not teacher:
        raise StepFailed("teacher1 not found in /auth/users")
    teacher_id = int(teacher["id"])

    # Ensure teacher1 can see/manage student1 in GUI flows.
    try:
        await asyncio.to_thread(
            _api_post,
            "/users/assign-student",
            token=token,
            json_body={"student_id": student_id, "teacher_id": teacher_id},
        )
    except Exception:
        # OK if already assigned or endpoint isn't critical for student flows.
        pass

    symbols = await asyncio.to_thread(_api_get, "/boards/symbols", token=token, params={"limit": 50})
    sym_ids = [int(s["id"]) for s in symbols if "id" in s]
    if len(sym_ids) < 3:
        raise StepFailed("Not enough symbols available to set up boards")

    playable_name = f"E2E Playable {_now_id()[-6:]}"
    locked_name = f"E2E Locked {_now_id()[-6:]}"

    playable_board = await asyncio.to_thread(
        _api_post,
        "/boards/",
        token=token,
        params={"user_id": admin_id},
        json_body={
            "name": playable_name,
            "description": "E2E playable board",
            "category": "general",
            "grid_rows": 2,
            "grid_cols": 2,
            "ai_enabled": False,
            "symbols": [],
        },
    )
    locked_board = await asyncio.to_thread(
        _api_post,
        "/boards/",
        token=token,
        params={"user_id": admin_id},
        json_body={
            "name": locked_name,
            "description": "E2E locked board",
            "category": "general",
            "grid_rows": 2,
            "grid_cols": 2,
            "ai_enabled": False,
            "symbols": [],
        },
    )

    playable_id = int(playable_board["id"])
    locked_id = int(locked_board["id"])

    await asyncio.to_thread(
        _api_post,
        f"/boards/{playable_id}/symbols",
        token=token,
        json_body={"symbol_id": sym_ids[0], "position_x": 0, "position_y": 0, "size": 1, "is_visible": True},
    )
    await asyncio.to_thread(
        _api_post,
        f"/boards/{playable_id}/symbols",
        token=token,
        json_body={"symbol_id": sym_ids[1], "position_x": 1, "position_y": 0, "size": 1, "is_visible": True},
    )

    await asyncio.to_thread(
        _api_post,
        f"/boards/{locked_id}/symbols",
        token=token,
        json_body={"symbol_id": sym_ids[2], "position_x": 0, "position_y": 0, "size": 1, "is_visible": True},
    )

    await asyncio.to_thread(_api_post, f"/boards/{playable_id}/assign", token=token, json_body={"student_id": student_id})
    await asyncio.to_thread(_api_post, f"/boards/{locked_id}/assign", token=token, json_body={"student_id": student_id})

    return {
        "student_id": student_id,
        "teacher_id": teacher_id,
        "playable": {"id": playable_id, "name": playable_name},
        "locked": {"id": locked_id, "name": locked_name},
    }


async def scenario_register_teacher_option_disabled(cdp: CDP):
    await clear_session(cdp)
    await cdp.goto(f"{BASE_URL}/register")
    await cdp.wait_for_selector("#username", timeout_s=15)
    radios = await cdp.eval("document.querySelectorAll('input[type=radio]').length", await_promise=False)
    if int(radios or 0) != 0:
        raise StepFailed("Teacher/student role selector radios are present; expected teacher self-registration disabled")

    body = await cdp.eval("document.body ? document.body.innerText : ''", await_promise=False)
    if not isinstance(body, str) or not re.search(r"Teacher accounts must be created|cuentas de profesor", body, re.I):
        raise StepFailed("Missing teacher registration note on Register page")


async def scenario_profile_and_change_password(cdp: CDP):
    await clear_session(cdp)
    suffix = _now_id()[-6:]
    acc = Account(f"e2e_profile_{suffix}", f"E2ePass_{suffix}!")
    new_display = f"E2E Profile {suffix}"
    new_email = f"e2e_{suffix}@example.com"

    await cdp.goto(f"{BASE_URL}/register")
    await cdp.wait_for_selector("#username", timeout_s=15)
    await cdp.set_value("#username", acc.username)
    await cdp.set_value("#password", acc.password)
    await cdp.set_value("#displayName", new_display)
    await cdp.click_text(r"(Create Account|Crear Cuenta)", tag="button")
    await assert_path(cdp, r"^/login$", timeout_s=20)

    await login(cdp, acc)

    await cdp.goto(f"{BASE_URL}/settings")
    await wait_text(cdp, r"Settings|Ajustes", timeout_s=20)

    await require_js(
        cdp,
        "Array.from(document.querySelectorAll('button')).some(b => /(Edit|Editar)/i.test((b.innerText||b.textContent||'').trim()))",
        timeout_s=20,
        error="Profile edit button did not appear in Settings",
    )
    await cdp.click_text(r"(Edit|Editar)", tag="button")
    await set_value_by_label(cdp, r"Display Name|Nombre para mostrar", f"{new_display} Updated")
    await set_value_by_label(cdp, r"Email|Correo", new_email)
    await cdp.click_text(r"^(Save|Guardar)$", tag="button")
    await wait_text(cdp, r"Profile updated successfully|Perfil actualizado|updated", timeout_s=20)

    await cdp.click_text(r"Change Password|Cambiar", tag="button")
    await require_js(
        cdp,
        "document.querySelectorAll('input[type=password]').length>=3",
        timeout_s=15,
        error="Change password modal did not show 3 password inputs",
    )
    new_pass = f"E2eNew_{suffix}!"
    await cdp.eval(
        f"""(() => {{
  const els = Array.from(document.querySelectorAll("input[type=password]"));
  if (els.length < 3) return false;
  const vals = [{json.dumps(acc.password)}, {json.dumps(new_pass)}, {json.dumps(new_pass)}];
  for (let i=0;i<3;i++) {{
    const el = els[i];
    el.focus();
    const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
    if (desc && desc.set) desc.set.call(el, vals[i]); else el.value = vals[i];
    el.dispatchEvent(new Event("input", {{ bubbles: true }}));
    el.dispatchEvent(new Event("change", {{ bubbles: true }}));
  }}
  return true;
 }})()""",
        await_promise=False,
    )
    await cdp.click_text(r"^(Save|Guardar)$", tag="button")
    await require_js(
        cdp,
        "document.querySelectorAll('input[type=password]').length===0",
        timeout_s=25,
        error="Change password modal did not close after saving",
    )

    await logout(cdp)
    await login(cdp, Account(acc.username, new_pass))
    await logout(cdp)


async def scenario_communication_features(cdp: CDP, board_setup: dict[str, Any]):
    await clear_session(cdp)
    await login(cdp, STUDENT)

    await cdp.goto(f"{BASE_URL}/communication")
    await wait_text(cdp, r"Select a board|Selecciona", timeout_s=20)

    has_disabled = await cdp.eval("document.querySelectorAll('button[disabled]').length > 0", await_promise=False)
    if not has_disabled:
        raise StepFailed("Expected at least one locked/disabled board in picker")

    playable_name = str((board_setup.get("playable") or {}).get("name") or "E2E Playable")
    await cdp.click_text(re.escape(playable_name), tag="button")
    await assert_path(cdp, r"^/communication", timeout_s=20)
    await require_js(
        cdp,
        "document.querySelectorAll('div.relative.shrink-0 > button').length > 0",
        timeout_s=25,
        error="Smartbar suggestions did not render for the selected board",
    )

    first_label = await cdp.eval(
        """(() => {
  const btn = document.querySelector('div.relative.shrink-0 > button span');
  return btn ? (btn.textContent||'').trim() : null;
})()""",
        await_promise=False,
    )
    if not first_label:
        raise StepFailed("Could not read first Smartbar suggestion label")
    await cdp.click("div.relative.shrink-0 > button")
    await asyncio.sleep(0.5)
    sentence_text = await cdp.eval(
        """(() => {
  const el = document.querySelector('.mt-1.px-1');
  return el ? (el.textContent||'') : '';
})()""",
        await_promise=False,
    )
    if not isinstance(sentence_text, str) or first_label not in sentence_text:
        raise StepFailed("Smartbar suggestion click did not add text to sentence strip preview")

    await cdp.click_text(r"^YES$|^S[IÍ]$", tag="span")
    await asyncio.sleep(0.25)
    await cdp.click_text(r"^(THANKS|GRACIAS)$", tag="span")
    await asyncio.sleep(0.25)
    await cdp.click_text(r"^(ALERT|ALERTA)$", tag="span")
    await asyncio.sleep(0.25)
    spoke = await cdp.eval("Boolean(window.speechSynthesis && window.speechSynthesis.speaking)", await_promise=False)
    if not spoke:
        exists = await cdp.eval("Boolean(window.speechSynthesis)", await_promise=False)
        if not exists:
            raise StepFailed("Speech synthesis unavailable; cannot validate quick response/attention")

    await cdp.click_text(r"^TYPE$|^ESCRIB", tag="span")
    await cdp.wait_for_js("Boolean(document.querySelector('textarea'))", timeout_s=10)
    await cdp.set_value("textarea", "hello from e2e")
    await cdp.click_text(r"^Speak$|^Hablar$|^Decir$", tag="button")

    await cdp.click_mouse("header button[title]")
    await cdp.wait_for_js("Boolean(document.fullscreenElement)", timeout_s=10)
    await cdp.click_mouse("header button[title]")
    await cdp.wait_for_js("!document.fullscreenElement", timeout_s=10)

    await logout(cdp)


async def scenario_settings_ignore_repeats(cdp: CDP, board_setup: dict[str, Any]):
    await clear_session(cdp)
    await login(cdp, STUDENT)

    await cdp.goto(f"{BASE_URL}/settings")
    await wait_text(cdp, r"Settings|Ajustes", timeout_s=20)
    await require_js(
        cdp,
        "document.querySelectorAll('input[type=range]').length >= 2",
        timeout_s=25,
        error="Settings preferences sliders did not load",
    )
    await set_range_by_text(cdp, r"Ignore Repeat Clicks|Ignorar", "2000")
    await cdp.click_text(r"Save Preferences|Guardar Preferencias", tag="button")
    await asyncio.sleep(1)

    await cdp.goto(f"{BASE_URL}/communication")
    await wait_text(cdp, r"Select a board|Selecciona", timeout_s=20)
    playable_name = str((board_setup.get("playable") or {}).get("name") or "E2E Playable")
    await cdp.click_text(re.escape(playable_name), tag="button")
    await require_js(
        cdp,
        "document.querySelectorAll('button[aria-label^=\"Add \"]').length>0",
        timeout_s=25,
        error="Could not locate any symbol cards in Communication board view",
    )

    label = await cdp.eval(
        """(() => {
  const btn = document.querySelector('button[aria-label^="Add "] span');
  return btn ? (btn.textContent||'').trim() : null;
})()""",
        await_promise=False,
    )
    if not label:
        raise StepFailed("Could not locate a symbol card label")
    await cdp.click("button[aria-label^=\"Add \"]")
    await asyncio.sleep(0.1)
    await cdp.click("button[aria-label^=\"Add \"]")
    await asyncio.sleep(0.3)
    sentence_text = await cdp.eval(
        """(() => {
  const el = document.querySelector('.mt-1.px-1');
  return el ? (el.textContent||'') : '';
})()""",
        await_promise=False,
    )
    if isinstance(sentence_text, str) and sentence_text.count(label) > 1:
        raise StepFailed("Ignore repeats did not debounce repeated clicks")

    await logout(cdp)


async def scenario_board_editor_features(cdp: CDP):
    await clear_session(cdp)
    await login(cdp, ADMIN)

    token = await asyncio.to_thread(_api_token, ADMIN)
    me = await asyncio.to_thread(_api_get, "/auth/me", token=token)
    admin_id = int(me["id"])
    symbols = await asyncio.to_thread(_api_get, "/boards/symbols", token=token, params={"limit": 30})
    sym_ids = [int(s["id"]) for s in symbols if "id" in s]
    if len(sym_ids) < 5:
        raise StepFailed("Not enough symbols to set up board editor test board")

    board_name = f"E2E Editor {_now_id()[-6:]}"
    board = await asyncio.to_thread(
        _api_post,
        "/boards/",
        token=token,
        params={"user_id": admin_id},
        json_body={
            "name": board_name,
            "description": "E2E editor board",
            "category": "general",
            "grid_rows": 4,
            "grid_cols": 4,
            "ai_enabled": False,
            "symbols": [],
        },
    )
    board_id = int(board["id"])
    for i in range(4):
        await asyncio.to_thread(
            _api_post,
            f"/boards/{board_id}/symbols",
            token=token,
            json_body={"symbol_id": sym_ids[i], "position_x": i % 4, "position_y": i // 4, "size": 1, "is_visible": True},
        )

    # Enable AI for this board without invoking AI generation during creation
    await asyncio.to_thread(
        _api_put,
        f"/boards/{board_id}",
        token=token,
        json_body={"ai_enabled": True, "ai_provider": "ollama", "ai_model": "@primary"},
    )

    await cdp.goto(f"{BASE_URL}/boards/{board_id}")
    await wait_text(cdp, r"Edit Board|Editar Tablero", timeout_s=25)

    await cdp.set_select_value("#board-layout", "2x2")
    await cdp.wait_for_js("document.querySelectorAll('[role=gridcell]').length===4", timeout_s=20)
    await cdp.set_select_value("#board-layout", "4x4")
    await cdp.wait_for_js("document.querySelectorAll('[role=gridcell]').length===16", timeout_s=20)

    await cdp.click_text(r"Clear Board|Limpiar Tablero", tag="button")
    await cdp.wait_for_js("document.querySelectorAll('button[aria-label=\"Add symbol\"]').length===16", timeout_s=30)

    await cdp.click_text(r"Get.*suggestions|Obtener.*sugerencias", tag="button")
    await cdp.wait_for_js("document.body && /AI Suggestions|Sugerencias/.test(document.body.innerText)", timeout_s=25)
    await require_js(
        cdp,
        "Array.from(document.querySelectorAll('button')).some(b => /(Add to board|Añadir al tablero)/i.test((b.innerText||b.textContent||'').trim()))",
        timeout_s=35,
        error="AI suggestions panel opened but produced no items",
    )

    await cdp.set_value("input[type=text][placeholder]", "daily routines")
    await cdp.click_text(r"Send refine|Enviar", tag="button")
    await asyncio.sleep(1)

    await cdp.click_text(r"Add to board|A.*adir al tablero|Añadir al tablero", tag="button")
    await asyncio.sleep(1)
    await cdp.click_text(r"Add all|A.*adir todo|Añadir todo", tag="button")
    await asyncio.sleep(2)

    await cdp.eval(
        """(() => {
  const btn = Array.from(document.querySelectorAll('button[aria-label]')).find(b => /board.*settings|configuraci/i.test(b.getAttribute('aria-label')||''));
  if (!btn) return false;
  btn.click();
  return true;
})()""",
        await_promise=False,
    )
    await cdp.wait_for_js("Boolean(document.querySelector('#aiEnabledEdit'))", timeout_s=10)
    await cdp.eval("document.querySelector('#aiEnabledEdit')?.checked || document.querySelector('#aiEnabledEdit')?.click()", await_promise=False)
    await cdp.eval(
        """(() => {
  const labels = Array.from(document.querySelectorAll('label')).filter(l => /(fallback|respaldo)/i.test(l.innerText||''));
  if (labels.length === 0) return false;
  const input = labels[0].querySelector('input[type=radio]');
  if (input && !input.disabled) { input.click(); return true; }
  return false;
})()""",
        await_promise=False,
    )
    await cdp.click_text(r"Save Settings|Guardar Ajustes", tag="button")
    await asyncio.sleep(1)

    await logout(cdp)


async def scenario_learning_load_session(cdp: CDP):
    await clear_session(cdp)
    await login(cdp, STUDENT)
    await cdp.goto(f"{BASE_URL}/learning")
    await assert_path(cdp, r"^/learning", timeout_s=20)
    await cdp.wait_for_selector("#learning-mode", timeout_s=25)
    await cdp.click_text(r"Show History|Mostrar historial|History", tag="button")
    await cdp.wait_for_js("Boolean(document.querySelector('.w-80'))", timeout_s=15)
    await cdp.eval(
        """(() => {
  const panel = document.querySelector('.w-80');
  if (!panel) return false;
  const buttons = Array.from(panel.querySelectorAll('button'));
  const candidates = buttons.filter(b => !/new conversation/i.test(b.innerText||''));
  if (candidates.length === 0) return false;
  candidates[0].click();
  return true;
})()""",
        await_promise=False,
    )
    await cdp.wait_for_request("/api/learning/", timeout_s=25)
    await cdp.wait_for_js("!document.querySelector('.w-80')", timeout_s=20)
    await logout(cdp)


async def scenario_students_voice_toggle(cdp: CDP):
    await clear_session(cdp)
    await login(cdp, TEACHER)
    await cdp.goto(f"{BASE_URL}/students")
    await wait_text(cdp, r"Students|Estudiantes", timeout_s=25)
    await require_js(
        cdp,
        f"Array.from(document.querySelectorAll('tbody tr')).some(tr => (tr.innerText||'').includes({json.dumps(STUDENT.username)}))",
        timeout_s=30,
        error="Students table did not load assigned students",
    )

    ok = await cdp.eval(
        f"""(() => {{
  const row = Array.from(document.querySelectorAll("tr")).find(tr => (tr.innerText||"").includes({json.dumps(STUDENT.username)}));
  if (!row) return false;
  const buttons = Array.from(row.querySelectorAll("button"));
  const btn =
    buttons.find(b => /(pref|prefer)/i.test((b.getAttribute("title")||"") + " " + (b.getAttribute("aria-label")||""))) ||
    buttons.find(b => (b.getAttribute("title")||"").length > 0);
  if (!btn) return false;
  btn.click();
  return true;
}})()""",
        await_promise=False,
    )
    if not ok:
        raise StepFailed("Could not open student preferences modal (is student assigned to teacher?)")
    await require_js(
        cdp,
        "Boolean(document.querySelector('input[type=checkbox].sr-only'))",
        timeout_s=20,
        error="Student preferences modal did not load voice mode toggle",
    )
    await cdp.eval(
        """(() => {
  const cb = document.querySelector('input[type=checkbox].sr-only');
  if (!cb) return false;
  cb.click();
  return true;
})()""",
        await_promise=False,
    )
    await cdp.click_text(r"(Save|Guardar|save)", tag="button")
    await asyncio.sleep(1)
    await logout(cdp)


async def scenario_admins_management(cdp: CDP):
    await clear_session(cdp)
    await login(cdp, ADMIN)
    await cdp.goto(f"{BASE_URL}/admins")
    await wait_text(cdp, r"Manage admin accounts|Admins", timeout_s=25)

    await cdp.wait_for_js("document.querySelectorAll('tbody tr').length >= 1 || /No admins found/i.test(document.body.innerText||'')", timeout_s=25)
    rows = await cdp.eval("document.querySelectorAll('tbody tr').length", await_promise=False)
    if int(rows or 0) < 1:
        raise StepFailed("Admins list is empty")

    suffix = _now_id()[-6:]
    new_admin = Account(f"e2e_admin_{suffix}", f"AdminX_{suffix}9")
    await cdp.click_text(r"\+\s*(Create|Crear)", tag="button")
    await require_js(
        cdp,
        "Boolean(document.querySelector('input#username'))",
        timeout_s=15,
        error="Create Admin modal did not open",
    )
    await cdp.set_value("input#username", new_admin.username)
    await cdp.set_value("input#displayName", f"E2E Admin {suffix}")
    await cdp.set_value("input#email", f"e2e_admin_{suffix}@example.com")
    await cdp.set_value("input#password", new_admin.password)
    await cdp.set_value("input#confirmPassword", new_admin.password)
    # Avoid ambiguity with the "+ Create Admin" page button by submitting the modal form directly.
    await cdp.click("div.fixed.inset-0 form button[type=submit]")
    await require_js(
        cdp,
        "Boolean(document.querySelectorAll('input#username').length===0)",
        timeout_s=25,
        error="Create Admin modal did not close after submit",
    )
    await wait_text(cdp, new_admin.username, timeout_s=20)

    reset_pass = f"AdminY_{suffix}8"
    await cdp.eval(
        f"""(() => {{
  const row = Array.from(document.querySelectorAll("tbody tr")).find(tr => (tr.innerText||"").includes({json.dumps(new_admin.username)}));
  if (!row) return false;
  const btn = Array.from(row.querySelectorAll("button")).find(b => /reset/i.test(b.innerText||""));
  if (!btn) return false;
  btn.click();
  return true;
}})()""",
        await_promise=False,
    )
    await require_js(
        cdp,
        "Boolean(document.querySelector('input[type=password]'))",
        timeout_s=10,
        error="Reset password modal did not open",
    )
    await cdp.set_value("input[type=password]", reset_pass)
    # Avoid ambiguity with the per-row "Reset" button by submitting the modal form directly.
    await cdp.click("div.fixed.inset-0 form button[type=submit]")
    await require_js(
        cdp,
        "Boolean(!document.querySelector('div.fixed.inset-0 input[type=password]'))",
        timeout_s=15,
        error="Reset password modal did not close after submit",
    )

    # Verify new password works
    await asyncio.to_thread(_api_token, Account(new_admin.username, reset_pass))

    await cdp.eval(
        f"""(() => {{
  const row = Array.from(document.querySelectorAll("tbody tr")).find(tr => (tr.innerText||"").includes({json.dumps(new_admin.username)}));
  if (!row) return false;
  const btn = Array.from(row.querySelectorAll("button")).find(b => /(delete|eliminar)/i.test(b.innerText||""));
  if (!btn) return false;
  btn.click();
  return true;
}})()""",
        await_promise=False,
    )
    await asyncio.sleep(0.5)
    try:
        await cdp.click_text(r"Confirm|Delete|Eliminar|Confirmar", tag="button")
    except Exception:
        pass
    await asyncio.sleep(1)

    await logout(cdp)


async def scenario_settings_export_import_and_modes(cdp: CDP):
    await clear_session(cdp)
    await login(cdp, ADMIN)

    download_dir = os.path.join("logs", "downloads_0612")
    _ensure_dir_empty(download_dir)
    await cdp.set_download_dir(os.path.abspath(download_dir))

    await cdp.goto(f"{BASE_URL}/settings")
    await wait_text(cdp, r"Data Management|Export", timeout_s=25)
    await cdp.click_text(r"Export My Data|Exportar", tag="button")

    start = time.time()
    exported_file: Optional[str] = None
    while time.time() - start < 20:
        files = [f for f in os.listdir(download_dir) if f.endswith(".json") and "aac-data" in f]
        if files:
            exported_file = os.path.join(download_dir, files[0])
            break
        await asyncio.sleep(0.25)
    if not exported_file:
        raise StepFailed("Export did not produce a downloaded JSON file")

    await cdp.set_input_files("input[type=file][accept='application/json']", [os.path.abspath(exported_file)])
    await wait_text(cdp, r"Import completed successfully", timeout_s=45)

    await cdp.click_text(r"Add New Learning Mode", tag="button")
    await wait_text(cdp, r"Create New Mode", timeout_s=10)
    suffix = _now_id()[-6:]
    await set_value_by_label(cdp, r"^Name$", f"E2E Mode {suffix}")
    await cdp.set_value("input[placeholder*='daily_conversation']", f"e2e_mode_{suffix}")
    await set_value_by_label(cdp, r"^Description$", "E2E mode description")
    await cdp.eval(
        """(() => {
  const ta = Array.from(document.querySelectorAll('textarea')).find(t => /System Prompt Instruction/i.test(t.previousElementSibling?.textContent||''));
  if (!ta) return false;
  ta.focus();
  ta.value = 'E2E prompt instruction';
  ta.dispatchEvent(new Event('input', {bubbles:true}));
  ta.dispatchEvent(new Event('change', {bubbles:true}));
  return true;
})()""",
        await_promise=False,
    )
    await cdp.click_text(r"Save Mode", tag="button")
    await asyncio.sleep(1)
    await wait_text(cdp, f"E2E Mode {suffix}", timeout_s=20)

    await logout(cdp)


async def scenario_offline_conflicts(cdp: CDP):
    token = await asyncio.to_thread(_api_token, ADMIN)
    me = await asyncio.to_thread(_api_get, "/auth/me", token=token)
    admin_id = int(me["id"])
    board_name = f"E2E Conflict {_now_id()[-6:]}"
    board = await asyncio.to_thread(
        _api_post,
        "/boards/",
        token=token,
        params={"user_id": admin_id},
        json_body={
            "name": board_name,
            "description": "offline conflict board",
            "category": "general",
            "grid_rows": 2,
            "grid_cols": 2,
            "ai_enabled": False,
            "symbols": [],
        },
    )
    board_id = int(board["id"])

    await clear_session(cdp)
    await login(cdp, ADMIN)
    await cdp.goto(f"{BASE_URL}/boards")
    await wait_text(cdp, r"Boards|Tableros", timeout_s=25)
    await require_js(
        cdp,
        "Boolean(document.querySelector('#boards-search'))",
        timeout_s=25,
        error="Boards page did not render search input",
    )
    await cdp.set_value("#boards-search", board_name)
    await require_js(
        cdp,
        f"Boolean(document.querySelector('a[href=\"/boards/{board_id}\"]'))",
        timeout_s=25,
        error="Newly created board did not appear in Boards list",
    )

    await cdp.emulate_offline(True)
    await cdp.eval("try{window.dispatchEvent(new Event('offline'))}catch(e){}", await_promise=False)
    await asyncio.sleep(0.5)

    ok = await cdp.eval(
        f"""(() => {{
  const link = document.querySelector('a[href=\"/boards/{board_id}\"]') || document.querySelector('a[href=\"/play/{board_id}\"]');
  const card = link ? link.closest('div.relative') : null;
  if (!card) return false;
  const btn = card.querySelector('button[aria-label=\"Delete board\"]');
  if (!btn) return false;
  btn.click();
  return true;
}})()""",
        await_promise=False,
    )
    if not ok:
        raise StepFailed("Could not click delete on the target board card while offline")
    await asyncio.sleep(0.5)
    try:
        await cdp.click_text(r"Delete|Eliminar", tag="button")
    except Exception:
        pass

    await asyncio.to_thread(_api_delete, f"/boards/{board_id}", token=token)

    await cdp.emulate_offline(False)
    await cdp.eval("try{window.dispatchEvent(new Event('online'))}catch(e){}", await_promise=False)
    await wait_text(cdp, r"Offline Conflicts", timeout_s=25)
    await logout(cdp)


async def run() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    async def step(name: str, fn: Callable[[], Any]):
        started = time.time()
        try:
            await fn()
            results.append({"name": name, "ok": True, "seconds": round(time.time() - started, 2)})
        except Exception as e:
            results.append({"name": name, "ok": False, "seconds": round(time.time() - started, 2), "error": str(e)})

    board_setup = await ensure_student1_setup()
    await ensure_ai_settings_configured()

    target = get_page_target(url_regex=r"^https?://(localhost|127\\.0\\.0\\.1):8086")
    async with CDP(target.ws_url) as cdp:
        await cdp.enable()
        await cdp.emulate_offline(False)
        await cdp.clear_origin_data(BASE_URL)

        await step("register_teacher_disabled", lambda: scenario_register_teacher_option_disabled(cdp))
        await step("profile_edit_and_change_password", lambda: scenario_profile_and_change_password(cdp))
        await step("communication_features", lambda: scenario_communication_features(cdp, board_setup))
        await step("settings_ignore_repeats", lambda: scenario_settings_ignore_repeats(cdp, board_setup))
        await step("board_editor_features", lambda: scenario_board_editor_features(cdp))
        await step("learning_load_session", lambda: scenario_learning_load_session(cdp))
        await step("students_voice_toggle", lambda: scenario_students_voice_toggle(cdp))
        await step("admins_management", lambda: scenario_admins_management(cdp))
        await step("settings_export_import_modes", lambda: scenario_settings_export_import_and_modes(cdp))
        await step("offline_conflicts_panel", lambda: scenario_offline_conflicts(cdp))

    return results


def main():
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    results = asyncio.run(run())
    out = {
        "results": results,
        "passed": sum(1 for r in results if r.get("ok")),
        "failed": sum(1 for r in results if not r.get("ok")),
        "base_url": BASE_URL,
        "api_base": API_BASE,
    }
    os.makedirs("logs", exist_ok=True)
    with open(os.path.join("logs", "e2e_cdp_report_0612.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    if out["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
