#pragma once

#include <atomic>
#include <string>

#include "routing_table.hpp"

class IPCClient {
public:
    struct Config {
        int max_pending_jobs = 50;
    };

    enum class FireResult {
        ACCEPTED,
        BACKPRESSURE,
    };

    IPCClient();
    explicit IPCClient(const Config& cfg);

    FireResult fire(const Route& route, const std::string& payload);
    int pending_jobs() const;

private:
    Config cfg_;
    std::atomic<int> pending_jobs_;
};
