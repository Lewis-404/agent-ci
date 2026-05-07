from fastapi.testclient import TestClient

from agent_ci.server import create_app

client = TestClient(create_app())


def test_verify_rejects_file_path():
    response = client.post("/verify", json={"output_directory": "src/agent_ci/cli.py"})

    assert response.status_code == 400
    assert "directory" in response.json()["detail"].lower()


def test_verify_rejects_directory_outside_workspace(tmp_path):
    response = client.post("/verify", json={"output_directory": str(tmp_path)})

    assert response.status_code == 400
    assert "workspace" in response.json()["detail"].lower()


def test_verify_ignores_request_supplied_config_file(valid_output):
    response = client.post(
        "/verify",
        json={
            "output_directory": str(valid_output),
            "config_file": "/definitely/missing/.agent-ci.yaml",
        },
    )

    assert response.status_code == 200
    assert response.json()["verdict"] in {"PASS", "PASS WITH WARNINGS", "REJECT"}
