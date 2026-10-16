"""Generate code from oj/v1/*.proto into every service of the monorepo.

    make gen            (repo root or proto/; = proto/.venv/bin/python proto/generate.py)
    make check          (= ... generate.py --check)

Generated code is committed in each service so its Docker build (context = the
service directory) needs no protoc. --check regenerates into a temp dir and
fails when any service's copy is stale; CI runs it. Each target only gets the
files it uses.
"""

from __future__ import annotations

import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from grpc_tools import protoc

PROTO_DIR = Path(__file__).resolve().parent
ROOT = PROTO_DIR.parent
NODE_BIN = PROTO_DIR / "node_modules" / ".bin"
GO_BIN = PROTO_DIR / ".bin"


def proto(*names: str) -> list[str]:
    return [f"oj/v1/{n}.proto" for n in names]


@dataclass(frozen=True)
class Target:
    service: str  # directory under the repo root
    out: str  # output dir inside the service
    lang: str  # go | python | ts
    protos: list[str]


TARGETS = [
    Target("api", "app/gen", "python", proto("types", "judge", "runner")),
    Target("runner", "internal/gen", "go", proto("types", "runner")),
    Target("webapp", "src/lib/gen", "ts", proto("types", "judge")),
]


def tool_env() -> dict[str, str]:
    path = os.pathsep.join([str(GO_BIN), str(NODE_BIN), os.environ["PATH"]])
    return {**os.environ, "PATH": path}


def buf(*args: str) -> None:
    exe = shutil.which("buf", path=tool_env()["PATH"])
    if not exe:
        sys.exit("buf not found; run `make setup`")
    subprocess.run([exe, *args], cwd=PROTO_DIR, env=tool_env(), check=True)


def go_module(service: str) -> str:
    for line in (ROOT / service / "go.mod").read_text().splitlines():
        if line.startswith("module "):
            return line.split()[1]
    sys.exit(f"{service}/go.mod has no module line")


def gen_go(t: Target, out: Path) -> None:
    template = {
        "version": "v2",
        "managed": {
            "enabled": True,
            "override": [
                {"file_option": "go_package_prefix", "value": f"{go_module(t.service)}/{t.out}"},
            ],
        },
        "plugins": [
            {"local": "protoc-gen-go", "out": ".", "opt": ["paths=source_relative"]},
        ],
    }
    paths = [a for p in t.protos for a in ("--path", p)]
    buf("generate", "--template", json.dumps(template), "--output", str(out), *paths)


def gen_ts(t: Target, out: Path) -> None:
    template = {
        "version": "v2",
        "plugins": [{"local": "protoc-gen-es", "out": ".", "opt": ["target=ts", "import_extension=js"]}],
    }
    paths = [a for p in t.protos for a in ("--path", p)]
    buf("generate", "--template", json.dumps(template), "--output", str(out), *paths)


def gen_python(t: Target, out: Path) -> None:
    wkt = files("grpc_tools") / "_proto"
    args = [
        "protoc",
        f"-I{PROTO_DIR}",
        f"-I{wkt}",
        f"--python_out={out}",
        f"--pyi_out={out}",
        *(str(PROTO_DIR / p) for p in t.protos),
    ]
    if protoc.main(args) != 0:
        sys.exit("protoc (python) failed")
    # Make every folder a package and make the absolute imports ("from oj.v1 import")
    # resolve inside the consumer's package (app.gen).
    package = t.out.replace("/", ".")
    for folder in [out, *[d for d in out.rglob("*") if d.is_dir()]]:
        (folder / "__init__.py").touch()
    for f in out.rglob("*_pb2*.py*"):
        text = f.read_text().replace("from oj.v1 import", f"from {package}.oj.v1 import")
        f.write_text(text, newline="\n")


GENERATORS = {"go": gen_go, "ts": gen_ts, "python": gen_python}


def generate(root: Path) -> list[Path]:
    """Generate every target under root/<service>/<out>; return the output dirs."""
    outs = []
    for t in TARGETS:
        out = root / t.service / t.out
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        GENERATORS[t.lang](t, out)
        outs.append(out)
    return outs


def dirs_equal(a: Path, b: Path) -> bool:
    if not b.is_dir():
        return False
    cmp = filecmp.dircmp(a, b, ignore=["__pycache__"])
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(dirs_equal(a / d, b / d) for d in cmp.common_dirs)


def main() -> None:
    missing = [t.service for t in TARGETS if not (ROOT / t.service).is_dir()]
    if missing:
        sys.exit(f"missing service directories: {', '.join(missing)}")
    buf("lint")
    buf("format", "--diff", "--exit-code")
    if "--check" in sys.argv:
        with tempfile.TemporaryDirectory() as tmp:
            # go_module() reads go.mod from the real tree, so the temp tree
            # only needs the output dirs.
            stale = [
                f"{t.service}/{t.out}"
                for t, out in zip(TARGETS, generate(Path(tmp)))
                if not dirs_equal(out, ROOT / t.service / t.out)
            ]
        if stale:
            sys.exit("Generated code is stale in: " + ", ".join(stale) + "\nRun: make gen")
        print("Generated code is up to date.")
    else:
        for t in TARGETS:
            print(f"generating {t.service}/{t.out} ({t.lang})")
        generate(ROOT)


if __name__ == "__main__":
    main()
