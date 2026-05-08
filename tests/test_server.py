import shutil

import pytest
from fastapi.testclient import TestClient

from agent_ci import __version__
from agent_ci.server import create_app

TEST_API_KEY = "secret-token"
client = TestClient(create_app())


@pytest.fixture
def auth_headers(monkeypatch) -> dict[str, str]:
    monkeypatch.setenv("AGENT_CI_API_KEY", TEST_API_KEY)
    return {"X-API-Key": TEST_API_KEY}


def test_verify_rejects_file_path(auth_headers):
    response = client.post(
        "/verify",
        json={"output_directory": "src/agent_ci/cli.py"},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "directory" in response.json()["detail"].lower()



def test_verify_rejects_directory_outside_workspace(tmp_path, auth_headers):
    response = client.post(
        "/verify",
        json={"output_directory": str(tmp_path)},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "workspace" in response.json()["detail"].lower()



def test_verify_rejects_same_prefix_sibling_outside_workspace(
    monkeypatch, tmp_path, valid_output, auth_headers
):
    workspace = tmp_path / "data"
    workspace.mkdir()

    attacker_root = tmp_path / "data-evil"
    attacker_root.mkdir()
    copied_output = attacker_root / "valid_output"
    shutil.copytree(valid_output, copied_output)

    monkeypatch.setenv("AGENT_CI_ALLOWED_ROOTS", str(workspace))
    scoped_client = TestClient(create_app())

    response = scoped_client.post(
        "/verify",
        json={"output_directory": str(copied_output)},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert "outside the workspace" in response.json()["detail"].lower()



def test_verify_rejects_nonexistent_path_outside_workspace(
    monkeypatch, tmp_path, auth_headers
):
    workspace = tmp_path / "data"
    workspace.mkdir()

    missing_path = tmp_path / "data-evil" / "missing-output"

    monkeypatch.setenv("AGENT_CI_ALLOWED_ROOTS", str(workspace))
    scoped_client = TestClient(create_app())

    response = scoped_client.post(
        "/verify",
        json={"output_directory": str(missing_path)},
        headers=auth_headers,
    )

    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "outside the workspace" in detail
    assert "not found" not in detail
    assert "path is not a directory" not in detail



def test_verify_rejects_invalid_resolved_path(monkeypatch, tmp_path, auth_headers):
    from pathlib import Path

    workspace = tmp_path / "data"
    workspace.mkdir()
    broken_path = workspace / "broken-output"

    original_resolve = Path.resolve

    def broken_resolve(self, *args, **kwargs):
        if self == broken_path:
            raise OSError("sensitive path detail")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setenv("AGENT_CI_ALLOWED_ROOTS", str(workspace))
    monkeypatch.setattr(Path, "resolve", broken_resolve)

    scoped_client = TestClient(create_app())
    response = scoped_client.post(
        "/verify",
        json={"output_directory": str(broken_path)},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid output directory path"
    assert "sensitive path detail" not in response.text



def test_verify_hides_invalid_workspace_path_details(
    monkeypatch, tmp_path, valid_output, auth_headers
):
    from pathlib import Path

    import agent_ci.server as server_module

    broken_workspace = tmp_path / "broken-workspace"
    original_resolve = Path.resolve

    def broken_resolve(self, *args, **kwargs):
        if self == broken_workspace:
            raise OSError("sensitive workspace detail")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(server_module, "_resolve_workspace", lambda config: broken_workspace)
    monkeypatch.setattr(Path, "resolve", broken_resolve)

    scoped_client = TestClient(create_app())
    response = scoped_client.post(
        "/verify",
        json={"output_directory": str(valid_output)},
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid workspace path"
    assert "sensitive workspace detail" not in response.text



def test_verify_hides_config_error_details(monkeypatch, valid_output, auth_headers):
    import agent_ci.server as server_module

    def broken_load_config(*args, **kwargs):
        raise RuntimeError("sensitive config detail")

    monkeypatch.setattr(server_module, "load_config", broken_load_config)

    scoped_client = TestClient(create_app())
    response = scoped_client.post(
        "/verify",
        json={"output_directory": str(valid_output)},
        headers=auth_headers,
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Config error"
    assert "sensitive config detail" not in response.text



def test_verify_uses_create_app_config_path_for_server_mode(
    tmp_path, valid_output, auth_headers
):
    workspace = tmp_path / "data"
    workspace.mkdir()
    copied_output = workspace / "valid_output"
    shutil.copytree(valid_output, copied_output)

    config_path = tmp_path / "server-config.yaml"
    config_path.write_text(
        f"server:\n  allowed_roots:\n    - {workspace}\n",
        encoding="utf-8",
    )

    scoped_client = TestClient(create_app(config_path=str(config_path)))
    response = scoped_client.post(
        "/verify",
        json={"output_directory": str(copied_output)},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["verdict"] in {"PASS", "PASS WITH WARNINGS", "REJECT"}



def test_verify_ignores_request_supplied_config_file(valid_output, auth_headers):
    response = client.post(
        "/verify",
        json={
            "output_directory": str(valid_output),
            "config_file": "/definitely/missing/.agent-ci.yaml",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["verdict"] in {"PASS", "PASS WITH WARNINGS", "REJECT"}


# ── API Key authentication ────────────────────────────────────────



def test_verify_returns_401_without_api_key_when_required(monkeypatch, valid_output):
    monkeypatch.setenv("AGENT_CI_API_KEY", TEST_API_KEY)

    response = client.post(
        "/verify",
        json={"output_directory": str(valid_output)},
    )

    assert response.status_code == 401
    assert "api key" in response.json()["detail"].lower()



def test_verify_returns_401_with_wrong_api_key(monkeypatch, valid_output):
    monkeypatch.setenv("AGENT_CI_API_KEY", TEST_API_KEY)

    response = client.post(
        "/verify",
        json={"output_directory": str(valid_output)},
        headers={"X-API-Key": "wrong-token"},
    )

    assert response.status_code == 401



def test_verify_succeeds_with_correct_api_key(monkeypatch, valid_output):
    monkeypatch.setenv("AGENT_CI_API_KEY", TEST_API_KEY)

    response = client.post(
        "/verify",
        json={"output_directory": str(valid_output)},
        headers={"X-API-Key": TEST_API_KEY},
    )

    assert response.status_code == 200
    assert response.json()["verdict"] in {"PASS", "PASS WITH WARNINGS", "REJECT"}



def test_verify_returns_401_without_api_key_when_not_configured(
    monkeypatch, valid_output
):
    monkeypatch.delenv("AGENT_CI_API_KEY", raising=False)

    response = client.post(
        "/verify",
        json={"output_directory": str(valid_output)},
    )

    assert response.status_code == 401
    assert "api key" in response.json()["detail"].lower()


# ── Health check ──────────────────────────────────────────────────



def test_health_endpoint_no_auth_required():
    """Health check should always be accessible without auth."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"



def test_health_check_includes_version():
    response = client.get("/health")

    assert response.json()["version"] == __version__



def test_health_check_includes_checkers_status():
    response = client.get("/health")

    checkers = response.json()["checkers"]
    assert isinstance(checkers, dict)
    assert "schema" in checkers
    assert "fact" in checkers
    assert "diff" in checkers
    assert checkers["schema"] == "healthy"
    assert checkers["fact"] == "healthy"
    assert checkers["diff"] == "healthy"



def test_health_check_hides_checker_exception_details(monkeypatch):
    from agent_ci.checkers import schema as schema_module

    class BrokenSchemaChecker:
        def __init__(self):
            raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr(schema_module, "SchemaChecker", BrokenSchemaChecker)

    scoped_client = TestClient(create_app())
    response = scoped_client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["checkers"]["schema"] == "unhealthy"
    assert "sensitive internal detail" not in response.text



def test_health_check_marks_import_failure_degraded(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def broken_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "agent_ci.checkers.schema":
            raise ImportError("sensitive import detail")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", broken_import)

    scoped_client = TestClient(create_app())
    response = scoped_client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["checkers"] == "unavailable"
    assert "sensitive import detail" not in response.text



def test_health_check_hides_non_import_checker_import_failure(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def broken_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "agent_ci.checkers.schema":
            raise RuntimeError("sensitive runtime import detail")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", broken_import)

    scoped_client = TestClient(create_app())
    response = scoped_client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["checkers"] == "unavailable"
    assert "sensitive runtime import detail" not in response.text


# ── Rate limiting ─────────────────────────────────────────────────



def test_rate_limit_returns_429_after_exceeding_limit(
    monkeypatch, valid_output, auth_headers
):
    monkeypatch.setenv("AGENT_CI_RATE_LIMIT", "10")
    monkeypatch.setenv("AGENT_CI_RATE_WINDOW", "60")

    rate_client = TestClient(create_app())

    statuses: list[int] = []
    for _ in range(12):
        response = rate_client.post(
            "/verify",
            json={"output_directory": str(valid_output)},
            headers=auth_headers,
        )
        statuses.append(response.status_code)

    assert 429 in statuses[10:]



def test_rate_limit_ok_under_limit(monkeypatch, valid_output, auth_headers):
    monkeypatch.setenv("AGENT_CI_RATE_LIMIT", "100")

    rate_client = TestClient(create_app())

    for _ in range(5):
        response = rate_client.post(
            "/verify",
            json={"output_directory": str(valid_output)},
            headers=auth_headers,
        )
        assert response.status_code != 429



def test_unauthenticated_request_does_not_consume_rate_limit(
    monkeypatch, valid_output, auth_headers
):
    monkeypatch.setenv("AGENT_CI_RATE_LIMIT", "1")
    monkeypatch.setenv("AGENT_CI_RATE_WINDOW", "60")

    rate_client = TestClient(create_app())

    unauthenticated_first = rate_client.post(
        "/verify",
        json={"output_directory": str(valid_output)},
    )
    unauthenticated_second = rate_client.post(
        "/verify",
        json={"output_directory": str(valid_output)},
    )
    authenticated = rate_client.post(
        "/verify",
        json={"output_directory": str(valid_output)},
        headers=auth_headers,
    )

    assert unauthenticated_first.status_code == 401
    assert unauthenticated_second.status_code == 429
    assert authenticated.status_code == 200



def test_rate_limit_partitions_authenticated_buckets_by_api_key(
    monkeypatch, valid_output
):
    monkeypatch.setenv("AGENT_CI_RATE_LIMIT", "1")
    monkeypatch.setenv("AGENT_CI_RATE_WINDOW", "60")

    rate_client = TestClient(create_app())

    monkeypatch.setenv("AGENT_CI_API_KEY", "key-one")
    first_key_one = rate_client.post(
        "/verify",
        json={"output_directory": str(valid_output)},
        headers={"X-API-Key": "key-one"},
    )

    monkeypatch.setenv("AGENT_CI_API_KEY", "key-two")
    first_key_two = rate_client.post(
        "/verify",
        json={"output_directory": str(valid_output)},
        headers={"X-API-Key": "key-two"},
    )

    monkeypatch.setenv("AGENT_CI_API_KEY", "key-one")
    second_key_one = rate_client.post(
        "/verify",
        json={"output_directory": str(valid_output)},
        headers={"X-API-Key": "key-one"},
    )

    assert first_key_one.status_code == 200
    assert first_key_two.status_code == 200
    assert second_key_one.status_code == 429



def test_health_endpoint_not_rate_limited(monkeypatch):
    """Health check should never be rate limited."""
    monkeypatch.setenv("AGENT_CI_RATE_LIMIT", "1")
    monkeypatch.setenv("AGENT_CI_RATE_WINDOW", "60")

    rate_client = TestClient(create_app())

    for _ in range(3):
        response = rate_client.get("/health")
        assert response.status_code == 200



def test_create_app_falls_back_on_invalid_rate_limit_env(monkeypatch):
    monkeypatch.setenv("AGENT_CI_RATE_LIMIT", "not-a-number")
    monkeypatch.setenv("AGENT_CI_RATE_WINDOW", "also-bad")

    rate_client = TestClient(create_app())
    response = rate_client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}
