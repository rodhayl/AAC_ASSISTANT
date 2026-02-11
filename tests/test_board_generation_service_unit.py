import pytest
from unittest.mock import AsyncMock, Mock
from src.aac_app.services.board_generation_service import BoardGenerationService
from src.aac_app.providers.ollama_provider import OllamaProvider

@pytest.fixture
def mock_llm_provider():
    return AsyncMock(spec=OllamaProvider)

@pytest.fixture
def service(mock_llm_provider):
    return BoardGenerationService(mock_llm_provider)

@pytest.mark.anyio
async def test_generate_board_items_valid_json(service, mock_llm_provider):
    # Setup
    mock_llm_provider.generate.return_value = """
    [
        {"label": "Yes", "symbol_key": "check_mark", "color": "#E8F5E9"},
        {"label": "No", "symbol_key": "cross_mark", "color": "#FFEBEE"}
    ]
    """
    
    # Execute
    items = await service.generate_board_items(topic="Test", item_count=2, fail_silently=False)
    
    # Verify
    assert len(items) == 2
    assert items[0]["label"] == "Yes"
    assert items[1]["label"] == "No"

@pytest.mark.anyio
async def test_generate_board_items_with_markdown_blocks(service, mock_llm_provider):
    # Setup
    mock_llm_provider.generate.return_value = """
    Here is the JSON:
    ```json
    [
        {"label": "Eat", "symbol_key": "eat", "color": "#FFFFFF"}
    ]
    ```
    """
    
    # Execute
    items = await service.generate_board_items(topic="Test", item_count=1, fail_silently=False)
    
    # Verify
    assert len(items) == 1
    assert items[0]["label"] == "Eat"

@pytest.mark.anyio
async def test_generate_board_items_empty_response_raises_error(service, mock_llm_provider):
    # Setup
    mock_llm_provider.generate.return_value = ""
    
    # Execute & Verify
    with pytest.raises(ValueError, match="AI response was not valid JSON"):
        await service.generate_board_items(topic="Test", fail_silently=False)

@pytest.mark.anyio
async def test_generate_board_items_invalid_content_raises_error(service, mock_llm_provider):
    # Setup - Use input that will be stripped away by fallback parser (only special chars)
    mock_llm_provider.generate.return_value = " * - "
    
    # Execute & Verify
    with pytest.raises(ValueError, match="AI response was not valid JSON"):
        await service.generate_board_items(topic="Test", fail_silently=False)

@pytest.mark.anyio
async def test_generate_board_items_fail_silently_returns_empty(service, mock_llm_provider):
    # Setup - Use input that will be stripped away
    mock_llm_provider.generate.return_value = " * - "
    
    # Execute
    items = await service.generate_board_items(topic="Test", fail_silently=True)
    
    # Verify
    assert items == []

@pytest.mark.anyio
async def test_generate_board_items_provider_exception(service, mock_llm_provider):
    # Setup
    mock_llm_provider.generate.side_effect = Exception("API Error")
    
    # Execute & Verify
    with pytest.raises(Exception, match="API Error"):
        await service.generate_board_items(topic="Test", fail_silently=False)

@pytest.mark.anyio
async def test_generate_board_items_provider_exception_fail_silently(service, mock_llm_provider):
    # Setup
    mock_llm_provider.generate.side_effect = Exception("API Error")
    
    # Execute
    items = await service.generate_board_items(topic="Test", fail_silently=True)
    
    # Verify
    assert items == []

@pytest.mark.anyio
async def test_generate_board_items_does_not_recurse_for_missing_items(service, mock_llm_provider):
    # Setup: Provider returns fewer items than requested.
    mock_llm_provider.generate.return_value = """
    [{"label": "Item 1", "symbol_key": "item_1", "color": "#FFFFFF"}]
    """

    # Execute
    items = await service.generate_board_items(topic="Test", item_count=3, fail_silently=False)

    # Verify: Service accepts partial responses and avoids extra LLM calls.
    assert len(items) == 1
    assert items[0]["label"] == "Item 1"
    assert mock_llm_provider.generate.call_count == 1
