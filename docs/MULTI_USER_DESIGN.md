# OpenHands 多用户架构设计方案

## 一、当前代码分析

### 1.1 核心模块

| 模块 | 路径 | 功能 |
|-----|------|------|
| **server/** | `openhands/server/` | Web API 服务 |
| **conversation_manager/** | `openhands/server/conversation_manager/` | 会话管理 |
| **runtime/** | `openhands/runtime/` | 沙箱执行环境 |
| **storage/** | `openhands/storage/` | 数据持久化 |
| **user_auth/** | `openhands/server/user_auth/` | 用户认证 |

### 1.2 当前限制

```python
# openhands/server/user_auth/default_user_auth.py
async def get_user_id(self) -> str | None:
    """The default implementation does not support multi tenancy, so user_id is always None"""
    return None
```

- ❌ 无用户隔离，所有用户共享同一设置
- ❌ 无 Token 认证机制
- ❌ 每个会话共享运行时容器（Docker 模式）
- ❌ Settings 存储在全局 `~/.openhands/settings.json`

---

## 二、多用户架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户访问层                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Web UI     │  │   API        │  │   WebSocket  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                      认证与授权层                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  JWT Auth    │  │   RBAC      │  │   Quota     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                      用户数据层 (新增)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   PostgreSQL │  │    Redis     │  │    S3/MinIO │          │
│  │  (用户/会话)  │  │  (会话缓存)  │  │  (文件存储)  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                      运行时隔离层                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  per-user    │  │  per-session │  │   Workspace  │          │
│  │  container   │  │  container   │  │   isolation │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心改动

#### 2.2.1 用户认证系统

```python
# 新增: openhands/server/user_auth/jwt_user_auth.py
class JWTUserAuth(UserAuth):
    """基于 JWT 的多用户认证"""
    
    async def get_user_id(self) -> str:
        """从 JWT token 中解析 user_id"""
        token = await self._extract_token()
        payload = jwt.decode(token, SECRET_KEY)
        return payload['user_id']
    
    async def get_user_email(self) -> str:
        """获取用户邮箱"""
        ...
    
    async def get_user_settings_store(self) -> SettingsStore:
        """获取用户隔离的设置存储"""
        user_id = await self.get_user_id()
        return await shared.SettingsStoreImpl.get_instance(
            shared.config, user_id  # 传入 user_id 实现隔离
        )
```

#### 2.2.2 用户隔离存储

```python
# 修改: openhands/storage/settings/file_settings_store.py
class FileSettingsStore(SettingsStore):
    """支持用户隔离的设置存储"""
    
    async def get_instance(config: OpenHandsConfig, user_id: str | None = None):
        # 如果 user_id 为 None，使用全局存储 (兼容旧模式)
        # 如果 user_id 存在，使用用户隔离目录
        if user_id:
            base_path = f"~/.openhands/users/{user_id}/settings.json"
        else:
            base_path = "~/.openhands/settings.json"
```

#### 2.2.3 用户隔离的工作空间

```python
# 新增: openhands/server/routes/workspace.py
@app.post("/api/workspace/{user_id}")
async def get_user_workspace(user_id: str = Depends(get_current_user)):
    """获取用户隔离的工作空间路径"""
    workspace_path = f"/workspace/users/{user_id}"
    return {"workspace_path": workspace_path}
```

**目录结构:**
```
/workspace/
├── users/
│   ├── user_123/
│   │   ├── .openhands/     # 用户配置
│   │   └── workspace/       # 用户文件
│   └── user_456/
│       ├── .openhands/
│       └── workspace/
└── shared/                  # 共享资源（可选）
```

#### 2.2.4 容器隔离策略

| 策略 | 说明 | 适用场景 |
|-----|------|---------|
| **per-session** | 每个会话一个容器 | 高安全要求 |
| **per-user** | 每个用户一个容器，复用 | 中等安全要求 |
| **shared** | 共享容器，进程隔离 | 低安全要求 |

```python
# 修改: openhands/runtime/impl/docker/docker_runtime.py
class DockerRuntime:
    """支持用户隔离的 Docker 运行时"""
    
    async def create_runtime(self, user_id: str, session_id: str):
        container_name = f"openhands-{user_id}-{session_id}"
        # 用户隔离的容器名称
```

---

## 三、数据库设计 (PostgreSQL)

### 3.1 用户表

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    
    -- 配额管理
    max_concurrent_sessions INTEGER DEFAULT 3,
    max_iterations INTEGER DEFAULT 500,
    storage_quota_gb INTEGER DEFAULT 10
);
```

### 3.2 会话表

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    
    -- 会话配置
    llm_model VARCHAR(100),
    runtime_type VARCHAR(50) DEFAULT 'docker',
    
    -- 状态
    status VARCHAR(20) DEFAULT 'idle',  -- idle, running, paused, terminated
    container_id VARCHAR(100),
    
    -- 资源使用
    iterations_used INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 3.3 API Keys 表

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,  -- openai, anthropic, minimax
    encrypted_key VARCHAR(255) NOT NULL,
    label VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP
);
```

---

## 四、API 设计

### 4.1 认证 API

| 方法 | 路径 | 说明 |
|-----|------|------|
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/auth/me` | 获取当前用户 |

### 4.2 用户 API

| 方法 | 路径 | 说明 |
|-----|------|------|
| GET | `/api/users/me` | 获取用户信息 |
| PUT | `/api/users/me` | 更新用户设置 |
| GET | `/api/users/me/quotas` | 获取配额使用 |

### 4.3 会话 API

| 方法 | 路径 | 说明 |
|-----|------|------|
| GET | `/api/sessions` | 列出用户会话 |
| POST | `/api/sessions` | 创建新会话 |
| GET | `/api/sessions/{id}` | 获取会话详情 |
| DELETE | `/api/sessions/{id}` | 删除会话 |

---

## 五、实施计划

### Phase 1: 基础架构 (1-2 周)

- [ ] 设计并实现用户数据库
- [ ] 实现 JWT 认证系统
- [ ] 修改 Settings 存储支持用户隔离

### Phase 2: 会话隔离 (1 周)

- [ ] 修改 ConversationManager 支持 user_id
- [ ] 实现用户工作空间隔离
- [ ] 容器命名添加 user_id 前缀

### Phase 3: 配额与限制 (1 周)

- [ ] 实现用户配额管理
- [ ] 添加并发会话限制
- [ ] 实现资源使用统计

### Phase 4: 生产部署 (1 周)

- [ ] Docker Compose 编排
- [ ] PostgreSQL + Redis 集成
- [ ] 日志与监控

---

## 六、配置文件变更

### docker-compose.yml (新增)

```yaml
version: '3.8'
services:
  openhands:
    # ... existing config
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/openhands
      - REDIS_URL=redis://redis:6379
      - JWT_SECRET=your-secret-key
      - MULTI_USER_MODE=true

  db:
    image: postgres:15
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: openhands

  redis:
    image: redis:7
```

---

## 七、向后兼容性

- 新增 `MULTI_USER_MODE` 环境变量
- 当 `MULTI_USER_MODE=false` 时，保持原有单用户行为
- 现有 API 端点保持兼容，通过 JWT token 区分
