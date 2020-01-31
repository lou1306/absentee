#!/usr/bin/env python3

from click import echo


def warn(msg):
    echo(msg, err=True)


class BaseError(Exception):
    HEADER = ""

    def handle(self):
        echo(f"{self.HEADER} error: {self.message}", err=True)
        exit(self.CODE)


class ConfigError(BaseError):
    HEADER = "Configuration"
    CODE = 1

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return f"Configuration error: {self.message}"


class TransformError(BaseError):
    HEADER = "Transformation"
    CODE = 6

    def __init__(self, message, coords):
        self.message = f"{message}\nat: {coords}"
        self.coords = coords


class ParseError(BaseError):
    HEADER = "Parsing"
    CODE = 10

    def __init__(self, ply_exception):
        self.message = ply_exception
