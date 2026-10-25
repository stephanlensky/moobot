import pytest
from pytest_mock import MockerFixture

from moobot.agent.model import get_client, get_model


def test_get_model__api_key_unset__raises(mocker: MockerFixture) -> None:
    mocker.patch("moobot.agent.model.settings.litellm_api_key", None)
    get_client.cache_clear()
    get_model.cache_clear()

    with pytest.raises(ValueError, match="LITELLM_API_KEY"):
        get_model()


def test_get_model__api_key_set__uses_agent_model(mocker: MockerFixture) -> None:
    mocker.patch("moobot.agent.model.settings.litellm_api_key", "test")
    get_client.cache_clear()
    get_model.cache_clear()

    model = get_model()

    assert model.model == "openrouter/z-ai/glm-5.3-flash"
    get_client.cache_clear()
    get_model.cache_clear()
