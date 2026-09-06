"""Symbol search must treat % and _ as literal text, not LIKE wildcards (PROMPT_7 D3).

Without escaping, ``?search=%`` matched every symbol and ``_`` matched any
single character, so a user typing one wildcard character got the whole
catalog instead of a literal match.
"""

from fastapi.testclient import TestClient

from src.aac_app.models import Symbol
from src.api.main import app

client = TestClient(app)


def _seed(session):
    session.add_all(
        [
            Symbol(label="dog", description="barks", keywords="animal pet"),
            Symbol(label="d_g", description="contains underscore", keywords=""),
            Symbol(label="100%_sure", description="has both wildcards", keywords="a%b"),
        ]
    )
    session.commit()


def _search(token, term):
    response = client.get(
        "/api/boards/symbols",
        params={"search": term},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return {item["label"] for item in response.json()}


def test_literal_percent_does_not_match_everything(setup_test_db, test_db_session, admin_token):
    _seed(test_db_session)

    # Red without the fix: an unescaped "%" matched all three symbols.
    assert _search(admin_token, "%") == {"100%_sure"}


def test_literal_underscore_matches_only_itself(setup_test_db, test_db_session, admin_token):
    _seed(test_db_session)

    # Red without the fix: an unescaped "_" acted like SQL's "any char",
    # so it also pulled in "dog" ("d?g").
    assert _search(admin_token, "_") == {"d_g", "100%_sure"}


def test_keywords_filter_escapes_wildcards(setup_test_db, test_db_session, admin_token):
    _seed(test_db_session)

    response = client.get(
        "/api/boards/symbols",
        params={"keywords": "a%"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    # "animal pet" has no literal %; without escaping "a%" matched every
    # keywords column containing "a" (dog, d_g) plus the % row.
    assert {item["label"] for item in response.json()} == {"100%_sure"}
