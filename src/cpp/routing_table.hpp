#pragma once

#include <string>
#include <vector>

struct Route {
    int route_id = 3;
    std::string name = "BRUCE";
    std::string endpoint = "http://localhost:8003";
    int priority = 1;
    float confidence_threshold = 0.70F;
    int bib_range_start = 2000;
    int bib_range_end = 2999;
};

class RoutingTable {
public:
    bool reload_from_database(const std::string& conninfo);
    std::vector<Route> resolve(int bibliothek_id) const;

private:
    std::vector<Route> routes_;
};
