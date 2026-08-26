"""凭据加密（M10 安全批次）：Fernet 对称加密 + 首启自动生成密钥（0600）。

小白零配置：首次使用时自动生成密钥到 ~/.config/talentforge/secret.key（0600 权限），
之后透明加解密。密钥与密文分离——key 在配置目录（不随数据迁移/备份），密文在数据目录。
现有明文凭据自动迁移：读取时检测非 Fernet 格式 → 按明文返回并触发加密重写。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_KEY_ENV = "TALENTFORGE_SECRET_KEY_FILE"
_KEY_DIR = Path.home() / ".config" / "talentforge"
_KEY_FILE = _KEY_DIR / "secret.key"

# Fernet token 固定前缀（用于区分密文与遗留明文）
_FERNET_PREFIX = "gAAAAA"


def _key_path() -> Path:
    env = os.environ.get(_KEY_ENV)
    return Path(env) if env else _KEY_FILE


def _load_or_create_key() -> bytes:
    """读密钥；不存在则生成并写 0600 文件（目录 0700）。"""
    path = _key_path()
    try:
        key = path.read_bytes()
        if len(key) == 44:  # Fernet key 长度（base64 urlsafe 44 字节）
            return key
        logger.warning("密钥文件 %s 长度异常（%d），重新生成", path, len(key))
    except OSError:
        pass
    key = Fernet.generate_key()
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        logger.info("已生成凭据加密密钥 %s", path)
    except OSError as exc:
        logger.warning("写入密钥文件失败（%s）：凭据将无法加密，仅警告不阻断", exc)
    return key


_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt_value(plaintext: str) -> str:
    """加密字符串 → Fernet token（str）。空串保持空串。"""
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_value(token: str) -> str:
    """解密 Fernet token → 原字符串；非法 token（含遗留明文）原样返回。"""
    if not token:
        return ""
    try:
        return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        return token


def is_encrypted(value: str) -> bool:
    """判断值是否为 Fernet 密文（用于旧明文迁移检测）。"""
    return value.startswith(_FERNET_PREFIX) and len(value) > 32
