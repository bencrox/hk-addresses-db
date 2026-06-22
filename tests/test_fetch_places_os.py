import json

import pytest

from bin import export_places_os as fps


def test_area_id_for_relation():
    assert fps.area_id_for_relation(1) == 3600000001
    assert fps.area_id_for_relation(913110) == 3600000000 + 913110


def test_build_overpass_query_contains_filters():
    aid = fps.area_id_for_relation(913110)
    types = ["place", "building", "railway=station"]
    q = fps.build_overpass_query(aid, types)
    assert f"area({aid})->.a" in q
    # ensure filters present
    assert '["place"]' in q
    assert '["building"]' in q
    assert '["railway"="station"]' in q


def test_fetch_overpass_posts_and_parses(monkeypatch):
    placeholder = {"elements": [{"type": "node", "id": 1}]}

    class DummyResp:
        def raise_for_status(self):
            return None

        def json(self):
            return placeholder

    called = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        called["url"] = url
        called["data"] = data
        called["headers"] = headers
        called["timeout"] = timeout
        return DummyResp()

    monkeypatch.setattr("requests.post", fake_post)

    q = "[out:json];\nnode(3600000000+913110)[place];\nout;\n"
    res = fps.fetch_overpass(
        "https://example.com/api", q, user_agent="u/1.0", timeout=5
    )
    assert res == placeholder
    assert called["url"] == "https://example.com/api"
    assert isinstance(called["data"], (bytes, bytearray))
    assert called["timeout"] == 5
