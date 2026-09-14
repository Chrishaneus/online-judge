package main

import (
	"net"
	"testing"

	"google.golang.org/grpc"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
)

func TestDialTarget(t *testing.T) {
	cases := map[string]string{
		":50052":          "passthrough:///127.0.0.1:50052",
		"0.0.0.0:50052":   "passthrough:///127.0.0.1:50052",
		"[::]:50052":      "passthrough:///127.0.0.1:50052",
		"dao:50052":       "passthrough:///dao:50052",
		"127.0.0.1:12345": "passthrough:///127.0.0.1:12345",
	}
	for in, want := range cases {
		if got := dialTarget(in); got != want {
			t.Errorf("dialTarget(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestHealthcheck(t *testing.T) {
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	hs := health.NewServer()
	srv := grpc.NewServer()
	healthpb.RegisterHealthServer(srv, hs)
	go func() { _ = srv.Serve(lis) }()
	defer srv.Stop()
	addr := lis.Addr().String()

	hs.SetServingStatus("", healthpb.HealthCheckResponse_SERVING)
	if err := healthcheck(addr); err != nil {
		t.Fatalf("serving: %v", err)
	}
	hs.SetServingStatus("", healthpb.HealthCheckResponse_NOT_SERVING)
	if err := healthcheck(addr); err == nil {
		t.Fatal("not serving must fail")
	}
	srv.Stop()
	if err := healthcheck(addr); err == nil {
		t.Fatal("unreachable must fail")
	}
}
