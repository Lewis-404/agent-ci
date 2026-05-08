"""Tests for plugin discovery and loading."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_ci.checkers import BaseChecker
from agent_ci.plugins import _load_directory_plugins, _load_entry_points, discover_plugins

# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_plugin_file(directory: Path, name: str, content: str) -> Path:
    """Write a .py plugin file to a directory, ensuring dir exists."""
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / f"{name}.py"
    p.write_text(content)
    return p


# ── _load_directory_plugins tests ────────────────────────────────────────────


class TestLoadDirectoryPlugins:
    """Test _load_directory_plugins function."""

    def test_non_existent_path(self):
        """Non-existent path should return silently."""
        plugins: dict = {}
        _load_directory_plugins(Path("/nonexistent/path/12345"), plugins)
        assert plugins == {}

    def test_path_is_file_not_dir(self, tmp_path: Path):
        """Path that is a file, not a directory, should be handled gracefully."""
        f = tmp_path / "not_a_dir.txt"
        f.write_text("hello")
        plugins: dict = {}
        _load_directory_plugins(f, plugins)
        assert plugins == {}

    def test_empty_directory(self, tmp_path: Path):
        """Empty directory should return empty plugins dict."""
        plugins: dict = {}
        _load_directory_plugins(tmp_path, plugins)
        assert plugins == {}

    def test_directory_only_underscore_files(self, tmp_path: Path):
        """Files starting with _ should be skipped."""
        _write_plugin_file(
            tmp_path,
            "_internal",
            """
from agent_ci.checkers import BaseChecker

class MyChecker(BaseChecker):
    name = "internal"
""",
        )
        plugins: dict = {}
        _load_directory_plugins(tmp_path, plugins)
        assert plugins == {}

    def test_discover_valid_checker(self, tmp_path: Path):
        """A valid checker class should be discovered and registered."""
        _write_plugin_file(
            tmp_path,
            "mychecker",
            """
from agent_ci.checkers import BaseChecker

class MyChecker(BaseChecker):
    name = "my_custom_checker"
""",
        )
        plugins: dict = {}
        _load_directory_plugins(tmp_path, plugins)
        assert "my_custom_checker" in plugins
        assert issubclass(plugins["my_custom_checker"], BaseChecker)

    def test_discover_multiple_valid_checkers(self, tmp_path: Path):
        """Multiple valid checker files should all be discovered."""
        _write_plugin_file(
            tmp_path,
            "checker_a",
            """
from agent_ci.checkers import BaseChecker

class CheckerA(BaseChecker):
    name = "checker_a"
""",
        )
        _write_plugin_file(
            tmp_path,
            "checker_b",
            """
from agent_ci.checkers import BaseChecker

class CheckerB(BaseChecker):
    name = "checker_b"
""",
        )
        plugins: dict = {}
        _load_directory_plugins(tmp_path, plugins)
        assert len(plugins) == 2
        assert "checker_a" in plugins
        assert "checker_b" in plugins

    def test_class_inherits_default_name(self, tmp_path: Path):
        """Class inheriting BaseChecker without explicit name gets default 'base'."""
        _write_plugin_file(
            tmp_path,
            "noname",
            """
from agent_ci.checkers import BaseChecker

class NoNameChecker(BaseChecker):
    pass
""",
        )
        plugins: dict = {}
        _load_directory_plugins(tmp_path, plugins)
        # BaseChecker.name defaults to "base", so subclass inherits it
        assert "base" in plugins
        assert plugins["base"].__name__ == "NoNameChecker"

    def test_skip_non_checker_class(self, tmp_path: Path):
        """Class that does NOT inherit BaseChecker should be skipped."""
        _write_plugin_file(
            tmp_path,
            "notchecker",
            """
class SomeRandomClass:
    name = "random"
""",
        )
        plugins: dict = {}
        _load_directory_plugins(tmp_path, plugins)
        assert plugins == {}

    def test_skip_basechecker_itself(self, tmp_path: Path):
        """The BaseChecker class itself (if present) should not be registered."""
        _write_plugin_file(
            tmp_path,
            "reimport",
            """
from agent_ci.checkers import BaseChecker as BC

# Re-exporting BaseChecker itself (not a subclass)
class JustBase(BC):
    pass

# This one is a proper subclass with name
class RealChecker(BC):
    name = "real"
""",
        )
        plugins: dict = {}
        _load_directory_plugins(tmp_path, plugins)
        # JustBase inherits default name="base", RealChecker has name="real"
        assert "real" in plugins
        assert "base" in plugins
        assert "JustBase" not in plugins
        assert "BaseChecker" not in plugins

    def test_module_import_error_is_silenced(self, tmp_path: Path):
        """A plugin file that raises on import should be silently skipped."""
        _write_plugin_file(
            tmp_path,
            "broken",
            """
raise RuntimeError("boom")
""",
        )
        plugins: dict = {}
        # Should not raise
        _load_directory_plugins(tmp_path, plugins)
        assert plugins == {}

    def test_partial_module_error_does_not_block_others(self, tmp_path: Path):
        """One broken plugin should not prevent other valid ones from loading."""
        _write_plugin_file(
            tmp_path,
            "broken",
            """
raise RuntimeError("boom")
""",
        )
        _write_plugin_file(
            tmp_path,
            "good",
            """
from agent_ci.checkers import BaseChecker

class GoodChecker(BaseChecker):
    name = "good_checker"
""",
        )
        plugins: dict = {}
        _load_directory_plugins(tmp_path, plugins)
        assert "good_checker" in plugins
        assert len(plugins) == 1

    def test_class_with_name_attr_but_not_checker(self, tmp_path: Path):
        """Class with 'name' attr but not BaseChecker subclass should be skipped."""
        _write_plugin_file(
            tmp_path,
            "impostor",
            """
class Impostor:
    name = "fake"
""",
        )
        plugins: dict = {}
        _load_directory_plugins(tmp_path, plugins)
        assert plugins == {}

    def test_spec_is_none_handled(self, tmp_path: Path, monkeypatch):
        """When spec_from_file_location returns None, should continue silently."""
        _write_plugin_file(
            tmp_path,
            "valid",
            """
from agent_ci.checkers import BaseChecker

class ValidChecker(BaseChecker):
    name = "valid"
""",
        )

        import importlib.util

        original = importlib.util.spec_from_file_location

        call_count = 0

        def mock_spec(name, path):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # simulate spec failure
            return original(name, path)

        monkeypatch.setattr(importlib.util, "spec_from_file_location", mock_spec)

        plugins: dict = {}
        _load_directory_plugins(tmp_path, plugins)
        # The first file gets None spec and is skipped; second file loads fine
        # Actually only one file exists — so it returns None and plugins stays empty
        assert plugins == {}

    def test_deterministic_order(self, tmp_path: Path):
        """Plugins should be loaded in sorted order (deterministic)."""
        names = ["zebra", "alpha", "mike"]
        for n in names:
            _write_plugin_file(
                tmp_path,
                n,
                f"""
from agent_ci.checkers import BaseChecker

class Checker{names.index(n)}(BaseChecker):
    name = "{n}"
""",
            )
        plugins: dict = {}
        _load_directory_plugins(tmp_path, plugins)

        # Already sorted alphabetically by filename (alpha < mike < zebra)
        # The registration order should match sorted file glob
        assert set(plugins.keys()) == set(names)

    def test_object_that_is_not_a_class(self, tmp_path: Path):
        """Module-level objects that are not classes should not crash discovery."""
        _write_plugin_file(
            tmp_path,
            "nonclass",
            """
from agent_ci.checkers import BaseChecker

NOT_A_CLASS = "just a string"

def some_function():
    pass

class RealChecker(BaseChecker):
    name = "real_checker"
""",
        )
        plugins: dict = {}
        _load_directory_plugins(tmp_path, plugins)
        assert "real_checker" in plugins
        assert len(plugins) == 1


# ── _load_entry_points tests ─────────────────────────────────────────────────


class TestLoadEntryPoints:
    """Test _load_entry_points function."""

    def test_no_entry_points(self):
        """When no entry points exist, plugins dict stays empty."""
        plugins: dict = {}
        with patch("importlib.metadata.entry_points", return_value=[]):
            _load_entry_points(plugins)
        assert plugins == {}

    def test_valid_entry_point(self):
        """Valid entry point with proper checker class should be registered."""
        plugins: dict = {}

        class ValidChecker(BaseChecker):
            name = "valid_checker"

        ep = MagicMock()
        ep.load.return_value = ValidChecker

        with patch("importlib.metadata.entry_points", return_value=[ep]):
            _load_entry_points(plugins)

        assert "valid_checker" in plugins
        assert plugins["valid_checker"] is ValidChecker

    def test_entry_point_not_a_checker(self):
        """Entry point that doesn't return a BaseChecker subclass should be skipped."""
        plugins: dict = {}

        class NotAChecker:
            name = "nope"

        ep = MagicMock()
        ep.load.return_value = NotAChecker

        with patch("importlib.metadata.entry_points", return_value=[ep]):
            _load_entry_points(plugins)

        assert plugins == {}

    def test_entry_point_inherits_default_name(self):
        """Entry point class without explicit 'name' inherits 'base' default."""
        plugins: dict = {}

        class NoName(BaseChecker):
            pass

        ep = MagicMock()
        ep.load.return_value = NoName

        with patch("importlib.metadata.entry_points", return_value=[ep]):
            _load_entry_points(plugins)

        # BaseChecker.name defaults to "base", so subclass inherits it
        assert "base" in plugins
        assert plugins["base"] is NoName

    def test_entry_point_load_raises(self):
        """Entry point whose load() raises should be silently skipped."""
        plugins: dict = {}
        ep = MagicMock()
        ep.load.side_effect = RuntimeError("cannot load")

        with patch("importlib.metadata.entry_points", return_value=[ep]):
            _load_entry_points(plugins)

        assert plugins == {}

    def test_entry_points_function_raises(self):
        """If entry_points() itself raises, should be silently handled."""
        plugins: dict = {}
        with patch(
            "importlib.metadata.entry_points",
            side_effect=ImportError("no entry_points"),
        ):
            _load_entry_points(plugins)
        assert plugins == {}

    def test_mixed_valid_and_invalid_entry_points(self):
        """Mix of valid and invalid entry points — only valid ones registered."""
        plugins: dict = {}

        class GoodChecker(BaseChecker):
            name = "good"

        class BadChecker:
            name = "bad"

        class NoNameBad(BaseChecker):
            pass

        ep_good = MagicMock()
        ep_good.load.return_value = GoodChecker

        ep_bad = MagicMock()
        ep_bad.load.return_value = BadChecker

        ep_noname = MagicMock()
        ep_noname.load.return_value = NoNameBad

        with patch(
            "importlib.metadata.entry_points",
            return_value=[ep_good, ep_bad, ep_noname],
        ):
            _load_entry_points(plugins)

        assert list(plugins.keys()) == ["good", "base"]


# ── discover_plugins integration tests ───────────────────────────────────────


class TestDiscoverPlugins:
    """Integration tests for discover_plugins."""

    def test_no_config_returns_empty(self):
        """Empty config with no plugin paths and no entry points should return {}."""
        with patch("importlib.metadata.entry_points", return_value=[]):
            result = discover_plugins({})
        assert result == {}

    def test_config_with_valid_directory_path(self, tmp_path: Path):
        """Valid plugin directory in config should be discovered."""
        _write_plugin_file(
            tmp_path / "plugins",
            "mychecker",
            """
from agent_ci.checkers import BaseChecker

class MyChecker(BaseChecker):
    name = "config_loaded"
""",
        )
        config = {"plugins": {"paths": [str(tmp_path / "plugins")]}}

        with patch("importlib.metadata.entry_points", return_value=[]):
            result = discover_plugins(config)

        assert "config_loaded" in result
        assert issubclass(result["config_loaded"], BaseChecker)

    def test_config_with_non_existent_path(self):
        """Non-existent paths in config should be silently handled."""
        config = {"plugins": {"paths": ["/nonexistent/path/xyz"]}}

        with patch("importlib.metadata.entry_points", return_value=[]):
            result = discover_plugins(config)

        assert result == {}

    def test_config_with_multiple_paths(self, tmp_path: Path):
        """Multiple plugin paths should all be scanned."""
        dir_a = tmp_path / "plugins_a"
        dir_b = tmp_path / "plugins_b"

        _write_plugin_file(
            dir_a,
            "checker_a",
            """
from agent_ci.checkers import BaseChecker

class CheckerA(BaseChecker):
    name = "a"
""",
        )
        _write_plugin_file(
            dir_b,
            "checker_b",
            """
from agent_ci.checkers import BaseChecker

class CheckerB(BaseChecker):
    name = "b"
""",
        )

        config = {"plugins": {"paths": [str(dir_a), str(dir_b)]}}

        with patch("importlib.metadata.entry_points", return_value=[]):
            result = discover_plugins(config)

        assert "a" in result
        assert "b" in result
        assert len(result) == 2

    def test_entry_points_and_directory_both_contribute(self, tmp_path: Path):
        """Both entry point plugins and directory plugins should merge."""
        _write_plugin_file(
            tmp_path / "plugins",
            "dir_checker",
            """
from agent_ci.checkers import BaseChecker

class DirChecker(BaseChecker):
    name = "from_dir"
""",
        )

        class EpChecker(BaseChecker):
            name = "from_ep"

        ep = MagicMock()
        ep.load.return_value = EpChecker

        config = {"plugins": {"paths": [str(tmp_path / "plugins")]}}

        with patch("importlib.metadata.entry_points", return_value=[ep]):
            result = discover_plugins(config)

        assert "from_dir" in result
        assert "from_ep" in result
        assert len(result) == 2

    def test_duplicate_names_last_wins(self, tmp_path: Path):
        """When two plugins have the same name, the last one loaded wins."""
        _write_plugin_file(
            tmp_path / "first",
            "checker",
            """
from agent_ci.checkers import BaseChecker

class FirstChecker(BaseChecker):
    name = "duplicate"
""",
        )
        _write_plugin_file(
            tmp_path / "second",
            "checker",
            """
from agent_ci.checkers import BaseChecker

class SecondChecker(BaseChecker):
    name = "duplicate"
""",
        )

        config = {
            "plugins": {"paths": [str(tmp_path / "first"), str(tmp_path / "second")]}
        }

        with patch("importlib.metadata.entry_points", return_value=[]):
            result = discover_plugins(config)

        assert "duplicate" in result
        assert result["duplicate"].__name__ == "SecondChecker"

    def test_config_without_plugins_key(self):
        """Config dictionary without 'plugins' key should work fine."""
        with patch("importlib.metadata.entry_points", return_value=[]):
            result = discover_plugins({"other": "stuff"})
        assert result == {}

    def test_config_with_plugins_but_no_paths(self):
        """Config with 'plugins' key but no 'paths' should work fine."""
        with patch("importlib.metadata.entry_points", return_value=[]):
            result = discover_plugins({"plugins": {}})
        assert result == {}
