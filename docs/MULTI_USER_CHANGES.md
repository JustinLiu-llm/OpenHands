# OpenHands Multi-User Support

This document describes the changes made to support multi-user isolation in OpenHands.

## Overview

The multi-user feature enables multiple users to use OpenHands with isolated configurations, conversations, and workspaces. Each user has their own settings and data that are completely separated from other users.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (3001)                      │
│  User A Browser  ←→  User B Browser  ←→  User C Browser    │
└─────────────────────────────────────────────────────────────┘
                              ↓ HTTP + JWT
┌─────────────────────────────────────────────────────────────┐
│                      Backend API (3000)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ User A     │  │ User B     │  │ User C     │        │
│  │ (JWT验证)   │  │ (JWT验证)   │  │ (JWT验证)   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              User-Isolated Storage                          │
│  ~/.openhands/users/{user_id}/                             │
│  ├── .openhands/settings.json    # User settings            │
│  ├── .openhands/secrets.json   # User API keys             │
│  ├── conversations/             # User conversations       │
│  └── workspace/                # User workspace            │
└─────────────────────────────────────────────────────────────┘
```

## Changes Made

### 1. Authentication System

**Files Modified:**
- `openhands/server/routes/auth.py` (NEW)
- `openhands/server/services/auth_service.py` (NEW)
- `openhands/server/services/user_onboarding.py` (NEW)

**Features:**
- JWT-based user authentication
- User registration with email/password
- Login with credentials
- Token-based session management

**API Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/auth/register | Register new user |
| POST | /api/auth/login | Login |
| GET | /api/auth/me | Get current user |
| GET | /api/auth/verify | Verify token |

### 2. Settings Isolation

**Files Modified:**
- `openhands/storage/settings/file_settings_store.py`
- `openhands/storage/secrets/file_secrets_store.py`

**Changes:**
- Added `user_id` parameter to `get_instance()` method
- User-specific settings stored in `~/.openhands/users/{user_id}/.openhands/`

### 3. Conversation Isolation

**Files Modified:**
- `openhands/storage/conversation/file_conversation_store.py`

**Changes:**
- Conversations stored in `~/.openhands/users/{user_id}/conversations/`
- Each user can only access their own conversations

### 4. User Authentication Backend

**Files Modified:**
- `openhands/server/user_auth/jwt_user_auth.py` (NEW)
- `openhands/server/user_auth/user_auth.py`
- `openhands/server/config/server_config.py`

**Changes:**
- Created JWT-based authentication class
- Updated default auth class to use JWT
- Fixed caching issues that caused configuration sharing between users

### 5. Frontend Integration

**Files Modified:**
- `frontend/src/api/auth.ts` (NEW)
- `frontend/src/api/client.ts` (NEW)
- `frontend/src/api/open-hands-axios.ts`
- `frontend/src/hooks/use-auth.ts` (NEW)
- `frontend/src/routes/login.tsx`
- `frontend/src/components/features/auth/email-auth-form.tsx` (NEW)
- `frontend/src/components/features/auth/login-content.tsx`
- `frontend/src/components/features/sidebar/chat-sidebar.tsx`

**Features:**
- Email/password login and registration UI
- JWT token storage in localStorage
- Automatic token injection in API requests
- Logout functionality

## Key Fixes

### Bug Fix: User Configuration Sharing

**Problem:** Multiple users were sharing the same configuration due to caching issues.

**Solution:**
1. Removed `request.state.user_auth` caching in `get_user_auth()` function
2. Removed `_settings` caching in `JWTUserAuth` class
3. Each request now creates a fresh instance

**Files Changed:**
- `openhands/server/user_auth/user_auth.py`
- `openhands/server/user_auth/jwt_user_auth.py`

### Bug Fix: Settings Cache

**Problem:** Settings were cached in memory, causing all users to see the same configuration.

**Solution:** Removed all caching in `get_user_settings()` method to always read from disk.

### Bug Fix: Onboarding Configuration

**Problem:** New users were copying global configuration instead of using default.

**Solution:** Modified `user_onboarding.py` to always create fresh default config instead of copying global settings.

## Storage Structure

```
~/.openhands/
├── settings.json              # Global default (optional)
├── users/
│   ├── {user_id_1}/
│   │   ├── metadata.json
│   │   ├── .openhands/
│   │   │   ├── settings.json
│   │   │   └── secrets.json
│   │   ├── conversations/
│   │   │   └── {conversation_id}/
│   │   └── workspace/
│   └── {user_id_2}/
│       └── ...
```

## Default Configuration

New users get these default settings:
- **Model:** openai/MiniMax-M2.5
- **API URL:** https://api.minimaxi.com/v1
- **Language:** zh
- **Agent:** CodeActAgent

## Running the Application

### Backend
```bash
cd /path/to/OpenHands
.venv/bin/python -m uvicorn openhands.server.listen:app --host 0.0.0.0 --port 3000
```

### Frontend
```bash
cd frontend
npm run dev -- --port 3001 --host 127.0.0.1
```

## Known Limitations

1. **In-Memory User Store**: User data is stored in memory and lost on restart. Production should use PostgreSQL.
2. **Conversation List API**: Still returns all users' conversations from legacy database (new conversations are isolated).
3. **Container Sharing**: Runtime containers are created per conversation, not per user.
4. **No Quota Limits**: No resource limits per user yet.

## Future Improvements

- [ ] Add PostgreSQL database for persistent user storage
- [ ] Add container pooling for faster startup
- [ ] Implement per-user resource quotas
- [ ] Add team/organization support
- [ ] Complete conversation list isolation
