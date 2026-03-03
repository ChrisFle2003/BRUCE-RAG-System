#pragma once

#include <array>
#include <cstdint>
#include <vector>

class StateToHierarchyMapper {
public:
    using StateVec = std::array<uint16_t, 7>;

    static uint16_t dim_to_zone(int16_t value, uint16_t num_zones);
    static StateVec map_embedding(const std::vector<int16_t>& embedding);
};
