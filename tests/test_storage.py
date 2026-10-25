import asyncio
import io
import json
from collections.abc import Generator

import boto3
import pytest
from agents import TResponseInputItem
from botocore.response import StreamingBody
from botocore.stub import Stubber
from pytest_mock import MockerFixture

from moobot.storage import get_transcript, set_transcript

KEY = "conversations/1.json"
ITEMS: list[TResponseInputItem] = [
    {"role": "user", "content": "hello"},
    {"role": "assistant", "content": "hi"},
]


@pytest.fixture
def stubber(mocker: MockerFixture) -> Generator[Stubber]:
    client = boto3.client(
        "s3",
        endpoint_url="http://s3.test",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
    mocker.patch("moobot.storage.get_client", return_value=client)
    with Stubber(client) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


def test_get_transcript__object_exists__returns_items(stubber: Stubber) -> None:
    body = json.dumps(ITEMS).encode()
    stubber.add_response(
        "get_object",
        {"Body": StreamingBody(io.BytesIO(body), len(body))},
        {"Bucket": "moobot", "Key": KEY},
    )

    assert asyncio.run(get_transcript(KEY)) == ITEMS


def test_get_transcript__object_missing__returns_empty_list(stubber: Stubber) -> None:
    stubber.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)

    assert asyncio.run(get_transcript(KEY)) == []


def test_set_transcript__writes_json(stubber: Stubber) -> None:
    stubber.add_response(
        "put_object",
        {},
        {
            "Bucket": "moobot",
            "Key": KEY,
            "Body": json.dumps(ITEMS).encode(),
            "ContentType": "application/json",
        },
    )

    asyncio.run(set_transcript(KEY, ITEMS))
