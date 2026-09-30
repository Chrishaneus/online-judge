"""Logs every unary RPC: method, status code, duration and the x-request-id set by oj-rest."""

import logging
import time

import grpc

log = logging.getLogger("app.access")

QUIET_PREFIX = "/grpc.health.v1.Health/"


class LoggingInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(self, continuation, handler_call_details):
        handler = await continuation(handler_call_details)
        if handler is None or handler.unary_unary is None:
            return handler
        method = handler_call_details.method
        metadata = dict(handler_call_details.invocation_metadata or ())
        request_id = metadata.get("x-request-id", "-")
        inner = handler.unary_unary
        level = logging.DEBUG if method.startswith(QUIET_PREFIX) else logging.INFO

        async def logged(request, context):
            start = time.perf_counter()
            code = grpc.StatusCode.OK
            try:
                return await inner(request, context)
            except grpc.aio.AbortError:
                code = context.code() or grpc.StatusCode.UNKNOWN
                raise
            except BaseException:
                code = grpc.StatusCode.UNKNOWN
                raise
            finally:
                ms = (time.perf_counter() - start) * 1000
                name = code.name if isinstance(code, grpc.StatusCode) else str(code)
                log.log(level, "%s %s %.1fms request_id=%s", method, name, ms, request_id)

        return grpc.unary_unary_rpc_method_handler(
            logged,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
