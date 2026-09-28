"""Docker HEALTHCHECK: exit 0 iff this instance's grpc.health.v1.Health reports SERVING.

Usage: python -m app.healthcheck [addr]   (default: 127.0.0.1:<port of GRPC_ADDR>)
"""

import sys

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

from app.config import Settings


def local_addr(grpc_addr: str) -> str:
    return f"127.0.0.1:{grpc_addr.rsplit(':', 1)[-1]}"


def check(addr: str, timeout_s: float = 3.0) -> bool:
    try:
        with grpc.insecure_channel(addr) as channel:
            res = health_pb2_grpc.HealthStub(channel).Check(
                health_pb2.HealthCheckRequest(), timeout=timeout_s
            )
        return res.status == health_pb2.HealthCheckResponse.SERVING
    except grpc.RpcError:
        return False


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else local_addr(Settings.from_env().grpc_addr)
    sys.exit(0 if check(target) else 1)
