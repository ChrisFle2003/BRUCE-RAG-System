#pragma once

#include <atomic>
#include <string>
#include <vector>

class HierarchicalGuard {
public:
    struct Config {
        uint16_t max_depth = 6;
        uint16_t max_pending_jobs = 50;
    };

    HierarchicalGuard();
    explicit HierarchicalGuard(const Config& cfg);

    bool is_whitelisted(const std::string& query_text, const std::vector<std::string>& patterns) const;
    bool can_route(uint16_t depth) const;
    bool reserve_slot();
    void release_slot();

private:
    Config cfg_;
    std::atomic<uint16_t> pending_jobs_;
};
