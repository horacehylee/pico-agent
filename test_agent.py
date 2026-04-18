import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import pytest

import agent


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def sample_file(tmp_dir):
    p = tmp_dir / "hello.txt"
    p.write_text("Hello World\nLine 2\nLine 3\n", encoding="utf-8")
    return p


class TestResolve:
    def test_absolute_path(self):
        result = agent._resolve(os.path.abspath("/tmp/test.txt"))
        assert result == Path(os.path.abspath("/tmp/test.txt"))

    def test_relative_path_resolves_to_cwd(self):
        result = agent._resolve("some/file.txt")
        assert result == (Path.cwd() / "some/file.txt").resolve()

    def test_home_expansion(self):
        result = agent._resolve("~/test.txt")
        assert str(result).startswith(str(Path.home()))


class TestHeaders:
    def test_headers_structure(self):
        h = agent._headers("my-key")
        assert h == {
            "Authorization": "Bearer my-key",
            "Content-Type": "application/json",
        }


class TestReadFile:
    def test_read_existing_file(self, sample_file):
        content = agent.read_file(str(sample_file))
        assert "Hello World" in content
        assert "Line 2" in content

    def test_read_nonexistent_file(self):
        result = agent.read_file("/nonexistent/path/file.txt")
        assert result.startswith("Error:")

    def test_read_file_contents(self, sample_file):
        content = agent.read_file(str(sample_file))
        assert content == "Hello World\nLine 2\nLine 3\n"


class TestListFiles:
    def test_list_directory(self, tmp_dir):
        (tmp_dir / "a.txt").write_text("a")
        (tmp_dir / "b.py").write_text("b")
        (tmp_dir / "subdir").mkdir()
        result = agent.list_files(str(tmp_dir))
        assert "[F] a.txt" in result
        assert "[F] b.py" in result
        assert "[D] subdir" in result

    def test_list_nonexistent_directory(self):
        result = agent.list_files("/nonexistent/dir")
        assert "Error" in result

    def test_list_empty_directory(self, tmp_dir):
        empty = tmp_dir / "empty"
        empty.mkdir()
        result = agent.list_files(str(empty))
        assert result == ""

    def test_list_file_instead_of_dir(self, sample_file):
        result = agent.list_files(str(sample_file))
        assert "Error" in result


class TestEditFile:
    def test_edit_existing_file(self, sample_file):
        result = agent.edit_file(str(sample_file), "Hello World", "Goodbye World")
        assert "Edited" in result
        assert sample_file.read_text() == "Goodbye World\nLine 2\nLine 3\n"

    def test_edit_file_old_str_not_found(self, sample_file):
        result = agent.edit_file(str(sample_file), "does not exist", "new")
        assert "Error" in result

    def test_edit_nonexistent_file(self, tmp_dir):
        result = agent.edit_file(str(tmp_dir / "nope.txt"), "old", "new")
        assert "Error" in result

    def test_create_new_file(self, tmp_dir):
        new_file = tmp_dir / "new.txt"
        result = agent.edit_file(str(new_file), "", "hello")
        assert "Created" in result
        assert new_file.read_text() == "hello"

    def test_create_file_in_new_subdirectory(self, tmp_dir):
        new_file = tmp_dir / "sub" / "dir" / "file.txt"
        result = agent.edit_file(str(new_file), "", "deep")
        assert "Created" in result
        assert new_file.read_text() == "deep"

    def test_edit_replaces_only_first_occurrence(self, tmp_dir):
        p = tmp_dir / "multi.txt"
        p.write_text("aaa bbb aaa", encoding="utf-8")
        agent.edit_file(str(p), "aaa", "zzz")
        assert p.read_text() == "zzz bbb aaa"


class TestRunBash:
    def test_successful_command(self):
        result = agent.run_bash("echo hello")
        assert "hello" in result

    def test_command_with_stderr(self):
        result = agent.run_bash('python -c "import sys; print(\'err\', file=sys.stderr)"')
        assert "err" in result

    def test_command_timeout(self):
        result = agent.run_bash("timeout 60 ping -t 60 127.0.0.1 2>nul || sleep 60")
        assert "timed out" in result or "Error" in result

    def test_no_output(self):
        result = agent.run_bash("cd .")
        assert result  # should return something, even "(no output)"


class TestSearchFiles:
    def test_search_finds_matches(self, tmp_dir):
        (tmp_dir / "code.py").write_text("def hello():\n    pass\n", encoding="utf-8")
        (tmp_dir / "other.py").write_text("def world():\n    pass\n", encoding="utf-8")
        result = agent.search_files("def hello", str(tmp_dir))
        assert "code.py" in result
        assert "def hello" in result

    def test_search_no_matches(self, tmp_dir):
        (tmp_dir / "code.py").write_text("nothing here\n", encoding="utf-8")
        result = agent.search_files("xyzzy_nonexistent", str(tmp_dir))
        assert "No matches found" in result

    def test_search_invalid_regex(self, tmp_dir):
        result = agent.search_files("[invalid", str(tmp_dir))
        assert "Error" in result

    def test_search_truncation_at_50(self, tmp_dir):
        for i in range(55):
            (tmp_dir / f"f{i}.txt").write_text(f"UNIQUE_MARKER_{i}\n", encoding="utf-8")
        result = agent.search_files("UNIQUE_MARKER", str(tmp_dir))
        assert "truncated" in result

    def test_search_with_line_numbers(self, tmp_dir):
        p = tmp_dir / "lines.txt"
        p.write_text("aaa\nbbb\nccc\n", encoding="utf-8")
        result = agent.search_files("bbb", str(tmp_dir))
        assert ":2:" in result


class TestCallLlm:
    @mock.patch("agent.requests.post")
    def test_call_llm_sends_correct_payload(self, mock_post):
        mock_resp = mock.MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "hi"}}]
        }
        mock_resp.raise_for_status = mock.MagicMock()
        mock_post.return_value = mock_resp

        messages = [{"role": "user", "content": "hello"}]
        result = agent.call_llm(messages)

        assert result["content"] == "hi"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["model"] == agent.MODEL
        assert payload["messages"] == messages
        assert payload["tools"] == agent.TOOLS
        assert payload["tool_choice"] == "auto"

    @mock.patch("agent.requests.post")
    def test_call_llm_raises_on_http_error(self, mock_post):
        mock_post.side_effect = Exception("connection failed")
        with pytest.raises(Exception, match="connection failed"):
            agent.call_llm([{"role": "user", "content": "hi"}])


class TestTools:
    def test_tools_schema_structure(self):
        for tool in agent.TOOLS:
            assert tool["type"] == "function"
            fn = tool["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            assert "required" in fn["parameters"]

    def test_tool_map_has_all_tools(self):
        for tool in agent.TOOLS:
            name = tool["function"]["name"]
            assert name in agent.TOOL_MAP
            assert callable(agent.TOOL_MAP[name])

    def test_tool_map_functions_match_tools(self):
        tool_names = {t["function"]["name"] for t in agent.TOOLS}
        assert set(agent.TOOL_MAP.keys()) == tool_names


class TestRun:
    @mock.patch("agent.call_llm")
    @mock.patch("builtins.input", side_effect=["what is 2+2?", EOFError])
    def test_run_simple_conversation(self, mock_input, mock_llm, capsys):
        mock_llm.return_value = {"role": "assistant", "content": "4"}
        agent.run()
        captured = capsys.readouterr()
        assert "4" in captured.out

    @mock.patch("builtins.input", side_effect=EOFError)
    def test_run_exits_on_eof(self, mock_input, capsys):
        agent.run()
        captured = capsys.readouterr()
        assert "Bye" in captured.out

    @mock.patch("agent.call_llm")
    @mock.patch("builtins.input", side_effect=["do stuff", EOFError])
    def test_run_handles_tool_calls(self, mock_input, mock_llm, tmp_dir, capsys):
        test_file = tmp_dir / "test_read.txt"
        test_file.write_text("file contents", encoding="utf-8")

        tool_response = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "tc1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"path": str(test_file)}),
                    },
                }
            ],
        }
        final_response = {"role": "assistant", "content": "Done reading file."}
        mock_llm.side_effect = [tool_response, final_response]

        agent.run()
        captured = capsys.readouterr()
        assert "Done reading file." in captured.out

    @mock.patch("agent.call_llm", side_effect=Exception("API down"))
    @mock.patch("builtins.input", side_effect=["hello", EOFError])
    def test_run_handles_api_error(self, mock_input, mock_llm, capsys):
        agent.run()
        captured = capsys.readouterr()
        assert "API error" in captured.out
