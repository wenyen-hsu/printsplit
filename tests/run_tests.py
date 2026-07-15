# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless test runner.

    "/Applications/Blender 4.5.app/Contents/MacOS/Blender" \
        --background --factory-startup --python tests/run_tests.py [-- filter]

Discovers test_*.py in this directory, runs every test_* function with a
fresh empty scene, and exits non-zero on any failure.
"""

import importlib.util
import os
import sys
import traceback

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS_DIR)


def load_addon_package():
    spec = importlib.util.spec_from_file_location(
        "printsplit",
        os.path.join(ROOT, "__init__.py"),
        submodule_search_locations=[ROOT],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["printsplit"] = module
    spec.loader.exec_module(module)
    module.register()
    return module


def fresh_scene():
    import bpy

    bpy.ops.wm.read_homefile(use_empty=True)


def main():
    argv = sys.argv
    name_filter = ""
    if "--" in argv:
        extra = argv[argv.index("--") + 1:]
        if extra:
            name_filter = extra[0]

    load_addon_package()

    test_files = sorted(
        f for f in os.listdir(TESTS_DIR)
        if f.startswith("test_") and f.endswith(".py")
    )

    passed, failed = 0, 0
    failures = []
    for filename in test_files:
        mod_name = filename[:-3]
        spec = importlib.util.spec_from_file_location(
            mod_name, os.path.join(TESTS_DIR, filename))
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)

        for attr in sorted(dir(module)):
            if not attr.startswith("test_"):
                continue
            if name_filter and name_filter not in f"{mod_name}.{attr}":
                continue
            fresh_scene()
            label = f"{mod_name}.{attr}"
            try:
                getattr(module, attr)()
            except Exception:
                failed += 1
                failures.append((label, traceback.format_exc()))
                print(f"FAIL  {label}")
            else:
                passed += 1
                print(f"ok    {label}")

    print(f"\n{passed} passed, {failed} failed")
    for label, tb in failures:
        print(f"\n--- {label} ---\n{tb}")
    sys.exit(1 if failed else 0)


main()
