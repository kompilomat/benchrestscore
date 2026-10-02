# -*- coding: utf-8 -*-
"""Headless unit tests for the settings module (temp dir, no window/GL)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import tempfile

from benchrestscore.settings import load, save, default_config_path, default_config_dir


def test_load_missing_file():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        assert load(path) == {}


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "sub", "settings.json")
        save({"language": "en"}, path=path)
        assert load(path) == {"language": "en"}
        assert os.path.exists(path)


def test_save_merges():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        save({"language": "de"}, path=path)
        save({"theme": "dark"}, path=path)
        assert load(path) == {"language": "de", "theme": "dark"}


def test_load_corrupt_file():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "settings.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json")
        assert load(path) == {}


def test_default_config_path_uses_xdg():
    save_env = os.environ.get("XDG_CONFIG_HOME")
    with tempfile.TemporaryDirectory() as td:
        os.environ["XDG_CONFIG_HOME"] = td
        try:
            p = default_config_path()
            assert p.startswith(td + os.sep)
            assert p.endswith(os.path.join("benchrestscore", "settings.json"))
        finally:
            if save_env is None:
                del os.environ["XDG_CONFIG_HOME"]
            else:
                os.environ["XDG_CONFIG_HOME"] = save_env


def test_default_config_dir_matches_path_dirname():
    save_env = os.environ.get("XDG_CONFIG_HOME")
    with tempfile.TemporaryDirectory() as td:
        os.environ["XDG_CONFIG_HOME"] = td
        try:
            assert default_config_dir() == os.path.dirname(default_config_path())
            assert default_config_dir().endswith(os.path.join("benchrestscore"))
        finally:
            if save_env is None:
                del os.environ["XDG_CONFIG_HOME"]
            else:
                os.environ["XDG_CONFIG_HOME"] = save_env


if __name__ == "__main__":
    for fn in (test_load_missing_file, test_save_and_load_roundtrip,
               test_save_merges, test_load_corrupt_file,
               test_default_config_path_uses_xdg,
               test_default_config_dir_matches_path_dirname):
        fn()
        print(f"PASS {fn.__name__}")
    print("All settings tests passed")