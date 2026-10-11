"""Seed only public examples into the user's writable directory."""
import json
import secrets
from . import paths


def initialize() -> None:
    bot = paths.bot_dir()
    bridge = paths.interlude_dir()
    for folder in (bot / "config", bot / "state", bot / "logs", bridge / "data"):
        folder.mkdir(parents=True, exist_ok=True)
    config = bot / "config/config.json"
    if not config.exists():
        data = json.loads((paths.bot_source_dir() / "config/config.example.json").read_text(encoding="utf-8"))
        data["account"].update(engine="edge", profile_dir="state/browser_profile_edge")
        # Startup alone must never send a message or call a model.
        data["whitelist"]["friends"] = []
        config.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    persona = bot / "config/persona.md"
    if not persona.exists():
        persona.write_text((paths.bot_source_dir() / "config/persona.example.md").read_text(encoding="utf-8"), encoding="utf-8")
    target = bridge / "bridge-config.json"
    if not target.exists():
        data = json.loads((paths.interlude_source_dir() / "bridge-config.example.json").read_text(encoding="utf-8"))
        data.update(token=secrets.token_urlsafe(32), autoAdvanceEnabled=False, allowProactiveMessages=False)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bot_setup_errors() -> list[str]:
    data = json.loads((paths.bot_dir() / "config/config.json").read_text(encoding="utf-8"))
    ai = data.get("ai", {})
    errors = []
    if not ai.get("api_key") or ai.get("model") in (None, "", "YOUR_MODEL") or "example.com" in ai.get("base_url", ""):
        errors.append("请在设置中填写模型地址、API Key 和模型名称")
    if not data.get("owner", {}).get("douyin_id"):
        errors.append("请在设置中填写自己的抖音号")
    if not any(f.get("enabled", True) for f in data.get("whitelist", {}).get("friends", [])):
        errors.append("请在好友白名单中添加至少一位好友")
    account = data.get("account", {})
    if not any((paths.bot_dir() / account.get(key, default)).is_file() for key, default in
               (("cookies_file", "state/cookies.json"), ("storage_state", "state/douyin_storage.json"))):
        errors.append("请先导入抖音 Cookies")
    return errors
