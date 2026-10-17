"""HTTP controllers (Flask blueprints) and the worker's RabbitMQ consumers. No business logic."""

from flask import Flask

from . import admin_controller, public_controller
from .consumers import JudgeConsumers
from .http import register_http_hooks


def register_controllers(app: Flask) -> None:
    for bp in (public_controller.health_bp, public_controller.bp, admin_controller.bp):
        app.register_blueprint(bp)
    register_http_hooks(app)


__all__ = ["JudgeConsumers", "register_controllers"]
