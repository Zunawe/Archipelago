"""
Functions related to AP regions for Pokemon Emerald (see ./data/regions for region definitions)
"""
from collections import Counter
from typing import Callable, List, Set, Tuple

from BaseClasses import Entrance, ItemClassification, Region, MultiWorld

from .data import data
from .items import PokemonEmeraldItem
from .locations import PokemonEmeraldLocation


def create_regions(multiworld: MultiWorld, player: int) -> None:
    """
    Iterates through regions created from JSON to create regions and adds them to the multiworld.
    Also creates and places events and connects regions via warps and the exits defined in the JSON.
    """
    connections = []
    for region_name, region_data in data.regions.items():
        new_region = Region(region_name, player, multiworld)

        for event_data in region_data.events:
            event = PokemonEmeraldLocation(player, event_data.name, None, new_region)
            event.place_locked_item(PokemonEmeraldItem(event_data.name, ItemClassification.progression, None, player))
            new_region.locations.append(event)

        for region_exit in region_data.exits:
            connections.append((f"{region_name} -> {region_exit}", region_name, region_exit))

        for warp in region_data.warps:
            dest_warp = data.warps[data.warp_destinations[warp]]
            if dest_warp.parent_region is None:
                continue
            connections.append((warp, region_name, dest_warp.parent_region))

        multiworld.regions.append(new_region)

    for name, source, dest in connections:
        multiworld.get_region(source, player).connect(multiworld.get_region(dest, player), name)

    menu = Region("Menu", player, multiworld)
    menu.connect(multiworld.get_region("REGION_LITTLEROOT_TOWN/MAIN", player), "Start Game")

    multiworld.regions.append(menu)


unrandomizable_warps = {
    "MAP_EVER_GRANDE_CITY_POKEMON_LEAGUE_1F:2,3/MAP_EVER_GRANDE_CITY_HALL5:0",
    "MAP_EVER_GRANDE_CITY_HALL5:0,2,3/MAP_EVER_GRANDE_CITY_POKEMON_LEAGUE_1F:2",
    "MAP_EVER_GRANDE_CITY_HALL5:1/MAP_EVER_GRANDE_CITY_SIDNEYS_ROOM:0",
    "MAP_EVER_GRANDE_CITY_SIDNEYS_ROOM:0/MAP_EVER_GRANDE_CITY_HALL5:1",
    "MAP_EVER_GRANDE_CITY_SIDNEYS_ROOM:1/MAP_EVER_GRANDE_CITY_HALL1:0",
    "MAP_EVER_GRANDE_CITY_HALL1:0,2,3/MAP_EVER_GRANDE_CITY_SIDNEYS_ROOM:1",
    "MAP_EVER_GRANDE_CITY_HALL1:1/MAP_EVER_GRANDE_CITY_PHOEBES_ROOM:0",
    "MAP_EVER_GRANDE_CITY_PHOEBES_ROOM:0/MAP_EVER_GRANDE_CITY_HALL1:1",
    "MAP_EVER_GRANDE_CITY_PHOEBES_ROOM:1/MAP_EVER_GRANDE_CITY_HALL2:0",
    "MAP_EVER_GRANDE_CITY_HALL2:0,2,3/MAP_EVER_GRANDE_CITY_PHOEBES_ROOM:1",
    "MAP_EVER_GRANDE_CITY_HALL2:1/MAP_EVER_GRANDE_CITY_GLACIAS_ROOM:0",
    "MAP_EVER_GRANDE_CITY_GLACIAS_ROOM:0/MAP_EVER_GRANDE_CITY_HALL2:1",
    "MAP_EVER_GRANDE_CITY_GLACIAS_ROOM:1/MAP_EVER_GRANDE_CITY_HALL3:0",
    "MAP_EVER_GRANDE_CITY_HALL3:0,2,3/MAP_EVER_GRANDE_CITY_GLACIAS_ROOM:1",
    "MAP_EVER_GRANDE_CITY_HALL3:1/MAP_EVER_GRANDE_CITY_DRAKES_ROOM:0",
    "MAP_EVER_GRANDE_CITY_DRAKES_ROOM:0/MAP_EVER_GRANDE_CITY_HALL3:1",
    "MAP_EVER_GRANDE_CITY_DRAKES_ROOM:1/MAP_EVER_GRANDE_CITY_HALL4:0",
    "MAP_EVER_GRANDE_CITY_CHAMPIONS_ROOM:0/MAP_EVER_GRANDE_CITY_HALL4:1",
    "MAP_EVER_GRANDE_CITY_CHAMPIONS_ROOM:1/MAP_EVER_GRANDE_CITY_HALL_OF_FAME:0"
}


def shuffle_warps(multiworld: MultiWorld, player: int):
    # Counter keeps track of which warps can be randomized and how many times each one has been involved in a swap
    warp_swap_counter: Counter[str] = Counter({
        warp: 0
        for warp in multiworld.worlds[player].modified_data.warp_destinations.keys()
        if warp not in unrandomizable_warps
    })

    def rotate_entrances(*entrance_pairs: Tuple[Entrance, Entrance]):
        """
        For two-way warps, shift their connections over by one in the list of pairs. For example:

        A   C   E
        |   |   |
        B   D   F

        becomes

        A   C   E
        |   |   |
        D   F   B

        Returns a function which undoes the rotation.
        """

        for i, (AB, BA) in enumerate(entrance_pairs):
            BA_next = entrance_pairs[(i + 1) % len(entrance_pairs)][1]
            AB_prev = entrance_pairs[(i - 1) % len(entrance_pairs)][0]

            AB.connected_region.entrances.remove(AB)
            AB.connect(BA_next.parent_region)
            multiworld.worlds[player].modified_data.warp_destinations[AB.name] = BA_next.name
            multiworld.worlds[player].modified_data.warp_map[AB.name] = f"{AB.name.split('/')[0]}/{BA_next.name.split('/')[1]}"

            BA.connected_region.entrances.remove(BA)
            BA.connect(AB_prev.parent_region)
            multiworld.worlds[player].modified_data.warp_destinations[BA.name] = AB_prev.name
            multiworld.worlds[player].modified_data.warp_map[BA.name] = f"{BA.name.split('/')[0]}/{AB_prev.name.split('/')[1]}"

            warp_swap_counter.update({AB.name: 1})
            warp_swap_counter.update({BA.name: 1})

        def undo():
            for AB, BA in entrance_pairs:
                AB.connected_region.entrances.remove(AB)
                AB.connect(BA.parent_region)
                multiworld.worlds[player].modified_data.warp_destinations[AB.name] = BA.name
                multiworld.worlds[player].modified_data.warp_map[AB.name] = f"{AB.name.split('/')[0]}/{BA.name.split('/')[1]}"

                BA.connected_region.entrances.remove(BA)
                BA.connect(AB.parent_region)
                multiworld.worlds[player].modified_data.warp_destinations[BA.name] = AB.name
                multiworld.worlds[player].modified_data.warp_map[BA.name] = f"{BA.name.split('/')[0]}/{AB.name.split('/')[1]}"

                warp_swap_counter.subtract({AB.name: 1})
                warp_swap_counter.subtract({BA.name: 1})

        return undo

    all_regions: Set[Region] = set(multiworld.get_regions(player))

    group_size = 1  # Controls the number of rotations to do before checking connectedness
    max_candidate_swaps = 0  # The maximum number of times a warp can have already been swapped before being considered
    num_swaps = 0  # Tracks the number of warps that have been swapped
    panic_counter = 0  # Breaks out of loops that could otherwise be infinite or very long
    while num_swaps < 1000 and panic_counter < 10000:
        panic_counter += 1

        # A list of warps we're allowed to swap this iteration
        # sorted for reproducibility
        candidate_warps = sorted([
            warp
            for warp in warp_swap_counter.keys()
            if warp_swap_counter[warp] <= max_candidate_swaps
        ])

        undo_stack: List[Callable[[], None]] = []
        for _i in range(group_size):
            warps_in_rotation: Set[str] = set()
            pairs: List[Tuple[Entrance, Entrance]] = []

            # Varies the number of pairs in the rotation for more diverse outcomes
            num_pairs = multiworld.worlds[player].random.randrange(2, 5)

            for _j in range(num_pairs):
                while True and panic_counter < 10000:
                    panic_counter += 1
                    AB = multiworld.get_entrance(multiworld.worlds[player].random.choice(candidate_warps), player)
                    BA = multiworld.get_entrance(multiworld.worlds[player].modified_data.warp_destinations[AB.name], player)

                    if multiworld.worlds[player].modified_data.warp_destinations[BA.name] != AB.name:
                        continue
                    if AB.name in warps_in_rotation or BA.name in warps_in_rotation:
                        continue

                    pairs.append((AB, BA))
                    break

                warps_in_rotation |= {AB.name, BA.name}

            undo_stack.append(rotate_entrances(*pairs))

        # If all regions are reachable, try doing more swaps next time before checking connectedness and reset the limit
        # on which warps should be swapped first. Otherwise, undo the rotations we've done in reverse order, cut the
        # number of swaps next time, and increase the pool of warps to include more warps that have already been
        # swapped.
        if len(all_regions - multiworld.get_all_state(False).reachable_regions[player]) == 0:
            num_swaps += group_size
            group_size += 1
            max_candidate_swaps = 0
        else:
            for undo in reversed(undo_stack):
                undo()
            assert(len(all_regions - multiworld.get_all_state(False).reachable_regions[player]) == 0)

            group_size = max(int(group_size / 2), 1)
            max_candidate_swaps += 1
