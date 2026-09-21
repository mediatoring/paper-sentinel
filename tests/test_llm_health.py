from app.services import llm_health


def test_provider_detection():
    assert llm_health.provider_for("http://127.0.0.1:1234/v1") == "lmstudio"
    assert llm_health.provider_for("http://host.docker.internal:11434/v1") == "ollama"
    assert llm_health.provider_for("http://ollama.local:8080/v1") == "ollama"
    assert llm_health.provider_for("https://api.example.com/v1") == "generic"
    assert llm_health.provider_for("") == "generic"


def test_hints_contain_runnable_commands():
    h = llm_health.hints("lmstudio", "http://127.0.0.1:1234/v1", "openai/gpt-oss-20b", "text-embedding-nomic-embed-text-v1.5")
    assert h["start"] == "lms server start --port 1234"
    assert h["load_chat"] == "lms load openai/gpt-oss-20b -y"
    assert "nomic" in h["load_embedding"]
    o = llm_health.hints("ollama", "http://127.0.0.1:11434/v1", "llama3.1", None)
    assert o["start"] == "ollama serve" and o["load_chat"] == "ollama pull llama3.1"
    assert "nomic-embed-text" in o["load_embedding"]


def test_probe_reports_unreachable_server():
    settings = {"llm_enabled": True, "llm_base_url": "http://127.0.0.1:9/v1", "llm_model": "m", "embedding_model": ""}
    result = llm_health.probe(settings, force=True)
    assert result["reachable"] is False
    assert result["provider"] == "generic"
    assert "127.0.0.1:9" in result["error"]
    assert result["hints"]["start"]
    assert result["chat_loaded"] is None


def test_probe_reads_lmstudio_states(monkeypatch):
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "chat-x"}, {"id": "text-embedding-y"}, {"id": "other"}]})
        if request.url.path == "/api/v0/models":
            return httpx.Response(200, json={"data": [
                {"id": "chat-x", "state": "loaded"}, {"id": "text-embedding-y", "state": "not-loaded"}, {"id": "other", "state": "not-loaded"},
            ]})
        return httpx.Response(404)

    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    settings = {"llm_enabled": True, "llm_base_url": "http://127.0.0.1:1234/v1", "llm_model": "chat-x", "embedding_model": ""}
    result = llm_health.probe(settings, force=True)
    assert result["reachable"] and result["provider"] == "lmstudio"
    assert result["chat_loaded"] is True and result["chat_available"] is True
    assert result["embedding_model"] == "text-embedding-y" and result["embedding_loaded"] is False
    assert result["loaded_models"] == ["chat-x"]
    assert result["hints"]["load_embedding"] == "lms load text-embedding-y -y"
