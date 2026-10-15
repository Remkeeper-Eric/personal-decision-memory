import json
import threading
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from decision_memory.models import render_record
from decision_memory.review import create_server


@pytest.fixture
def review(store):
    server = create_server(store)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield server
    server.shutdown()
    server.server_close()
    worker.join(2)


def request(url, data=None, origin=None):
    headers = {}
    if origin:
        headers['Origin'] = origin
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(url, data=json.dumps(data).encode() if data is not None else None, headers=headers)
    with urlopen(req, timeout=5) as response:
        return json.load(response)


def test_review_without_confirmation_cannot_publish(store, record, review):
    relative = store.stage(record)
    view = request(review.review_url + 'api/draft?path=' + quote(relative))
    with pytest.raises(HTTPError) as err:
        request(review.review_url + 'api/publish', {'review_token': view['review_token']})
    assert err.value.code == 400
    assert store.doctor()['active_count'] == 0
    result = request(review.review_url + 'api/publish',
                     {'review_token': view['review_token'], 'confirmed': True})
    assert result['version'] == 1


def test_review_changed_after_display_cannot_publish(store, record, review):
    relative = store.stage(record)
    view = request(review.review_url + 'api/draft?path=' + quote(relative))
    (store.root / relative).write_bytes(render_record(record.model_copy(update={'action': '显示后改动'})))
    with pytest.raises(HTTPError) as err:
        request(review.review_url + 'api/publish',
                {'review_token': view['review_token'], 'confirmed': True})
    assert err.value.code == 400
    assert store.doctor()['active_count'] == 0


def test_cross_origin_and_wrong_capability_rejected(review):
    with pytest.raises(HTTPError) as err:
        request(review.review_url + 'api/list', origin='https://evil.example')
    assert err.value.code == 403
    with pytest.raises(HTTPError):
        request(f'http://127.0.0.1:{review.server_port}/review/wrong/api/list')


def test_user_revoke_uses_displayed_version(store, record, review):
    relative = store.stage(record)
    view = request(review.review_url + 'api/draft?path=' + quote(relative))
    request(review.review_url + 'api/publish', {'review_token': view['review_token'], 'confirmed': True})
    official = request(review.review_url + 'api/record?id=' + record.id)
    request(review.review_url + 'api/revoke', {'review_token': official['review_token'], 'confirmed': True})
    assert not store.search('维护')['results']


def test_identity_matches_only_this_vault(store, review):
    import os
    identity = request(review.review_url + 'api/identity')
    assert identity == {'pid': os.getpid(), 'vault': str(store.root)}


def test_review_html_exposes_no_automatic_approval(review):
    with urlopen(review.review_url, timeout=5) as response:
        html = response.read().decode('utf-8')
        assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
    assert 'id="submit"' in html and 'disabled' in html
    assert 'text.textContent=value' in html  # untrusted note text is not interpreted as markup
