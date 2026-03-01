from __future__ import annotations

import json
import os
from dataclasses import dataclass

from openhands.core.config.openhands_config import OpenHandsConfig
from openhands.core.logger import openhands_logger as logger
from openhands.storage import get_file_store
from openhands.storage.data_models.secrets import Secrets
from openhands.storage.files import FileStore
from openhands.storage.secrets.secrets_store import SecretsStore
from openhands.utils.async_utils import call_sync_from_async


# 用户隔离的配置目录
def get_user_secrets_path(user_id: str | None, config: OpenHandsConfig) -> str:
    """获取用户隔离的 secrets 路径"""
    if user_id:
        base_path = os.path.expanduser(config.file_store_path or "~/.openhands")
        return os.path.join(base_path, "users", user_id, ".openhands")
    else:
        return os.path.expanduser(config.file_store_path or "~/.openhands")


@dataclass
class FileSecretsStore(SecretsStore):
    file_store: FileStore
    path: str = 'secrets.json'
    user_id: str | None = None

    async def load(self) -> Secrets | None:
        try:
            json_str = await call_sync_from_async(self.file_store.read, self.path)
            kwargs = json.loads(json_str)
            provider_tokens = {
                k: v
                for k, v in (kwargs.get('provider_tokens') or {}).items()
                if v.get('token')
            }
            kwargs['provider_tokens'] = provider_tokens
            secrets = Secrets(**kwargs)
            return secrets
        except FileNotFoundError:
            if self.user_id:
                logger.warning(f"User secrets not found for user: {self.user_id}")
            return None

    async def store(self, secrets: Secrets) -> None:
        json_str = secrets.model_dump_json(context={'expose_secrets': True})
        await call_sync_from_async(self.file_store.write, self.path, json_str)

    @classmethod
    async def get_instance(
        cls, config: OpenHandsConfig, user_id: str | None
    ) -> FileSecretsStore:
        # 获取用户隔离的 secrets 路径
        user_secrets_path = get_user_secrets_path(user_id, config)
        
        logger.info(f"Creating FileSecretsStore for user_id={user_id}, path={user_secrets_path}")
        
        file_store = get_file_store(
            file_store_type=config.file_store,
            file_store_path=user_secrets_path,
            file_store_web_hook_url=config.file_store_web_hook_url,
            file_store_web_hook_headers=config.file_store_web_hook_headers,
            file_store_web_hook_batch=config.file_store_web_hook_batch,
        )
        
        # 确保目录存在
        os.makedirs(user_secrets_path, exist_ok=True)
        
        return FileSecretsStore(file_store=file_store, user_id=user_id)
