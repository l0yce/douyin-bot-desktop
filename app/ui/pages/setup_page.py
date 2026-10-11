"""Edit local model, account and persona without asking beginners to edit JSON."""
import json
from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit,
                              QLabel, QPushButton, QMessageBox, QComboBox, QScrollArea, QHBoxLayout)
from ...core import paths
from ...core.configuration import config_lock, commit_files, revision


class SetupPage(QWidget):
    def __init__(self, process_mgr, parent=None):
        super().__init__(parent)
        self.manager = process_mgr
        self.config = paths.bot_dir() / "config/config.json"
        with config_lock(self.config):
            raw = self.config.read_bytes()
        self._revision = revision(raw)
        data = json.loads(raw)
        layout = QVBoxLayout(self)
        intro = QLabel("先填写模型和自己的抖音号，再导入 Cookies、添加白名单，最后启动机器人。\n"
                       "支持 OpenAI 兼容接口；模型名称需与服务商提供的一致。视觉模型可留空。")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        self.fields = {}
        for section, key, title, hint in [
            ("ai", "base_url", "模型接口地址", "https://你的服务地址/v1"),
            ("ai", "api_key", "API Key", "服务商提供的密钥，仅保存到本机"),
            ("ai", "model", "聊天模型", "服务商提供的模型名称"),
            ("ai", "vision_model", "视觉模型（可选）", "留空时按项目降级策略处理图片"),
            ("ai", "max_tokens", "最大输出 Token（可选）", "留空使用服务商默认值"),
            ("owner", "douyin_id", "自己的抖音号", "个人主页显示的抖音号"),
            ("owner", "nickname", "自己的昵称", "显示名称"),
            ("account", "proxy_server", "浏览器代理（可选）", "家庭网络通常留空，例如 http://127.0.0.1:8792"),
        ]:
            value = data.get(section, {}).get(key, "")
            if key == "proxy_server" and not value:
                value = data.get("account", {}).get("proxy", "")
            edit = QLineEdit(str(value))
            edit.setPlaceholderText(hint)
            if key == "api_key":
                edit.setEchoMode(QLineEdit.Password)
            form.addRow(title, edit)
            self.fields[section, key] = edit
        self.engine = QComboBox()
        self.engine.addItems(["edge", "chrome"])
        self.engine.setCurrentText(data.get("account", {}).get("engine", "edge"))
        form.addRow("系统浏览器", self.engine)
        self.persona = QTextEdit()
        self.persona.setAcceptRichText(False)
        self.persona.setMinimumHeight(180)
        self.persona_path = paths.bot_dir() / data.get("prompts", {}).get("system_prompt_file", "config/persona.md")
        persona_raw = self.persona_path.read_bytes()
        self.persona.setPlainText(persona_raw.decode("utf-8"))
        self.bridge_path = paths.interlude_dir() / "bridge-config.json"
        self._persona_revision = revision(persona_raw)
        self._bridge_revision = revision(self.bridge_path.read_bytes())
        form.addRow("角色人设", self.persona)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        save = QPushButton("保存设置")
        save.clicked.connect(self.save)
        reload_button = QPushButton("重新读取设置")
        reload_button.clicked.connect(self.reload)
        buttons = QHBoxLayout()
        buttons.addWidget(reload_button)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        note = QLabel(f"本机数据目录：{paths.data_dir()}")
        note.setWordWrap(True)
        note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(note)

    def reload(self):
        if QMessageBox.question(self, "重新读取设置", "重新读取会放弃此页未保存的输入，继续吗？",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            with config_lock(self.config):
                raw = self.config.read_bytes()
                data = json.loads(raw)
                persona_path = paths.bot_dir() / data.get("prompts", {}).get("system_prompt_file", "config/persona.md")
                persona = persona_path.read_bytes()
                bridge = self.bridge_path.read_bytes()
            for (section, key), edit in self.fields.items():
                value = data.get(section, {}).get(key, "")
                if key == "proxy_server" and not value:
                    value = data.get("account", {}).get("proxy", "")
                edit.setText(str(value))
            self.engine.setCurrentText(data.get("account", {}).get("engine", "edge"))
            self.persona_path = persona_path
            self.persona.setPlainText(persona.decode("utf-8"))
            self._revision, self._persona_revision, self._bridge_revision = map(revision, (raw, persona, bridge))
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "读取失败", str(exc))

    def save(self):
        if any(s.desired or (s.proc and s.proc.state() != QProcess.NotRunning) for k, s in self.manager.services.items() if k != "panel"):
            QMessageBox.warning(self, "请先停止服务", "请先停止机器人和幕间引擎，再修改设置。控制面板可以继续运行。")
            return
        try:
            # Read fresh config so whitelist and panel changes are preserved.
            data = json.loads(self.config.read_text(encoding="utf-8"))
            for (section, key), edit in self.fields.items():
                value = edit.text().strip()
                if key == "max_tokens" and value:
                    value = int(value)
                    if value < 1:
                        raise ValueError("最大输出 Token 必须是正整数，或留空")
                data.setdefault(section, {})[key] = value
            data["account"]["engine"] = self.engine.currentText()
            if data["account"]["engine"] != "edge":
                data["account"]["profile_dir"] = "state/browser_profile_chrome"
            else:
                data["account"]["profile_dir"] = "state/browser_profile_edge"
            bridge_path = self.bridge_path
            bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
            bridge.setdefault("story", {})["characterProfile"] = self.persona.toPlainText()
            if data["owner"].get("nickname"):
                bridge["story"]["characterName"] = data["owner"]["nickname"]
            model = bridge.setdefault("hdsiOverrides", {}).setdefault("model", {})
            if data["ai"].get("max_tokens"):
                model["mainMaxTokens"] = data["ai"]["max_tokens"]
            else:
                model.pop("mainMaxTokens", None)
            data["account"].pop("proxy", None)
            payloads = {
                self.config: (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
                self.persona_path: self.persona.toPlainText().encode("utf-8"),
                bridge_path: (json.dumps(bridge, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            }
            expected = (self._revision, self._persona_revision, self._bridge_revision)
            with config_lock(self.config):
                if tuple(revision(path.read_bytes()) for path in payloads) != expected:
                    raise ValueError("配置已被其他操作修改。当前输入已保留，请点击“重新读取设置”后再保存。")
                commit_files(self.config, payloads)
            self._revision, self._persona_revision, self._bridge_revision = map(revision, payloads.values())
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        QMessageBox.information(self, "已保存", "模型、账号和人设已保存到本机。现在可以导入 Cookies 和配置好友。")
