from os import environ

import pytest
from hypothesis import HealthCheck, settings

from cattrs import BaseConverter, Converter


@pytest.fixture(params=(True, False))
def genconverter(request):
    return Converter(detailed_validation=request.param)


@pytest.fixture(params=(True, False))
def converter(request, converter_cls):
    args = dict(detailed_validation=request.param)
    if converter_cls is Converter:
        args["include_subclasses"] = request.param
    return converter_cls(**args)


@pytest.fixture(params=(BaseConverter, Converter), scope="session")
def converter_cls(request):
    return request.param


settings.register_profile(
    "tests", suppress_health_check=(HealthCheck.too_slow,), deadline=None
)
settings.register_profile("fast", settings.get_profile("tests"), max_examples=10)

settings.load_profile("fast" if "FAST" in environ else "tests")
