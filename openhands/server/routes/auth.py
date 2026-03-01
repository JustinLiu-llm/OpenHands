from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

from openhands.core.logger import openhands_logger as logger
from openhands.server.services.auth_service import (
    user_store,
    generate_jwt,
    verify_jwt,
    TokenData,
    User,
)
from openhands.server.services.user_onboarding import UserOnboardingService


app = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


# Request/Response Models
class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    user: User


class UserProfileResponse(BaseModel):
    user_id: str
    email: str
    username: str
    created_at: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenData:
    """获取当前登录用户"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    
    return verify_jwt(credentials.credentials)


@app.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """用户注册"""
    logger.info(f"Register request for email: {request.email}")
    
    # 1. 创建用户
    user = await user_store.create_user(
        email=request.email,
        username=request.username,
        password=request.password,
    )
    
    # 2. 创建用户目录结构
    onboarding = UserOnboardingService()
    await onboarding.create_user(user.user_id, request.email)
    
    # 3. 生成 Token
    token = generate_jwt(user.user_id, user.email)
    
    return AuthResponse(token=token, user=user)


@app.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """用户登录"""
    logger.info(f"Login request for email: {request.email}")
    
    user = await user_store.authenticate(request.email, request.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    token = generate_jwt(user.user_id, user.email)
    
    return AuthResponse(token=token, user=user)


@app.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: TokenData = Depends(get_current_user)):
    """获取当前用户信息"""
    user_data = await user_store.get_user(current_user.user_id)
    
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return UserProfileResponse(
        user_id=user_data["user_id"],
        email=user_data["email"],
        username=user_data["username"],
        created_at=user_data["created_at"],
    )


@app.post("/logout")
async def logout():
    """用户登出"""
    # JWT 是无状态的，登出由客户端删除 token
    return {"message": "Logged out successfully"}


@app.get("/verify")
async def verify_token(current_user: TokenData = Depends(get_current_user)):
    """验证 Token 是否有效"""
    return {
        "valid": True,
        "user_id": current_user.user_id,
        "email": current_user.email,
    }
