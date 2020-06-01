import logging
import os

import pytest
import requests

from mock import patch

from nbexchange.plugin import Exchange

logger = logging.getLogger(__file__)
logger.setLevel(logging.ERROR)

"""
In this module we check that various helper methods in the Exchange base class works as expected.
In particular, we're checking that the api_request method does the right thing, as we will
be mocking it when testing the other classes.
"""


@pytest.mark.gen_test
def test_exhange_api_request_post():
    plugin = Exchange()

    def asserts(*args, **kwargs):
        assert "cookies" in kwargs
        assert "noteable_auth" in kwargs["cookies"]
        assert kwargs["cookies"]["noteable_auth"] == "test_token"
        assert "headers" in kwargs
        assert args[0] == plugin.service_url() + "test"
        return "Success"

    naas_token = os.environ.get("NAAS_JWT")
    os.environ["NAAS_JWT"] = "test_token"
    with patch("nbexchange.plugin.exchange.requests.post", side_effect=asserts):
        called = plugin.api_request("test", method="POST")
        assert called == "Success"
    if naas_token is not None:
        os.environ["NAAS_JWT"] = naas_token
    else:
        del os.environ["NAAS_JWT"]


@pytest.mark.gen_test
def test_exhange_api_request_delete():
    plugin = Exchange()

    def asserts(*args, **kwargs):
        assert "cookies" in kwargs
        assert "noteable_auth" in kwargs["cookies"]
        assert kwargs["cookies"]["noteable_auth"] == "test_token"
        assert "headers" in kwargs
        assert args[0] == plugin.service_url() + "test"
        return "Success"

    naas_token = os.environ.get("NAAS_JWT")
    os.environ["NAAS_JWT"] = "test_token"
    with patch("nbexchange.plugin.exchange.requests.delete", side_effect=asserts):
        called = plugin.api_request("test", method="DELETE")
        assert called == "Success"
    if naas_token is not None:
        os.environ["NAAS_JWT"] = naas_token
    else:
        del os.environ["NAAS_JWT"]


@pytest.mark.gen_test
def test_exhange_api_request_get():
    plugin = Exchange()

    def asserts(*args, **kwargs):
        assert "cookies" in kwargs
        assert "noteable_auth" in kwargs["cookies"]
        assert kwargs["cookies"]["noteable_auth"] == "test_token"
        assert "headers" in kwargs
        assert args[0] == plugin.service_url() + "test"
        return "Success"

    naas_token = os.environ.get("NAAS_JWT")
    os.environ["NAAS_JWT"] = "test_token"
    with patch("nbexchange.plugin.exchange.requests.get", side_effect=asserts):
        called = plugin.api_request("test")
        assert called == "Success"
    if naas_token is not None:
        os.environ["NAAS_JWT"] = naas_token
    else:
        del os.environ["NAAS_JWT"]