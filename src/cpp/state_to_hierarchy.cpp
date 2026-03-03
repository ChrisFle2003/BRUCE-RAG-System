#include "state_to_hierarchy.hpp"

#include <algorithm>
#include <stdexcept>

uint16_t StateToHierarchyMapper::dim_to_zone(int16_t value, uint16_t num_zones) {
    if (num_zones == 0) {
        throw std::invalid_argument("num_zones must be > 0");
    }

    uint32_t normalized = static_cast<uint32_t>(static_cast<int32_t>(value) + 32768);
    uint32_t zone_size = 65536u / num_zones;
    uint32_t zone = normalized / zone_size;

    if (zone >= num_zones) {
        zone = num_zones - 1;
    }

    return static_cast<uint16_t>(zone);
}

StateToHierarchyMapper::StateVec StateToHierarchyMapper::map_embedding(
    const std::vector<int16_t>& embedding
) {
    StateVec state{};
    const std::array<uint16_t, 7> zone_layout = {27, 27, 27, 27, 27, 27, 27};

    for (size_t i = 0; i < state.size(); ++i) {
        int16_t value = 0;
        if (i < embedding.size()) {
            value = embedding[i];
        }
        state[i] = dim_to_zone(value, zone_layout[i]);
    }

    return state;
}
