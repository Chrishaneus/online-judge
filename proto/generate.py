"""Generate code from oj/v1/*.proto into every sibling service repo.

    make gen            (= .venv/bin/python generate.py)
    make check          (= .venv/bin/python generate.py --check)

Generated code is committed in each consumer so its Docker build needs no
protoc. --check regenerates into a temp dir and fails when any consumer's copy
is stale; it is the same gate every service runs in CI. Each target only gets
the files it uses.

Expects the repos side by side:   online-judge/{oj-proto, oj-dao, oj-rest, ...}
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
WORKSPACE = PROTO_DIR.parent
NODE_BIN = PROTO_DIR / "node_modules" / ".bin"
GO_BIN = PROTO_DIR / ".bin"


def proto(*names: str) -> list[str]:
    return [f"oj/v1/{n}.proto" for n in names]


@dataclass(frozen=True)
class Target:
    repo: str  # sibling directory
    out: str  # output dir inside the repo
    lang: str  # go | python | ts
    protos: list[str]


TARGETS = [
    Target("oj-dao", "internal/gen", "go", proto("types", "dao")),
    Target("oj-rest", "internal/gen", "go", proto("types", "judge")),
    Target("oj-runner", "internal/gen", "go", proto("types", "runner")),
    Target("oj-midlayer", "app/gen", "python", proto("types", "dao", "judge", "runner")),
    Target("oj-webapp", "src/lib/gen", "ts", proto("types", "judge")),
]


def tool_env() -> dict[str, str]:
    path = os.pathsep.join([str(GO_BIN), str(NODE_BIN), os.environ["PATH"]])
    return {**os.environ, "PATH": path}


def buf(*args: str) -> None:
    exe = shutil.which("buf", path=tool_env()["PATH"])
    if not exe:
        sys.exit("buf not found; run `make setup` in oj-proto")
    subprocess.run([exe, *args], cwd=PROTO_DIR, env=tool_env(), check=True)


def go_module(repo: str) -> str:
    for line in (WORKSPACE / repo / "go.mod").read_text().splitlines():
        if line.startswith("module "):
            return line.split()[1]
    sys.exit(f"{repo}/go.mod has no module line")


def gen_go(t: Target, out: Path) -> None:
    template = {
        "version": "v2",
        "managed": {
            "enabled": True,
            "override": [
                {"file_option": "go_package_prefix", "value": f"{go_module(t.repo)}/{t.out}"},
            ],
        },
        "plugins": [
            {"local": "protoc-gen-go", "out": ".", "opt": ["paths=source_relative"]},
            {"local": "protoc-gen-go-grpc", "out": ".", "opt": ["paths=source_relative"]},
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
        f"--grpc_python_out={out}",
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
    """Generate every target under root/<repo>/<out>; return the output dirs."""
    outs = []
    for t in TARGETS:
        out = root / t.repo / t.out
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
    missing = [t.repo for t in TARGETS if not (WORKSPACE / t.repo).is_dir()]
    if missing:
        sys.exit(f"missing sibling repos: {', '.join(missing)}")
    buf("lint")
    buf("format", "--diff", "--exit-code")
    if "--check" in sys.argv:
        with tempfile.TemporaryDirectory() as tmp:
            # go_module() reads go.mod from the real workspace, so the temp tree
            # only needs the output dirs.
            stale = [
                f"{t.repo}/{t.out}"
                for t, out in zip(TARGETS, generate(Path(tmp)))
                if not dirs_equal(out, WORKSPACE / t.repo / t.out)
            ]
        if stale:
            sys.exit("Generated code is stale in: " + ", ".join(stale) + "\nRun: make gen (in oj-proto)")
        print("Generated code is up to date.")
    else:
        for t in TARGETS:
            print(f"generating {t.repo}/{t.out} ({t.lang})")
        generate(WORKSPACE)


if __name__ == "__main__":
    main()
