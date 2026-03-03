#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include <libpq-fe.h>

#include "hierarchical_guard.hpp"
#include "ipc_client.hpp"
#include "routing_table.hpp"
#include "state_to_hierarchy.hpp"

namespace {

std::string get_env(const char* key, const std::string& fallback) {
    const char* value = std::getenv(key);
    if (value == nullptr || std::strlen(value) == 0) {
        return fallback;
    }
    return value;
}

std::string build_conninfo() {
    std::ostringstream oss;
    oss << "host=" << get_env("DB_HOST", "localhost")
        << " port=" << get_env("DB_PORT", "5432")
        << " dbname=" << get_env("DB_NAME", "bruce_rag")
        << " user=" << get_env("DB_USER", "bruce")
        << " password=" << get_env("DB_PASSWORD", "secretpassword");
    return oss.str();
}

std::vector<std::string> load_whitelist_patterns(const std::string& conninfo) {
    std::vector<std::string> patterns;

    PGconn* conn = PQconnectdb(conninfo.c_str());
    if (PQstatus(conn) != CONNECTION_OK) {
        PQfinish(conn);
        return patterns;
    }

    PGresult* res = PQexec(conn, "SELECT pattern FROM whitelist WHERE match_type = 'exact'");
    if (PQresultStatus(res) == PGRES_TUPLES_OK) {
        int rows = PQntuples(res);
        for (int i = 0; i < rows; ++i) {
            patterns.push_back(PQgetvalue(res, i, 0));
        }
    }

    PQclear(res);
    PQfinish(conn);
    return patterns;
}

std::vector<int16_t> embed_query_stub(const std::string& query) {
    std::vector<int16_t> out(64, 0);
    std::hash<std::string> hasher;

    for (size_t i = 0; i < out.size(); ++i) {
        size_t h = hasher(query + ":" + std::to_string(i));
        int16_t value = static_cast<int16_t>(static_cast<int>(h % 65536) - 32768);
        out[i] = value;
    }

    return out;
}

int map_state_to_bibliothek_id(const StateToHierarchyMapper::StateVec& state) {
    const int offset = static_cast<int>(state[0]) * 37;
    return 2000 + std::min(offset, 999);
}

std::string json_escape(const std::string& value) {
    std::string escaped;
    escaped.reserve(value.size() + 8);
    for (char c : value) {
        switch (c) {
            case '"': escaped += "\\\""; break;
            case '\\': escaped += "\\\\"; break;
            case '\n': escaped += "\\n"; break;
            case '\r': escaped += "\\r"; break;
            case '\t': escaped += "\\t"; break;
            default: escaped += c; break;
        }
    }
    return escaped;
}

std::string build_payload(
    const std::string& query,
    const StateToHierarchyMapper::StateVec& state,
    const std::string& route_name
) {
    std::ostringstream oss;
    oss << "{";
    oss << "\"request_id\":\"cpp-" << std::chrono::steady_clock::now().time_since_epoch().count() << "\",";
    oss << "\"trace_id\":\"cpp-trace\",";
    oss << "\"job_id\":\"00000000-0000-0000-0000-000000000001\",";
    oss << "\"route_name\":\"" << json_escape(route_name) << "\",";
    oss << "\"state_vec\":["
        << state[0] << "," << state[1] << "," << state[2] << ","
        << state[3] << "," << state[4] << "," << state[5] << "," << state[6] << "],";
    oss << "\"context\":{\"chunks\":[{\"seite_id\":0,\"content\":\""
        << json_escape(query)
        << "\",\"similarity\":0.8}]},";
    oss << "\"task\":{\"type\":\"extract_facts\",\"language\":\"de\",\"max_tokens\":512}";
    oss << "}";
    return oss.str();
}

int run_benchmark() {
    constexpr int iterations = 500000;
    auto started = std::chrono::high_resolution_clock::now();

    volatile uint16_t sink = 0;
    for (int i = 0; i < iterations; ++i) {
        sink ^= StateToHierarchyMapper::dim_to_zone(static_cast<int16_t>(i % 65536 - 32768), 27);
    }

    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::high_resolution_clock::now() - started
    );
    std::cout << "Benchmark complete: " << iterations << " dim_to_zone ops in "
              << elapsed.count() << "ms\n";
    std::cout << "Sink=" << sink << "\n";
    return 0;
}

}  // namespace

int main(int argc, char* argv[]) {
    if (argc > 1 && std::string(argv[1]) == "--benchmark") {
        return run_benchmark();
    }

    const std::string query = (argc > 1) ? argv[1] : "default";
    const std::string conninfo = build_conninfo();

    HierarchicalGuard guard({6, static_cast<uint16_t>(std::stoi(get_env("MAX_PENDING_JOBS", "50")))});
    const auto whitelist = load_whitelist_patterns(conninfo);

    if (!guard.is_whitelisted(query, whitelist)) {
        std::cerr << "Query blocked by whitelist\n";
        return 2;
    }

    const auto embedding = embed_query_stub(query);
    const auto state = StateToHierarchyMapper::map_embedding(embedding);
    const int bibliothek_id = map_state_to_bibliothek_id(state);

    RoutingTable routing;
    if (!routing.reload_from_database(conninfo)) {
        std::cerr << "Routing load failed; using built-in fallback route\n";
    }

    const auto routes = routing.resolve(bibliothek_id);
    IPCClient ipc({std::stoi(get_env("MAX_PENDING_JOBS", "50"))});

    for (const auto& route : routes) {
        const auto payload = build_payload(query, state, route.name);
        const auto result = ipc.fire(route, payload);
        if (result == IPCClient::FireResult::BACKPRESSURE) {
            std::cerr << "Backpressure: too many pending jobs\n";
            return 3;
        }
    }

    std::cout << "Dispatched query to " << routes.size() << " route(s)."
              << " state=[" << state[0] << "," << state[1] << "," << state[2] << ","
              << state[3] << "," << state[4] << "," << state[5] << "," << state[6] << "]"
              << " bib_id=" << bibliothek_id << "\n";

    return 0;
}
