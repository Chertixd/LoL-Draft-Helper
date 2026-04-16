"""
Unit tests for GET /api/draft/active endpoint (UPD-04, D-12).
Tests the endpoint that the Tauri updater uses to defer installAndRelaunch()
when a champion-select session is in progress.
"""
import json
import pytest

import backend as backend_module
from backend import app


@pytest.fixture
def client():
    """Flask test client."""
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def reset_draft_state():
    """Reset _last_draft_state before each test."""
    backend_module._last_draft_state = None
    yield
    backend_module._last_draft_state = None


def test_draft_active_no_session(client):
    """When no draft session is active, returns active: false."""
    resp = client.get('/api/draft/active')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['active'] is False


def test_draft_active_with_session(client):
    """When a draft session is active with timer phase, returns active: true and phase."""
    backend_module._last_draft_state = {
        'session': {
            'timer': {'phase': 'BAN_SELECTION'}
        }
    }
    resp = client.get('/api/draft/active')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['active'] is True
    assert data['phase'] == 'BAN_SELECTION'


def test_draft_active_no_timer_phase(client):
    """When draft state exists but has no session/timer/phase, returns UNKNOWN."""
    backend_module._last_draft_state = {'some_key': 'some_value'}
    resp = client.get('/api/draft/active')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['active'] is True
    assert data['phase'] == 'UNKNOWN'
