#include "ipc_client.hpp"

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <thread>

#include <unistd.h>

IPCClient::IPCClient()
    : IPCClient(Config{}) {}

IPCClient::IPCClient(const Config& cfg)
    : cfg_(cfg), pending_jobs_(0) {}

IPCClient::FireResult IPCClient::fire(const Route& route, const std::string& payload) {
    int current = pending_jobs_.load(std::memory_order_relaxed);
    while (current < cfg_.max_pending_jobs) {
        if (pending_jobs_.compare_exchange_weak(current, current + 1, std::memory_order_relaxed)) {
            break;
        }
    }

    if (current >= cfg_.max_pending_jobs) {
        return FireResult::BACKPRESSURE;
    }

    std::thread([this, route, payload]() {
        char tmp_name[] = "/tmp/bruce_payload_XXXXXX.json";
        int fd = mkstemps(tmp_name, 5);
        if (fd >= 0) {
            close(fd);
            std::ofstream out(tmp_name);
            out << payload;
            out.close();

            std::string cmd = "curl -s -o /dev/null -m 5 -X POST '" + route.endpoint +
                "/calc' -H 'Content-Type: application/json' --data-binary @" + tmp_name;
            std::system(cmd.c_str());
            std::remove(tmp_name);
        }

        pending_jobs_.fetch_sub(1, std::memory_order_relaxed);
    }).detach();

    return FireResult::ACCEPTED;
}

int IPCClient::pending_jobs() const {
    return pending_jobs_.load(std::memory_order_relaxed);
}
