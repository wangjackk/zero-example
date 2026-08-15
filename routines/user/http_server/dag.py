"""DAG 子系统 HTTP/WS handler 函数.

由 ``server.HttpServer._on_client_message`` 和 ``app.build_app`` 调用.
设计成模块级函数(接收 ``inst`` 第一参数),避免 HttpServer 类膨胀 ----
DAG 是可选子系统,import 失败时降级为空列表.
"""
from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# dag 子系统可选(新版本未移植).import 失败时降级为空列表.
try:
    from ..dag import DAG_DIR  # type: ignore
    from ..dag.loader import load_dag_yaml_file  # type: ignore
    _DAG_AVAILABLE = True
except ImportError:
    _DAG_AVAILABLE = False


async def on_dag_list(inst, msg: dict, reply) -> None:
    """列出 DAG_DIR 下所有 .yaml 文件 + 解析后的 name/description/filename."""
    req_id = msg.get('id')
    if not _DAG_AVAILABLE:
        await reply({'type': 'dag_list_result', 'id': req_id, 'dags': []})
        return
    try:
        dags = []
        for yaml_path in sorted(Path(DAG_DIR).glob('*.yaml')):
            try:
                spec = load_dag_yaml_file(yaml_path)
                dags.append({
                    'name': spec.name,
                    'description': spec.description,
                    'filename': yaml_path.stem,
                })
            except Exception as exc:
                dags.append({
                    'name': yaml_path.stem,
                    'description': f'[解析失败] {exc}',
                    'filename': yaml_path.stem,
                })
        await reply({'type': 'dag_list_result', 'id': req_id, 'dags': dags})
    except Exception as exc:
        logger.warning('[bridge] dag_list error: %s', exc)
        await reply({'type': 'dag_list_result', 'id': req_id, 'error': str(exc), 'dags': []})


async def on_dag_spec(inst, msg: dict, reply) -> None:
    """读取指定 DAG 的 spec(name -> DAG_DIR/{name}.yaml)."""
    req_id = msg.get('id')
    dag_name = str(msg.get('dag') or '').strip()
    if not dag_name:
        await reply({'type': 'dag_spec_result', 'id': req_id, 'error': 'dag name is required'})
        return
    if not _DAG_AVAILABLE:
        await reply({'type': 'dag_spec_result', 'id': req_id, 'error': 'dag subsystem not available'})
        return
    try:
        path = Path(DAG_DIR) / f'{dag_name}.yaml'
        spec = load_dag_yaml_file(path)
        await reply({'type': 'dag_spec_result', 'id': req_id, 'spec': dataclasses.asdict(spec)})
    except Exception as exc:
        logger.warning('[bridge] dag_spec error: %s', exc)
        await reply({'type': 'dag_spec_result', 'id': req_id, 'error': str(exc)})


async def on_dag_run(inst, msg: dict, reply) -> None:
    """触发 DAG 运行(submit run_dag + start + wait).事件流靠 WS dag_event 推送."""
    req_id = msg.get('id')
    dag_name = str(msg.get('dag') or '').strip()
    inputs = msg.get('inputs', {})
    if not dag_name:
        await reply({'type': 'dag_run_result', 'id': req_id, 'success': False, 'error': 'dag name is required'})
        return
    if not _DAG_AVAILABLE:
        await reply({'type': 'dag_run_result', 'id': req_id, 'success': False, 'error': 'dag subsystem not available'})
        return
    try:
        inputs_json = json.dumps(inputs, ensure_ascii=False) if inputs else ''
        handle = await inst.submit('run_dag', {'dag': dag_name, 'inputs': inputs_json})
        await handle.start()
        result = await handle.wait()
        await reply({'type': 'dag_run_result', 'id': req_id, 'success': True, 'result': result})
    except Exception as exc:
        logger.warning('[bridge] dag_run error: %s', exc)
        await reply({'type': 'dag_run_result', 'id': req_id, 'success': False, 'error': str(exc)})
