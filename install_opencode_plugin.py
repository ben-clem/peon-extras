#!/usr/bin/env python3
"""Register the local peon-extras plugin in OpenCode's global config."""

import json
import os
import stat
import sys
import tempfile


def merge(data, plugin_directory):
    if not isinstance(data, dict):
        raise ValueError("OpenCode config must be an object")
    merged = dict(data)
    plugins = merged.get("plugins", [])
    if not isinstance(plugins, list):
        raise ValueError("OpenCode config plugins must be an array")
    plugin_directory = os.path.abspath(plugin_directory)
    if plugin_directory not in plugins:
        merged["plugins"] = [*plugins, plugin_directory]
    return merged


def write_config(path, data):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    mode = stat.S_IMODE(os.stat(path).st_mode) if os.path.exists(path) else 0o600
    descriptor, temporary_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.remove(temporary_path)
        except OSError:
            pass
        raise


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) != 3:
        print("usage: install_opencode_plugin.py CONFIG_JSON PLUGIN_DIRECTORY", file=sys.stderr)
        return 2

    config_path, plugin_directory = argv[1:]
    try:
        if os.path.isfile(config_path):
            with open(config_path) as handle:
                original = json.load(handle)
        else:
            original = {"$schema": "https://opencode.ai/config.json"}
        merged = merge(original, plugin_directory)
        if merged == original:
            print("unchanged", config_path)
            return 0
        write_config(config_path, merged)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("install_opencode_plugin.py: {}".format(error), file=sys.stderr)
        return 1

    print("wrote", config_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
