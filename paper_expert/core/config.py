"""Configuration management for Paper Expert.

Loads/saves TOML config from ~/.config/paper_expert/config.toml (or platform-appropriate path).
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paper_expert.core.domain import DomainConfig

if __import__("sys").version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]


def _default_config_dir() -> Path:
    """Return platform-appropriate config directory."""
    system = platform.system()
    if system == "Windows":
        base = Path.home() / "AppData" / "Roaming"
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg = Path.home() / ".config"
        base = Path(xdg)
    return base / "paper_expert"


def _default_library_path() -> Path:
    return Path.home() / "paper_expert-library"


@dataclass
class LLMConfig:
    """LLM model configuration."""

    local_model: str = "ollama/qwen2.5"
    cloud_model: str = "openai/gpt-4o"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    api_base: str = ""  # Proxy base URL, e.g. "https://api.example.com/v1"


@dataclass
class APIKeysConfig:
    """API keys for external services."""

    semantic_scholar: str = ""
    openai: str = ""
    anthropic: str = ""
    ieee_xplore: str = ""
    unpaywall_email: str = ""


@dataclass
class SearchConfig:
    """Search behavior configuration."""

    default_sources: list[str] = field(
        default_factory=lambda: ["semantic_scholar", "openalex"]
    )
    default_limit: int = 20


@dataclass
class ParserConfig:
    """PDF parser configuration."""

    preferred: str = "marker"  # "marker" or "grobid"
    grobid_url: str = "http://localhost:8070"
    chunk_size: int = 3000
    chunk_overlap: int = 100


@dataclass
class NotifyConfig:
    """Notification webhook configuration for paper monitoring."""

    wechat_webhook: str = ""
    feishu_webhook: str = ""
    dingtalk_webhook: str = ""
    # SMTP email notification
    smtp_host: str = ""       # e.g. "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_recipient: str = ""  # e.g. "user@example.com"


@dataclass
class CampusConfig:
    """Campus network proxy for downloading paywalled papers."""

    enabled: bool = False
    http_proxy: str = ""  # e.g. "http://proxy.campus.edu:8080"
    https_proxy: str = ""  # e.g. "http://proxy.campus.edu:8080"
    ieee_inst_url: str = ""  # e.g. "https://ieeexplore.ieee.org" (with institution SSO)
    acm_inst_url: str = ""


@dataclass
class PaperExpertConfig:
    """Top-level configuration for Paper Expert."""

    library_path: Path = field(default_factory=_default_library_path)
    llm: LLMConfig = field(default_factory=LLMConfig)
    api_keys: APIKeysConfig = field(default_factory=APIKeysConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    domain: DomainConfig = field(default_factory=DomainConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    campus: CampusConfig = field(default_factory=CampusConfig)

    @classmethod
    def load(cls, config_path: Path | None = None) -> PaperExpertConfig:
        """Load configuration from TOML file, falling back to defaults."""
        if config_path is None:
            config_path = _default_config_dir() / "config.toml"

        config = cls()
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            config._apply_dict(data)
        return config

    def save(self, config_path: Path | None = None) -> None:
        """Save current configuration to TOML file."""
        if config_path is None:
            config_path = _default_config_dir() / "config.toml"

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(self._to_toml())

    def get_nested(self, dotted_key: str) -> Any:
        """Get a config value by dotted key like 'llm.local_model'."""
        parts = dotted_key.split(".")
        obj: Any = self
        for part in parts:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                raise KeyError(f"Unknown config key: {dotted_key}")
        return obj

    def set_nested(self, dotted_key: str, value: str) -> None:
        """Set a config value by dotted key like 'llm.local_model'."""
        parts = dotted_key.split(".")
        obj: Any = self
        for part in parts[:-1]:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                raise KeyError(f"Unknown config key: {dotted_key}")

        final_key = parts[-1]
        if not hasattr(obj, final_key):
            raise KeyError(f"Unknown config key: {dotted_key}")

        current = getattr(obj, final_key)
        if isinstance(current, Path):
            setattr(obj, final_key, Path(value))
        elif isinstance(current, int):
            setattr(obj, final_key, int(value))
        elif isinstance(current, list):
            setattr(obj, final_key, [v.strip() for v in value.split(",")])
        else:
            setattr(obj, final_key, value)

    def _apply_dict(self, data: dict[str, Any]) -> None:
        """Apply a nested dict to the config, overriding defaults."""
        if "library_path" in data:
            self.library_path = Path(data["library_path"])

        if "llm" in data:
            llm = data["llm"]
            if "local_model" in llm:
                self.llm.local_model = llm["local_model"]
            if "cloud_model" in llm:
                self.llm.cloud_model = llm["cloud_model"]
            if "embedding_model" in llm:
                self.llm.embedding_model = llm["embedding_model"]
            if "api_base" in llm:
                self.llm.api_base = llm["api_base"]

        if "api_keys" in data:
            keys = data["api_keys"]
            for attr in ("semantic_scholar", "openai", "anthropic", "ieee_xplore", "unpaywall_email"):
                if attr in keys:
                    setattr(self.api_keys, attr, keys[attr])

        if "search" in data:
            s = data["search"]
            if "default_sources" in s:
                self.search.default_sources = s["default_sources"]
            if "default_limit" in s:
                self.search.default_limit = s["default_limit"]

        if "parser" in data:
            p = data["parser"]
            for attr in ("preferred", "grobid_url", "chunk_size", "chunk_overlap"):
                if attr in p:
                    setattr(self.parser, attr, p[attr])

        if "domain" in data:
            from paper_expert.core.domain import load_domain_from_toml
            self.domain = load_domain_from_toml(data)

        if "notify" in data:
            n = data["notify"]
            for attr in ("wechat_webhook", "feishu_webhook", "dingtalk_webhook",
                         "smtp_host", "smtp_port", "smtp_username",
                         "smtp_password", "email_recipient"):
                if attr in n:
                    setattr(self.notify, attr, n[attr])

        if "campus" in data:
            c = data["campus"]
            for attr in ("enabled", "http_proxy", "https_proxy", "ieee_inst_url", "acm_inst_url"):
                if attr in c:
                    setattr(self.campus, attr, c[attr])

    def _to_toml(self) -> str:
        """Serialize config to TOML string."""

        def _val(v: str) -> str:
            """Escape a string value for TOML (use single quotes to avoid backslash issues)."""
            # TOML literal strings (single quotes) don't process escape sequences
            if "'" in v:
                # Fall back to basic string with escaped backslashes
                return '"' + v.replace("\\", "\\\\") + '"'
            return f"'{v}'"

        lines: list[str] = []
        # Use forward slashes for path to avoid TOML escape issues
        path_str = str(self.library_path).replace("\\", "/")
        lines.append(f"library_path = '{path_str}'")
        lines.append("")

        lines.append("[llm]")
        lines.append(f"local_model = {_val(self.llm.local_model)}")
        lines.append(f"cloud_model = {_val(self.llm.cloud_model)}")
        lines.append(f"embedding_model = {_val(self.llm.embedding_model)}")
        lines.append(f"api_base = {_val(self.llm.api_base)}")
        lines.append("")

        lines.append("[api_keys]")
        lines.append(f"semantic_scholar = {_val(self.api_keys.semantic_scholar)}")
        lines.append(f"openai = {_val(self.api_keys.openai)}")
        lines.append(f"anthropic = {_val(self.api_keys.anthropic)}")
        lines.append(f"ieee_xplore = {_val(self.api_keys.ieee_xplore)}")
        lines.append(f"unpaywall_email = {_val(self.api_keys.unpaywall_email)}")
        lines.append("")

        lines.append("[search]")
        sources = ", ".join(f"'{s}'" for s in self.search.default_sources)
        lines.append(f"default_sources = [{sources}]")
        lines.append(f"default_limit = {self.search.default_limit}")
        lines.append("")

        lines.append("[parser]")
        lines.append(f"preferred = {_val(self.parser.preferred)}")
        lines.append(f"grobid_url = {_val(self.parser.grobid_url)}")
        lines.append(f"chunk_size = {self.parser.chunk_size}")
        lines.append(f"chunk_overlap = {self.parser.chunk_overlap}")
        lines.append("")

        lines.append("[notify]")
        lines.append(f"wechat_webhook = {_val(self.notify.wechat_webhook)}")
        lines.append(f"feishu_webhook = {_val(self.notify.feishu_webhook)}")
        lines.append(f"dingtalk_webhook = {_val(self.notify.dingtalk_webhook)}")
        lines.append(f"smtp_host = {_val(self.notify.smtp_host)}")
        lines.append(f"smtp_port = {self.notify.smtp_port}")
        lines.append(f"smtp_username = {_val(self.notify.smtp_username)}")
        lines.append(f"smtp_password = {_val(self.notify.smtp_password)}")
        lines.append(f"email_recipient = {_val(self.notify.email_recipient)}")
        lines.append("")

        lines.append("[campus]")
        lines.append(f"enabled = {'true' if self.campus.enabled else 'false'}")
        lines.append(f"http_proxy = {_val(self.campus.http_proxy)}")
        lines.append(f"https_proxy = {_val(self.campus.https_proxy)}")
        lines.append(f"ieee_inst_url = {_val(self.campus.ieee_inst_url)}")
        lines.append(f"acm_inst_url = {_val(self.campus.acm_inst_url)}")
        lines.append("")

        # Domain section
        if self.domain.is_initialized():
            lines.append("[domain]")
            lines.append(f"domain_name = '{self.domain.domain_name}'")
            lines.append("")
            if self.domain.l0_keywords:
                lines.append("[domain.l0_keywords]")
                for group, keywords in self.domain.l0_keywords.items():
                    kw_str = ", ".join(f"'{k}'" for k in keywords)
                    lines.append(f"{group} = [{kw_str}]")
                lines.append("")
            if self.domain.l1_vocabulary:
                lines.append("[domain.l1_vocabulary]")
                for canonical, aliases in self.domain.l1_vocabulary.items():
                    alias_str = ", ".join(f"'{a}'" for a in aliases)
                    lines.append(f"{canonical} = [{alias_str}]")
                lines.append("")
            if self.domain.l1_prompt_template:
                template = self.domain.l1_prompt_template.replace("\\", "\\\\")
                lines.append(f"l1_prompt_template = '{template}'")
            lines.append("")

        return "\n".join(lines)
