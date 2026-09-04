import hashlib
import logging
import secrets

from fastapi import APIRouter, HTTPException, Depends, Response, Cookie, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import pymysql
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from app.core.database import get_db_connection
from app.core.audit import audit
from app.schemas.auth import LoginRequest, RegisterRequest

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)
_LOGIN_WINDOW_SECONDS = 60
_LOGIN_MAX_ATTEMPTS = 10
_REFRESH_COOKIE = "refresh_token"


def _hash_token(token: str) -> str:
    """refresh token 只以 SHA-256 摘要落库，明文不存库、不可逆。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _issue_refresh_token(connection, user_id: int, client_ip: str | None) -> str:
    """签发一个不透明 refresh token，明文仅经 HttpOnly Cookie 下发。

    有效期由 settings.REFRESH_TOKEN_EXPIRE_DAYS 控制；到期后服务端拒绝续期。
    """
    plain = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at, client_ip) "
            "VALUES (%s, %s, %s, %s)",
            (user_id, _hash_token(plain), expires_at, client_ip),
        )
    connection.commit()
    return plain


def _lookup_refresh_token(connection, token: str):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT refresh_token_id, user_id, expires_at, revoked_at "
            "FROM refresh_tokens WHERE token_hash = %s",
            (_hash_token(token),),
        )
        return cursor.fetchone()


def _revoke_refresh_token(connection, refresh_token_id: int) -> None:
    """服务端撤销：置 revoked_at，任何携带该 token 的后续请求都会被拒绝。"""
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE refresh_tokens SET revoked_at = NOW() "
            "WHERE refresh_token_id = %s",
            (refresh_token_id,),
        )
    connection.commit()


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """统一签发认证 Cookie：均 HttpOnly + SameSite=Lax，生产环境追加 Secure。"""
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        _REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
    )


def _build_access_token(user_id: int) -> str:
    """签发短期 JWT access token（iss/aud 校验见 get_current_user_id）。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iss": "wishindiary-api",
        "aud": "wishindiary-web",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _check_login_rate_limit(client_key: str) -> bool:
    """基于 MySQL 表的滑动窗口登录限流（多进程/多实例共享）。

    限流计数存放在 login_attempts 表，窗口内达到上限返回 False。
    每次调用先惰性清理该 key 的过期记录，再统计窗口内记录数；
    未超限则插入一条记录（登录成败都会占用计数，与历史行为一致）。

    DB 不可用时不阻断登录流程（fail-open 并记录日志），
    由后续登录查询统一处理 503，避免限流表故障导致登录假死。
    """
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            # 清理该 key 的过期记录（滑动窗口）
            cursor.execute(
                "DELETE FROM login_attempts "
                "WHERE client_key = %s AND attempted_at < NOW() - INTERVAL %s SECOND",
                (client_key, _LOGIN_WINDOW_SECONDS),
            )
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM login_attempts "
                "WHERE client_key = %s AND attempted_at >= NOW() - INTERVAL %s SECOND",
                (client_key, _LOGIN_WINDOW_SECONDS),
            )
            row = cursor.fetchone()
            count = int(row["cnt"]) if row else 0
            if count >= _LOGIN_MAX_ATTEMPTS:
                connection.commit()
                return False
            cursor.execute(
                "INSERT INTO login_attempts (client_key, attempted_at, success) "
                "VALUES (%s, NOW(), %s)",
                (client_key, 0),
            )
        connection.commit()
        return True
    except pymysql.MySQLError:
        # 限流表查询失败不阻断登录，由后续业务逻辑处理 DB 故障
        logger.exception("Rate-limit table check failed for client_key=%s", client_key)
        return True
    finally:
        if connection is not None:
            connection.close()

security = HTTPBearer(auto_error=False)

# 1. 核心鉴权依赖项：供其他业务接口安全提取 user_id
def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    access_token: str | None = Cookie(default=None),
) -> int:
    token = credentials.credentials if credentials else access_token
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要登录")
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            issuer="wishindiary-api",
            audience="wishindiary-web",
            options={"require": ["exp", "iat", "sub"]},
        )
        try:
            user_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证凭证")
        if user_id <= 0:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证凭证")
        # 追加用户存在性校验：账号被删除后旧 JWT 立即失效，不能继续访问业务数据。
        connection = None
        try:
            connection = get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不存在")
        except pymysql.MySQLError:
            logger.exception("get_current_user_id: 用户存在性校验查询失败 user_id=%s", user_id)
            raise HTTPException(status_code=503, detail="数据库连接失败，请稍后重试")
        finally:
            if connection is not None:
                connection.close()
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 已过期，请重新登录")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无法验证凭证")

@router.post("/register")
def register(req: RegisterRequest):
    if len(req.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="密码 UTF-8 字节长度不能超过 72")
    connection = None
    try:
        connection = get_db_connection()
        hashed_password = bcrypt.hashpw(req.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (req.username, hashed_password)
            )
            new_user_id = int(cursor.lastrowid)
        connection.commit()
        audit("auth.register", actor_user_id=new_user_id, username=req.username, success=True)
        return {"status": "success", "message": "注册成功", "user_id": new_user_id}
    except pymysql.err.IntegrityError:
        if connection is not None:
            connection.rollback()
        raise HTTPException(status_code=400, detail="用户名已存在")
    except pymysql.err.OperationalError:
        if connection is not None:
            connection.rollback()
        logger.exception("Registration database connection failed")
        raise HTTPException(status_code=503, detail="数据库连接失败，请检查 wishindiary-api/.env")
    except Exception:
        if connection is not None:
            connection.rollback()
        logger.exception("Registration failed for username=%s", req.username)
        raise HTTPException(status_code=500, detail="注册失败，请稍后重试")
    finally:
        if connection is not None:
            connection.close()

@router.post("/login")
def login(req: LoginRequest, response: Response, request: Request):
    client_key = request.client.host if request.client else "unknown"
    # 基于 MySQL 表的共享限流（跨进程/实例），不再使用进程内字典
    if not _check_login_rate_limit(client_key):
        audit("auth.login.rate_limited", username=req.username, ip=client_key, success=False)
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")
    if len(req.password.encode("utf-8")) > 72:
        audit("auth.login.invalid", username=req.username, ip=client_key, success=False)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT user_id, password_hash FROM users WHERE username = %s", (req.username,))
            user = cursor.fetchone()

        if not user or not bcrypt.checkpw(req.password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            audit("auth.login.failed", username=req.username, ip=client_key, success=False)
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 2. 签发短期 JWT access token + 长期 refresh token（服务端可撤销）
        access_token = _build_access_token(user["user_id"])
        refresh_token = _issue_refresh_token(connection, user["user_id"], client_key)
        _set_auth_cookies(response, access_token, refresh_token)
        audit("auth.login.success", actor_user_id=user["user_id"], username=req.username, ip=client_key, success=True)

        # 3. 安全实践：登录响应体不再携带 JWT，仅保留 HttpOnly Cookie。
        return {
            "status": "success",
            "user_id": user['user_id'],
            "username": req.username
        }
    except HTTPException as he:
        raise he
    except pymysql.err.OperationalError:
        logger.exception("Login database connection failed")
        raise HTTPException(status_code=503, detail="数据库连接失败，请检查 wishindiary-api/.env")
    except Exception:
        logger.exception("Login failed for username=%s", req.username)
        raise HTTPException(status_code=500, detail="登录失败，请稍后重试")
    finally:
        if connection is not None:
            connection.close()


@router.get("/session")
def get_session(user_id: int = Depends(get_current_user_id)):
    """Return the authenticated user's public session data.

    The web client uses this endpoint after a page refresh instead of trusting
    user-controlled browser storage as proof of authentication.
    """
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT user_id, username FROM users WHERE user_id = %s",
                (user_id,),
            )
            user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
        return {"status": "success", "user_id": user["user_id"], "username": user["username"]}
    except HTTPException:
        raise
    except pymysql.err.OperationalError:
        logger.exception("Session database connection failed for user_id=%s", user_id)
        raise HTTPException(status_code=503, detail="数据库连接失败，请稍后重试")
    except Exception:
        logger.exception("Session lookup failed for user_id=%s", user_id)
        raise HTTPException(status_code=500, detail="会话查询失败，请稍后重试")
    finally:
        if connection is not None:
            connection.close()


@router.post("/logout")
def logout(response: Response, request: Request, refresh_token: str | None = Cookie(default=None)):
    """退出登录：服务端撤销当前 refresh token + 清除两个认证 Cookie。

    即便 Cookie 被手动清除，撤销记录仍会阻止该 refresh token 被再次使用；
    撤销状态存于 MySQL，可跨进程/多实例共享。
    """
    client_ip = request.client.host if request.client else None
    actor_user_id: int | None = None
    connection = None
    try:
        connection = get_db_connection()
        if refresh_token:
            row = _lookup_refresh_token(connection, refresh_token)
            if row:
                _revoke_refresh_token(connection, row["refresh_token_id"])
                actor_user_id = row["user_id"]
    except pymysql.MySQLError:
        # 撤销失败不阻断登出（Cookie 已清除），但记日志便于排查
        logger.exception("Logout: failed to revoke refresh token")
    finally:
        if connection is not None:
            connection.close()
    response.delete_cookie("access_token", path="/")
    response.delete_cookie(_REFRESH_COOKIE, path="/")
    audit("auth.logout", actor_user_id=actor_user_id, ip=client_ip, success=True)
    return {"status": "success"}


@router.post("/refresh")
def refresh_access_token(
    response: Response,
    request: Request,
    refresh_token: str | None = Cookie(default=None),
):
    """用长期 refresh token 换取新的 access token（无感续期）。

    安全策略：
    1. 过期控制：refresh token 超过 REFRESH_TOKEN_EXPIRE_DAYS 直接拒绝；
    2. 服务端撤销：已被撤销（退出登录/上次刷新轮换）的 token 拒绝；
    3. 刷新轮换：每次成功刷新都会撤销旧 refresh token 并签发新 token，
       重放旧 token 立即失效，降低泄露窗口。
    """
    client_ip = request.client.host if request.client else None
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少刷新令牌")
    connection = None
    try:
        connection = get_db_connection()
        row = _lookup_refresh_token(connection, refresh_token)
        if not row:
            audit("auth.refresh.invalid", ip=client_ip, success=False)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌无效")
        user_id = int(row["user_id"])
        if row["revoked_at"] is not None:
            audit("auth.refresh.revoked", actor_user_id=user_id, ip=client_ip, success=False)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌已被撤销")
        expires_naive = row["expires_at"]
        if expires_naive is not None and expires_naive.tzinfo is not None:
            expires_naive = expires_naive.replace(tzinfo=None)
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        if expires_naive <= now_naive:
            audit("auth.refresh.expired", actor_user_id=user_id, ip=client_ip, success=False)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌已过期，请重新登录")

        # 轮换：撤销旧 refresh token，签发新 access + 新 refresh
        _revoke_refresh_token(connection, row["refresh_token_id"])
        access_token = _build_access_token(user_id)
        new_refresh = _issue_refresh_token(connection, user_id, client_ip)
        _set_auth_cookies(response, access_token, new_refresh)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT username FROM users WHERE user_id = %s",
                (user_id,),
            )
            user_row = cursor.fetchone()
        username = user_row["username"] if user_row else None
        audit("auth.refresh.success", actor_user_id=user_id, username=username, ip=client_ip, success=True)
        return {"status": "success", "user_id": user_id, "username": username}
    except HTTPException:
        raise
    except pymysql.err.OperationalError:
        logger.exception("Refresh: database connection failed")
        raise HTTPException(status_code=503, detail="数据库连接失败，请检查 wishindiary-api/.env")
    except Exception:
        logger.exception("Refresh failed for user_id")
        raise HTTPException(status_code=500, detail="刷新令牌失败，请稍后重试")
    finally:
        if connection is not None:
            connection.close()
