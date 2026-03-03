#include "hierarchical_guard.hpp"

HierarchicalGuard::HierarchicalGuard()
    : HierarchicalGuard(Config{}) {}

HierarchicalGuard::HierarchicalGuard(const Config& cfg)
    : cfg_(cfg), pending_jobs_(0) {}

bool HierarchicalGuard::is_whitelisted(
    const std::string& query_text,
    const std::vector<std::string>& patterns
) const {
    if (patterns.empty()) {
        return true;
    }

    for (const auto& pattern : patterns) {
        if (pattern == "__ALLOW_ALL__") {
            return true;
        }
        if (query_text == pattern) {
            return true;
        }
    }

    return false;
}

bool HierarchicalGuard::can_route(uint16_t depth) const {
    if (depth > cfg_.max_depth) {
        return false;
    }
    return pending_jobs_.load(std::memory_order_relaxed) < cfg_.max_pending_jobs;
}

bool HierarchicalGuard::reserve_slot() {
    uint16_t current = pending_jobs_.load(std::memory_order_relaxed);
    while (current < cfg_.max_pending_jobs) {
        if (pending_jobs_.compare_exchange_weak(current, current + 1, std::memory_order_relaxed)) {
            return true;
        }
    }
    return false;
}

void HierarchicalGuard::release_slot() {
    uint16_t current = pending_jobs_.load(std::memory_order_relaxed);
    while (current > 0) {
        if (pending_jobs_.compare_exchange_weak(current, current - 1, std::memory_order_relaxed)) {
            return;
        }
    }
}
