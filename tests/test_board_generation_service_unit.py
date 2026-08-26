from unittest.mock import AsyncMock

import pytest

from src.aac_app.providers.ollama_provider import OllamaProvider
from src.aac_app.services.board_generation_service import BoardGenerationService


@pytest.fixture
def mock_llm_provider():
    return AsyncMock(spec=OllamaProvider)


@pytest.fixture
def service(mock_llm_provider):
    return BoardGenerationService(mock_llm_provider)


@pytest.mark.anyio
async def test_generate_board_items_valid_json(service, mock_llm_provider):
    mock_llm_provider.generate.return_value = """
    [
        {"label": "Yes", "symbol_key": "check_mark", "color": "#E8F5E9"},
        {"label": "No", "symbol_key": "cross_mark", "color": "#FFEBEE"}
    ]
    """

    items = await service.generate_board_items(topic="Test", item_count=2)

    assert [item["label"] for item in items] == ["Yes", "No"]


@pytest.mark.anyio
async def test_generate_board_items_with_markdown_blocks(service, mock_llm_provider):
    mock_llm_provider.generate.return_value = """
    Here is the JSON:
    ```json
    [
        {"label": "Eat", "symbol_key": "eat", "color": "#FFFFFF"}
    ]
    ```
    """

    items = await service.generate_board_items(topic="Test", item_count=1)

    assert items[0]["label"] == "Eat"


@pytest.mark.anyio
async def test_generate_board_items_empty_response_raises_error(service, mock_llm_provider):
    mock_llm_provider.generate.return_value = ""

    with pytest.raises(ValueError, match="AI response was not valid JSON"):
        await service.generate_board_items(topic="Test")


@pytest.mark.anyio
async def test_generate_board_items_invalid_content_raises_error(service, mock_llm_provider):
    mock_llm_provider.generate.return_value = " * - "

    with pytest.raises(ValueError, match="AI response was not valid JSON"):
        await service.generate_board_items(topic="Test")


@pytest.mark.anyio
async def test_generate_board_items_provider_exception_propagates(service, mock_llm_provider):
    mock_llm_provider.generate.side_effect = Exception("API Error")

    with pytest.raises(Exception, match="API Error"):
        await service.generate_board_items(topic="Test")


@pytest.mark.anyio
async def test_generate_board_items_rejects_incomplete_item_count(service, mock_llm_provider):
    mock_llm_provider.generate.return_value = """
    [{"label": "Item 1", "symbol_key": "item_1", "color": "#FFFFFF"}]
    """

    with pytest.raises(ValueError, match="expected 3"):
        await service.generate_board_items(topic="Test", item_count=3)
    assert mock_llm_provider.generate.call_count == 1
