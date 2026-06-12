import pytest

from llm_runner import extract_json


class TestExtractJson:
    def test_plain_object(self):
        assert extract_json('{"a": 1}') == '{"a": 1}'

    def test_object_with_code_fence_and_preamble(self):
        text = '結果です。\n```json\n{"items": [1, 2]}\n```\nご確認ください。'
        assert extract_json(text) == '{"items": [1, 2]}'

    def test_top_level_array(self):
        assert extract_json('回答:\n[{"a": 1}, {"a": 2}]') == '[{"a": 1}, {"a": 2}]'

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            extract_json("JSON を出力できませんでした。")

    def test_unclosed_json_raises(self):
        with pytest.raises(ValueError):
            extract_json('{"a": 1')
