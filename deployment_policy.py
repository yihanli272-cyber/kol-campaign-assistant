"""Fail-closed server-side write policy. Browser/session input cannot enable writes."""
import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name('deployment_config.json')


def deployment_mode():
    override=os.environ.get('KOL_DEPLOYMENT_MODE')
    if override is not None:
        return 'local_dev' if override.strip()=='local_dev' else 'public_demo'
    try:
        configured=json.loads(CONFIG_PATH.read_text(encoding='utf-8')).get('mode')
    except (OSError,ValueError,TypeError,AttributeError):
        return 'public_demo'
    return 'local_dev' if configured=='local_dev' else 'public_demo'


def is_local_development():
    return deployment_mode()=='local_dev'


def require_server_write(operation):
    if not is_local_development():
        raise PermissionError(f'公开展示模式禁止服务端写入：{operation}。仅可由本地开发环境显式启用。')
