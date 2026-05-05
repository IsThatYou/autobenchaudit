from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any


class AgentCliError(RuntimeError):
    """Raised when the configured agent CLI is missing or fails."""


_DEBUG_COMMAND_LOCK = Lock()


@dataclass(slots=True)
class AgentRequest:
    agent_cli: str
    model: str | None = None
    add_dirs: list[str] = field(default_factory=list)
    api_key_env: str | None = None


def build_agent_request(
    agent_cli: str | None,
    model: str | None,
    add_dirs: list[str] | None = None,
    api_key_env: str | None = None,
) -> AgentRequest:
    if not agent_cli:
        raise AgentCliError("agent_cli must be configured; fallback generation has been removed")
    if agent_cli not in {"claude", "cursor", "codex"}:
        raise AgentCliError(f"unsupported agent_cli: {agent_cli}")
    return AgentRequest(agent_cli=agent_cli, model=model, add_dirs=list(add_dirs or []), api_key_env=api_key_env)


def _build_env_override(request: AgentRequest) -> dict[str, str] | None:
    if not request.api_key_env:
        return None
    api_key = os.environ.get(request.api_key_env)
    if not api_key:
        raise AgentCliError(f"api_key_env '{request.api_key_env}' is set in config but the environment variable is empty or missing")
    # codex exec uses CODEX_API_KEY (not OPENAI_API_KEY) for per-invocation API key auth
    if request.agent_cli == "codex":
        return {"CODEX_API_KEY": api_key}
    return {"OPENAI_API_KEY": api_key}


def invoke_text(
    request: AgentRequest,
    prompt: str,
    timeout: int | None = None,
    conversation_log_path: Path | None = None,
) -> str:
    command, input_text = _text_command(request, prompt)
    raw = _run_command(
        request.agent_cli,
        command,
        input_text=input_text,
        timeout=timeout,
        prompt_text=prompt,
        prompt_kind="text",
        env_override=_build_env_override(request),
        conversation_log_path=conversation_log_path,
    )
    return _extract_text_output(request.agent_cli, raw)


def invoke_structured(request: AgentRequest, prompt: str, json_schema: dict[str, Any], timeout: int | None = None, conversation_log_path: Path | None = None) -> str:
    env_override = _build_env_override(request)

    if request.agent_cli == "cursor":
        command = _cursor_base_command(request)
        command.extend(["--output-format", "json"])
        schema_prompt = (
            f"{prompt}\n\nReturn only a JSON object that matches this schema:\n"
            f"{json.dumps(json_schema, indent=2)}"
        )
        return _run_command(
            request.agent_cli,
            command,
            input_text=schema_prompt,
            timeout=timeout,
            prompt_text=schema_prompt,
            prompt_kind="structured",
            env_override=env_override,
            conversation_log_path=conversation_log_path,
        )

    if request.agent_cli == "claude":
        command = _claude_base_command(request)
        command.extend(["--json-schema", json.dumps(json_schema)])
        command.extend(["--output-format", "stream-json"])
        command.extend(["--allowedTools", "Bash,Read,Glob,Grep,WebFetch,WebSearch"])
        raw = _run_command(
            request.agent_cli,
            command,
            input_text=prompt,
            timeout=timeout,
            prompt_text=prompt,
            prompt_kind="structured",
            env_override=env_override,
            conversation_log_path=conversation_log_path,
        )
        return _extract_structured_output(request.agent_cli, raw)

    with tempfile.TemporaryDirectory(prefix="bench_audit_schema_") as tmpdir:
        schema_path = Path(tmpdir) / "output_schema.json"
        schema_path.write_text(json.dumps(json_schema, indent=2) + "\n")
        if request.agent_cli == "codex":
            command = _codex_base_command(request)
            command.append("--json")
            command.extend([prompt, "--output-schema", str(schema_path)])
            raw = _run_command(
                request.agent_cli,
                command,
                timeout=timeout,
                prompt_text=prompt,
                prompt_kind="structured",
                env_override=env_override,
                conversation_log_path=conversation_log_path,
            )
            return _extract_structured_output(request.agent_cli, raw)
        raise AgentCliError(f"unsupported structured-output agent_cli: {request.agent_cli}")


def _run_command(
    agent_cli: str,
    command: list[str],
    input_text: str | None = None,
    timeout: int | None = None,
    prompt_text: str | None = None,
    prompt_kind: str | None = None,
    env_override: dict[str, str] | None = None,
    conversation_log_path: Path | None = None,
) -> str:
    binary = command[0]
    _log_debug_request(
        agent_cli,
        command,
        input_text=input_text,
        timeout=timeout,
        prompt_text=prompt_text,
        prompt_kind=prompt_kind,
    )
    if shutil.which(binary) is None:
        raise AgentCliError(f"configured agent CLI binary is not installed or not on PATH: {binary}")
    run_env = None
    if env_override:
        run_env = {**os.environ, **env_override}
    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=run_env,
        )
    except FileNotFoundError as exc:
        raise AgentCliError(f"configured agent CLI binary is not installed or not on PATH: {binary}") from exc
    try:
        stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        # The process may have finished its real work but hung due to
        # background child processes keeping stdout open.  Kill the tree
        # and drain whatever was already buffered.
        proc.kill()
        stdout, stderr = proc.communicate()
        stdout = (stdout or "").strip()
        if stdout:
            print(f"[bench-audit] {agent_cli} timed out after {timeout}s but produced output; recovering", file=sys.stderr)
        else:
            raise AgentCliError(f"{agent_cli} timed out after {timeout}s")
    else:
        stdout = (stdout or "").strip()
        stderr = (stderr or "").strip()
        if proc.returncode != 0:
            detail = stderr or stdout or f"exit code {proc.returncode}"
            raise AgentCliError(f"{agent_cli} failed while generating output: {detail}")
    if not stdout:
        raise AgentCliError(f"{agent_cli} returned empty output")
    if conversation_log_path is not None:
        conversation_log_path.parent.mkdir(parents=True, exist_ok=True)
        conversation_log_path.write_text(stdout)
    return stdout


def _log_debug_request(
    agent_cli: str,
    command: list[str],
    input_text: str | None = None,
    timeout: int | None = None,
    prompt_text: str | None = None,
    prompt_kind: str | None = None,
) -> None:
    if os.environ.get("BENCH_AUDIT_DEBUG_PROMPTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    with _DEBUG_COMMAND_LOCK:
        if prompt_text is not None:
            header = f"=== BENCH_AUDIT_DEBUG_PROMPT agent={agent_cli}"
            footer = f"=== END BENCH_AUDIT_DEBUG_PROMPT agent={agent_cli}"
            if prompt_kind:
                header += f" kind={prompt_kind}"
                footer += f" kind={prompt_kind}"
            print(f"{header} ===", file=sys.stderr)
            print(prompt_text, file=sys.stderr)
            print(f"{footer} ===", file=sys.stderr)
        print(f"=== BENCH_AUDIT_DEBUG_COMMAND agent={agent_cli} ===", file=sys.stderr)
        print(shlex.join(command), file=sys.stderr)
        if timeout is not None:
            print(f"timeout={timeout}s", file=sys.stderr)
        if input_text is not None:
            print("stdin=provided", file=sys.stderr)
        print(f"=== END BENCH_AUDIT_DEBUG_COMMAND agent={agent_cli} ===", file=sys.stderr, flush=True)


def _extract_structured_output(agent_cli: str, raw: str) -> str:
    if agent_cli == "codex":
        return _extract_codex_last_message(raw)
    if agent_cli == "claude":
        extracted = _extract_claude_stream_result(raw, expect_structured=True)
        if extracted is not None:
            return extracted
    try:
        wrapper = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(wrapper, dict) and "structured_output" in wrapper:
        return json.dumps(wrapper["structured_output"])
    return raw


def _extract_text_output(agent_cli: str, raw: str) -> str:
    if agent_cli == "codex":
        return _extract_codex_last_message(raw)
    if agent_cli == "claude":
        extracted = _extract_claude_stream_result(raw, expect_structured=False)
        if extracted is not None:
            return extracted
    return raw


def _iter_jsonl_objects(raw: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            objects.append(payload)
    return objects


def _extract_codex_last_message(raw: str) -> str:
    task_complete: str | None = None
    final_agent_message: str | None = None
    assistant_output: str | None = None
    for item in _iter_jsonl_objects(raw):
        item_type = item.get("type")
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        if item_type == "event_msg":
            payload_type = payload.get("type")
            if payload_type == "task_complete":
                last_message = payload.get("last_agent_message")
                if isinstance(last_message, str) and last_message.strip():
                    task_complete = last_message.strip()
            elif payload_type == "agent_message" and payload.get("phase") == "final_answer":
                message = payload.get("message")
                if isinstance(message, str) and message.strip():
                    final_agent_message = message.strip()
        elif item_type == "response_item" and payload.get("type") == "message" and payload.get("role") == "assistant":
            content = payload.get("content")
            if isinstance(content, list):
                texts = [
                    part.get("text", "").strip()
                    for part in content
                    if isinstance(part, dict) and isinstance(part.get("text"), str) and part.get("text", "").strip()
                ]
                if texts:
                    assistant_output = "\n".join(texts)
    if task_complete is not None:
        return task_complete
    if final_agent_message is not None:
        return final_agent_message
    if assistant_output is not None:
        return assistant_output
    stripped = raw.strip()
    if "\n" not in stripped:
        return stripped
    raise AgentCliError("codex returned JSONL output without a final agent message")


def _extract_claude_stream_result(raw: str, expect_structured: bool) -> str | None:
    result_value: str | None = None
    assistant_text: str | None = None
    for item in _iter_jsonl_objects(raw):
        item_type = item.get("type")
        if item_type == "result":
            if expect_structured:
                structured = item.get("structured_output")
                if structured is not None:
                    return json.dumps(structured)
            result_text = item.get("result")
            if isinstance(result_text, str) and result_text.strip():
                result_value = result_text.strip()
        elif item_type == "assistant":
            message = item.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, list):
                    texts = [
                        part.get("text", "").strip()
                        for part in content
                        if isinstance(part, dict) and isinstance(part.get("text"), str) and part.get("text", "").strip()
                    ]
                    if texts:
                        assistant_text = "\n".join(texts)
    if result_value is not None:
        return result_value
    if assistant_text is not None:
        return assistant_text
    return None


def _text_command(request: AgentRequest, prompt: str) -> tuple[list[str], str | None]:
    if request.agent_cli == "claude":
        command = _claude_base_command(request)
        command.extend(["--output-format", "stream-json"])
        return (command, prompt)
    if request.agent_cli == "cursor":
        return (_cursor_base_command(request), prompt)
    if request.agent_cli == "codex":
        command = _codex_base_command(request)
        command.append("--json")
        command.append("-")
        return (command, prompt)
    raise AgentCliError(f"unsupported agent_cli: {request.agent_cli}")


def _claude_base_command(request: AgentRequest) -> list[str]:
    command = ["claude", "-p", "--verbose", "--dangerously-skip-permissions"]
    if request.model:
        command.extend(["--model", request.model])
    for directory in request.add_dirs:
        command.extend(["--add-dir", directory])
    return command


def _cursor_base_command(request: AgentRequest) -> list[str]:
    return ["cursor-agent", "-p"]


def _codex_base_command(request: AgentRequest) -> list[str]:
    command = ["codex", "exec", "--yolo"]
    if request.model:
        command.extend(["--model", request.model])
    for directory in request.add_dirs:
        command.extend(["--add-dir", directory])
    return command
