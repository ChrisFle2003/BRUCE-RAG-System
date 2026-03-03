#include "routing_table.hpp"

#include <algorithm>
#include <cstdlib>
#include <iostream>

#include <libpq-fe.h>

bool RoutingTable::reload_from_database(const std::string& conninfo) {
    PGconn* conn = PQconnectdb(conninfo.c_str());
    if (PQstatus(conn) != CONNECTION_OK) {
        std::cerr << "[routing] DB connect failed: " << PQerrorMessage(conn) << "\n";
        PQfinish(conn);
        return false;
    }

    const char* sql = R"SQL(
SELECT
    COALESCE((route->>'route_id')::int, 3) AS route_id,
    COALESCE(route->>'name', 'BRUCE') AS name,
    COALESCE(route->>'endpoint', 'http://localhost:8003') AS endpoint,
    COALESCE((route->>'priority')::int, 1) AS priority,
    COALESCE((route->>'confidence_threshold')::float, 0.70) AS confidence_threshold,
    COALESCE((route->'bibliothek_id_range'->>0)::int, 2000) AS bib_range_start,
    COALESCE((route->'bibliothek_id_range'->>1)::int, 2999) AS bib_range_end
FROM routing_versions rv,
LATERAL jsonb_array_elements(rv.config_json->'routes') AS route
WHERE rv.is_active = TRUE
ORDER BY priority ASC;
)SQL";

    PGresult* res = PQexec(conn, sql);
    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
        std::cerr << "[routing] query failed: " << PQerrorMessage(conn) << "\n";
        PQclear(res);
        PQfinish(conn);
        return false;
    }

    std::vector<Route> loaded;
    int rows = PQntuples(res);
    for (int i = 0; i < rows; ++i) {
        Route route;
        route.route_id = std::atoi(PQgetvalue(res, i, 0));
        route.name = PQgetvalue(res, i, 1);
        route.endpoint = PQgetvalue(res, i, 2);
        route.priority = std::atoi(PQgetvalue(res, i, 3));
        route.confidence_threshold = static_cast<float>(std::atof(PQgetvalue(res, i, 4)));
        route.bib_range_start = std::atoi(PQgetvalue(res, i, 5));
        route.bib_range_end = std::atoi(PQgetvalue(res, i, 6));
        loaded.push_back(route);
    }

    PQclear(res);
    PQfinish(conn);

    if (loaded.empty()) {
        return false;
    }

    std::sort(loaded.begin(), loaded.end(), [](const Route& a, const Route& b) {
        return a.priority < b.priority;
    });

    routes_ = std::move(loaded);
    return true;
}

std::vector<Route> RoutingTable::resolve(int bibliothek_id) const {
    std::vector<Route> selected;

    for (const auto& route : routes_) {
        if (bibliothek_id >= route.bib_range_start && bibliothek_id <= route.bib_range_end) {
            selected.push_back(route);
        }
    }

    if (selected.empty()) {
        selected.push_back(Route{});
    }

    return selected;
}
