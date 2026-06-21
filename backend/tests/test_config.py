import pytest
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shorts_generator import config

def test_require_api_key_missing():
    with patch("shorts_generator.config.MUAPI_API_KEY", ""):
        with pytest.raises(RuntimeError) as exc_info:
            config.require_api_key()

        assert "MUAPI_API_KEY is not set" in str(exc_info.value)

def test_require_api_key_present():
    with patch("shorts_generator.config.MUAPI_API_KEY", "test_key_123"):
        result = config.require_api_key()
        assert result == "test_key_123"
