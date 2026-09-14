import os
import tempfile
_test_dir = tempfile.TemporaryDirectory(prefix="zhishu-api-")
os.environ["DATABASE_URL"] = "sqlite:///" + _test_dir.name.replace("\\", "/") + "/test.db"
from fastapi.testclient import TestClient
from app.main import app
import atexit
from app.db import engine
atexit.register(engine.dispose)

def test_workspace_is_isolated_and_stale_write_is_409():
    with TestClient(app) as first, TestClient(app) as second:
        assert first.get("/api/workspace").status_code == 200
        assert second.get("/api/workspace").status_code == 200
        created=first.post("/api/workspace/actions",json={"type":"create","title":"private","revision":0})
        assert created.status_code == 200
        assert second.get("/api/workspace").json()["state"]["sessions"] == []
        stale=first.post("/api/workspace/actions",json={"type":"create","title":"stale","revision":0})
        assert stale.status_code == 409 and "requestId" in stale.json()

def test_invalid_action_is_400_and_unconfigured_chat_is_503():
    with TestClient(app) as client:
        assert client.post("/api/workspace/actions",json={"type":"create","revision":0}).status_code == 400
        workspace=client.get("/api/workspace").json()
        created=client.post("/api/workspace/actions",json={"type":"create","title":"private","revision":workspace["revision"]}).json()
        branch=created["active"]
        pending=client.post("/api/workspace/actions",json={"type":"send","branchId":branch,"text":"hello","revision":created["revision"]})
        assert client.post("/api/ai/chat",json={"branchId":branch,"revision":pending.json()["revision"]}).status_code == 503


def test_paged_routes_compact_defaults_owner_and_cursor_validation():
    with TestClient(app) as client, TestClient(app) as other:
        view = client.get('/api/workspace/view').json()
        result = client.post('/api/workspace/actions', json={"type": "create", "title": "paged", "revision": view['revision']}).json()
        assert 'state' not in result and len(str(result)) < 1000
        bid = result['active']
        assert client.get(f'/api/branches/{bid}').status_code == 200
        assert other.get(f'/api/branches/{bid}').status_code == 404
        assert other.get(f'/api/branches/{bid}/entries').status_code == 404
        for query in ['cursor=abc', 'cursor=-2', 'limit=101', 'limit=0', 'cursor=true']:
            assert client.get(f'/api/branches/{bid}/entries?{query}').status_code == 400
        assert client.get(f'/api/branches/{bid}/entries?anchor=missing').status_code == 404
        assert client.get('/api/topics?search=paged').json()['items'][0]['title'] == 'paged'


def test_model_form_validation_and_connection_key_scope(monkeypatch):
    # This tests form/key scope, not live provider DNS availability.
    import socket
    monkeypatch.setattr('app.services.socket.getaddrinfo', lambda host, port: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))
    ])
    with TestClient(app) as client:
        body = dict(baseUrl='https://api.openai.com/v1', model='model', apiKey='secret', provider='openai')
        for invalid in [dict(model='  '), dict(apiKey='  '), dict(baseUrl='https://user:pass@example.com'), dict(baseUrl='https://api.openai.com/v1?q=secret'), dict(maxTokens=None), dict(maxTokens=True), dict(timeoutMs=1.5)]:
            assert client.post('/api/ai/config', json=body | invalid).status_code == 400
        assert client.post('/api/ai/config', json=body).status_code == 200
        assert client.post('/api/ai/config', json=body | dict(apiKey='', model='other')).status_code == 200
        for change in [dict(provider='anthropic'), dict(baseUrl='https://api.anthropic.com')]:
            assert client.post('/api/ai/config', json=body | dict(apiKey='') | change).status_code == 400
        public = client.get('/api/ai/config').json()
        assert public['model'] == 'other' and 'secret' not in str(public)


def test_deepseek_fake_ip_save_and_revalidation(monkeypatch):
    import socket
    from app import services
    monkeypatch.setattr(services.settings, 'ai_fake_ip_hosts', 'api.deepseek.com')
    monkeypatch.setattr(services.settings, 'ai_allow_private_hosts', False)
    monkeypatch.setattr(services.settings, 'ai_allowed_hosts', '')
    addresses = ['198.18.0.212', 'fdfe:dcba:9876::3f']
    monkeypatch.setattr(services.socket, 'getaddrinfo', lambda *_: [
        (socket.AF_INET6 if ':' in address else socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 443))
        for address in addresses
    ])
    async def complete(request):
        assert request.base_url == 'https://api.deepseek.com/v1'
        assert request.model == 'deepseek-flash'
        return '连接成功'
    monkeypatch.setattr('app.providers.complete', complete)
    with TestClient(app) as client:
        body = dict(baseUrl='https://api.deepseek.com/v1', model='deepseek-flash', apiKey='fake-test-key', provider='openai')
        assert client.post('/api/ai/config', json=body).status_code == 200
        assert client.post('/api/ai/config/test').status_code == 200
        addresses[:] = ['127.0.0.1']
        blocked = client.post('/api/ai/config/test')
        assert blocked.status_code == 400 and 'requestId' in blocked.json()
        assert client.get('/api/ai/config').json()['model'] == 'deepseek-flash'


def test_graph_http_strict_owner_idempotency_and_recovery():
    with TestClient(app) as client, TestClient(app) as other:
        view = client.get('/api/workspace/view').json()
        created = client.post('/api/workspace/actions', json={
            'type': 'create', 'title': 'native graph', 'revision': view['revision']}).json()
        bid = created['active']
        graph = client.get('/api/graph', params={'focus': bid}).json()
        node = next(n for n in graph['nodes'] if n['id'] == bid)
        assert other.get('/api/graph', params={'focus': bid}).status_code == 404
        for invalid in [{'extra': 1}, {'x': 1_000_001}, {'version': True}]:
            assert client.post('/api/graph/positions', json={
                'branchId': bid, 'x': 10, 'y': 20, 'version': 0, **invalid}).status_code == 400
        assert client.post('/api/graph/contacts', json={'source': bid, 'targets': [bid]}).status_code == 400
        assert client.post('/api/graph/contacts', json={'source': bid, 'targets': ['x'] * 21}).status_code == 400
        payload = {'operationId': 'http-remove', 'targets': [{'id': bid, 'revision': node['revision']}]}
        result = client.post('/api/graph/removals', json=payload)
        assert result.status_code == 200
        assert client.post('/api/graph/removals', json=payload).json()['revision'] == result.json()['revision']
        assert other.get('/api/graph/removals/http-remove').status_code == 404
        assert other.post('/api/graph/removals/http-remove/restore', json={}).status_code == 404
        assert client.get('/api/graph/removals').json()['count'] == 1
        assert client.post('/api/graph/removals/http-remove/restore', json={}).status_code == 200
        assert client.get('/api/branches/' + bid).status_code == 200
