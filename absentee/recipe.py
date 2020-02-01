#!/usr/bin/env python3

import toml
from .transforms import *
from .error import ConfigError


def build_toml(toml_input, ast):

    BIND = {
        "addLabels": AddLabels,
        "constantFolding": ConstantFolding,
        "initialize": Initialize,
        "noArrays": NoArrays,
        "purgeTypedefs": PurgeTypedefs,
        "renameCalls": RenameCalls,
        "retype": Retype,
        "toLogical": ToLogical
    }

    conf = toml.loads(toml_input)

    if "main" not in conf:
        raise ConfigError("Missing \"main\" in configuration")

    main = conf["main"]

    undefined_transforms = [k for k in main.get("do", []) if k not in BIND]
    if undefined_transforms:
        warn("Warning: The following transformations are not defined:",
             ", ".join(undefined_transforms))

    transforms = [
        BIND[k](ast, conf.get(k, {}))
        for k in main.get("do", [])
        if k in BIND
    ]

    includes = [
        f"#include {i}"
        if i.startswith("<")
        else f"#include \"{i}\""
        for i in main.get("includes", [])
    ]

    return transforms, includes, main.get("rawPrelude", "")
