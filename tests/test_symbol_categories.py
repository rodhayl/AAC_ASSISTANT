from fastapi.testclient import TestClient

from src.aac_app.models import Symbol
from src.api.main import app

client = TestClient(app)


def test_symbol_categories_returns_distinct_sorted_values(
    setup_test_db, test_db_session, admin_token
):
    test_db_session.add_all(
        [
            Symbol(label="Zebra", category="zoo"),
            Symbol(label="Apple", category="food"),
            Symbol(label="Banana", category="food"),
        ]
    )
    test_db_session.commit()

    response = client.get(
        "/api/boards/symbols/categories",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json() == ["food", "zoo"]
