"""Validate the actual embedded Compose config locally, without AWS access.

Run from module-02: uv run --project backend python deploy/aws/validate.py
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile

import yaml


class TemplateLoader(yaml.SafeLoader):
    pass


TemplateLoader.add_multi_constructor(
    "!", lambda loader, tag, node: (
        loader.construct_sequence(node) if isinstance(node, yaml.SequenceNode)
        else loader.construct_scalar(node)
    )
)
template = yaml.load(Path(__file__).with_name("cloudformation.yaml").read_text(), Loader=TemplateLoader)
script = template["Resources"]["Server"]["Properties"]["UserData"]["Fn::Base64"]
values = {"AppImage": "example/pairroom:test", "StartPairRoomOnBootstrap": "true"}


def substitute(match):
    name = match[1]
    return "${" + name[1:] + "}" if name.startswith("!") else values[name]


for mode in ('true', 'false'):
    values['StartPairRoomOnBootstrap'] = mode
    rendered = re.sub(r"\$\{([^}]+)\}", substitute, script)
    compose = rendered.split("<<'COMPOSE'\n", 1)[1].split("\nCOMPOSE", 1)[0]
    with tempfile.TemporaryDirectory(prefix="pairroom-validate-") as directory:
        folder = Path(directory)
        (folder / "compose.yaml").write_text(compose)
        subprocess.run(
            ["docker", "compose", "-f", str(folder / "compose.yaml"), "config", "--quiet"],
            env={**os.environ, "POSTGRES_PASSWORD": "validation-only-not-a-real-secret",
                 "FRONTEND_ORIGINS": "http://203.0.113.10"},
            check=True,
        )
    print(f"Embedded Compose valid with StartPairRoomOnBootstrap={mode}.")
print("No AWS calls or containers started.")
