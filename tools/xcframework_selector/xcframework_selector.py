# Copyright 2021 The Bazel Authors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import errno
from typing import Any, Dict, Set
import re
import os
import plistlib
import shutil
import sys
import pathlib

# classes borrowed from https://github.com/keith/xcframework-to-fat/blob/main/xcframework-to-fat
_VALID_PLATFORMS = {"watchos", "ios", "tvos", "macosx"}
_VALID_ARCHS = {"i386", "arm64", "arm64e", "x86_64", "armv7s", "armv7k"}


class Triple:
    # Examples: x86_64-apple-ios11.0-simulator, arm64-apple-ios11.0
    def __init__(self, triple: str):
        self._original = triple
        parts = triple.split("-")
        if len(parts) not in (2, 3, 4):
            raise SystemExit(
                f"ERROR: invalid triple: '{triple}', expected arch-apple-platform[version][-simulator]"
            )

        self.arch = parts[0]
        if self.arch not in _VALID_ARCHS:
            raise SystemExit(
                f"ERROR: unexpected arch: '{self.arch}', expected one of: {', '.join(_VALID_ARCHS)}"
            )

        self.platform = parts[1]
        if self.platform == "apple":
            self.platform = parts[2]

        self.platform = re.sub(r"[^a-z]+", "", self.platform)
        if self.platform not in _VALID_PLATFORMS:
            raise SystemExit(
                f"ERROR: unexpected platform: {self.platform}, expected one of: {', '.join(_VALID_PLATFORMS)}"
            )

        self.is_simulator = parts[-1] == "simulator"

    def __str__(self) -> str:
        return self._original


class Library:
    def __init__(self, root: str, plist_definition: Dict[str, Any]):
        self.name = os.path.splitext(plist_definition["LibraryPath"])[0]
        self.framework_path: str = os.path.join(
            root,
            plist_definition["LibraryIdentifier"],
            plist_definition["LibraryPath"],
        )
        self.binary_path = os.path.join(self.framework_path, self.name)
        self.archs: Set[str] = set(plist_definition["SupportedArchitectures"])
        self.platform: str = plist_definition["SupportedPlatform"]
        self.is_simulator = (
                plist_definition.get("SupportedPlatformVariant") == "simulator"
        )

    def matches(self, triple: Triple) -> bool:
        return (
                triple.platform == self.platform
                and triple.arch in self.archs
                and triple.is_simulator == self.is_simulator
        )


def _main(triple_string, plist_path, output_path):
    triple = Triple(triple_string)
    with open(plist_path, "br") as plist_file:
        xcframework_path = plist_path.split("/Info.plist")[0]
        plist = plistlib.load(plist_file)
        v = plist["XCFrameworkFormatVersion"]
        if v != "1.0":
            raise SystemExit(f"ERROR: unsupported xcframework version: {v}")
        found = False
        for definition in plist["AvailableLibraries"]:
            library = Library(xcframework_path, definition)
            if library.matches(triple):
                if found:
                    raise SystemExit(
                        f"ERROR: multiple .framework matches found for triple: '{triple}'",
                    )
                shutil.copytree(
                    library.framework_path,
                    output_path,
                    symlinks=False,
                    ignore_dangling_symlinks=False,
                    dirs_exist_ok=True
                )
                found = True
        if not found:
            raise SystemExit(
                f"ERROR: .framework not found for triple: '{triple}'"
            )


if __name__ == '__main__':
    if len(sys.argv) < 4:
        sys.stderr.write('ERROR: expected exactly 3 arguments\n')
        exit(1)
    _main(sys.argv[1], sys.argv[2], sys.argv[3])