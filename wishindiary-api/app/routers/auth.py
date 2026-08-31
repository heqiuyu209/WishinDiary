import logging
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Depends, Response, Cookie, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import pymysql
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from app.core.database import get_db_connection

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)
_login_attempts: dict[str, deque[float]] = defaultdict(deque)
_LOGIN_WINDOW_SECONDS = 60
_LOGIN_MAX_ATTEMPTS = 10

security = HTTPBearer(auto_error=False)

class UserAuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)


class RegisterRequest(UserAuthRequest):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(UserAuthRequest):
    # Keep legacy accounts usable; new registrations still require 8+ characters.
    password: str = Field(min_length=1, max_length=128)

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
        connection.commit()
        return {"status": "success", "message": "注册成功"}
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
    now_monotonic = time.monotonic()
    attempts = _login_attempts[client_key]
    while attempts and now_monotonic - attempts[0] > _LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")
    attempts.append(now_monotonic)
    if len(req.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT user_id, password_hash FROM users WHERE username = %s", (req.username,))
            user = cursor.fetchone()

        if not user or not bcrypt.checkpw(req.password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 2. 签发短期 JWT Token
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user["user_id"]),
            "iss": "wishindiary-api",
            "aud": "wishindiary-web",
            "iat": now,
            "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        access_token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        response.set_cookie(
            "access_token",
            access_token,
            httponly=True,
            secure=settings.ENVIRONMENT == "production",
            samesite="lax",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )

        return {
            "status": "success",
            "access_token": access_token,
            "token_type": "bearer",
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
def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"status": "success"}
