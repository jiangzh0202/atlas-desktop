"""
元策·擎天 认证中间件
Flask 装饰器：从 Authorization header 解析 JWT → 注入角色 → 检查权限

用法:
  @require_role('quote')    # 报价员/主管/老板可访问
  @require_role('procure')  # 采购员/主管/老板可访问
  @require_role('manage')   # 主管/老板可访问
  @require_role('platform') # 仅管理员
"""
import functools
import hashlib
import hmac
import base64
import json
import time
from flask import request, jsonify, g
from config import cfg
from models import get_user, role_can

JWT_SECRET = cfg.get("jwt", "secret", default="atlas-v3-modular-2026")

def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64url_decode(s: str) -> bytes:
    s = s + "=" * (4 - len(s) % 4) if len(s) % 4 else s
    return base64.urlsafe_b64decode(s)

def sign_jwt(payload: dict) -> str:
    header = _base64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _base64url(json.dumps(payload).encode())
    sig = hmac.new(JWT_SECRET.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_base64url(sig)}"

def verify_jwt(token: str) -> dict | None:
    """验证 JWT，成功返回 payload dict，失败返回 None"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        expected_sig = hmac.new(
            JWT_SECRET.encode(),
            f"{header_b64}.{payload_b64}".encode(),
            hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        # 检查过期
        exp = payload.get("exp", 0)
        if exp and exp < time.time():
            return None
        return payload
    except Exception:
        return None

def parse_auth():
    """从请求中提取用户信息，注入 g.user。返回 (user_dict, error_response_or_None)"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, (jsonify({"ok": False, "error": "未登录"}), 401)

    token = auth[7:]
    payload = verify_jwt(token)
    if not payload:
        return None, (jsonify({"ok": False, "error": "登录已过期"}), 401)

    user_id = payload.get("user_id") or payload.get("sub")
    if not user_id:
        return None, (jsonify({"ok": False, "error": "无效令牌"}), 401)

    user = get_user(user_id)
    if not user:
        return None, (jsonify({"ok": False, "error": "用户不存在"}), 401)
    if user.get("status") != "active":
        return None, (jsonify({"ok": False, "error": "账号已停用"}), 403)

    g.user = user
    g.user_id = user["id"]
    g.role = user["role"]
    g.company_id = user.get("company_id", "")
    return user, None

def require_auth(f):
    """要求登录（不检查角色）"""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        user, err = parse_auth()
        if err:
            return err
        return f(*args, **kwargs)
    return wrapper

def require_role(action: str):
    """要求登录 + 特定角色权限"""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            user, err = parse_auth()
            if err:
                return err
            if not role_can(user["role"], action):
                return jsonify({"ok": False, "error": f"权限不足（需要:{action}，当前:{user['role']}）"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator
