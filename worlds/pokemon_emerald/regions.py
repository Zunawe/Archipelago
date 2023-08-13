"""
Functions related to AP regions for Pokemon Emerald (see ./data/regions for region definitions)
"""
from collections import Counter
from typing import Tuple, List, Set, Callable

from BaseClasses import CollectionState, Entrance, ItemClassification, Region, MultiWorld

from .data import data
from .items import PokemonEmeraldItem
from .locations import PokemonEmeraldLocation


def create_regions(multiworld: MultiWorld, player: int) -> None:
    """
    Iterates through regions created from JSON to create regions and adds them to the multiworld.
    Also creates and places events and connects regions via warps and the exits defined in the JSON.
    """
    connections: List[Tuple[str, str, str, bool]] = []
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


_unrandomizable_warps = {
    "MAP_LITTLEROOT_TOWN:1/MAP_LITTLEROOT_TOWN_BRENDANS_HOUSE_1F:1",
    "MAP_LITTLEROOT_TOWN_BRENDANS_HOUSE_1F:0,1/MAP_LITTLEROOT_TOWN:1",
    "MAP_LITTLEROOT_TOWN_BRENDANS_HOUSE_1F:2/MAP_LITTLEROOT_TOWN_BRENDANS_HOUSE_2F:0",
    "MAP_LITTLEROOT_TOWN_BRENDANS_HOUSE_2F:0/MAP_LITTLEROOT_TOWN_BRENDANS_HOUSE_1F:2",
    "MAP_LITTLEROOT_TOWN:0/MAP_LITTLEROOT_TOWN_MAYS_HOUSE_1F:1",
    "MAP_LITTLEROOT_TOWN_MAYS_HOUSE_1F:0,1/MAP_LITTLEROOT_TOWN:0",
    "MAP_LITTLEROOT_TOWN_MAYS_HOUSE_1F:2/MAP_LITTLEROOT_TOWN_MAYS_HOUSE_2F:0",
    "MAP_LITTLEROOT_TOWN_MAYS_HOUSE_2F:0/MAP_LITTLEROOT_TOWN_MAYS_HOUSE_1F:2",

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
    "MAP_EVER_GRANDE_CITY_HALL4:0/MAP_EVER_GRANDE_CITY_DRAKES_ROOM:1",
    "MAP_EVER_GRANDE_CITY_CHAMPIONS_ROOM:0/MAP_EVER_GRANDE_CITY_HALL4:1",
    "MAP_EVER_GRANDE_CITY_HALL4:1/MAP_EVER_GRANDE_CITY_CHAMPIONS_ROOM:0",
    "MAP_EVER_GRANDE_CITY_CHAMPIONS_ROOM:1/MAP_EVER_GRANDE_CITY_HALL_OF_FAME:0"
    "MAP_EVER_GRANDE_CITY_HALL_OF_FAME:0/MAP_EVER_GRANDE_CITY_CHAMPIONS_ROOM:1"
}


def shuffle_warps(multiworld: MultiWorld, player: int):
    """
    Randomizes two-way warps while maintaining a fully connected map.

    Until 1000 swaps have been made, every iteration of a loop, two pairs of warps are chosen randomly and have their
    destinations swapped. For example, the pairs (A, B) and (C, D) are chosen where A leads to B, B leads to A, C leads
    to D, and D leads to C. The destinations are "rotated" so that the resulting pairs look like (A, D) and (C, B).
    Then, check to see whether any regions were made unreachable by the rotation. If so, undo the changes.

    To potentially cut down on the number of times we must check that every region is reachable, the function tries
    to do multiple rotations before checking. The first "group size" is 1, so one rotation is made before checking
    reachability. Every time the rotation is successful in maintaining a connected graph, increase the group size by 1.
    So if group size is 5, do 5 rotations before checking reachability. If the graph isn't fully connected, undo all 5.
    Every time the rotation results in a graph that isn't fully connected, divide group size by 2. Growing linearly
    while shrinking exponentially ensures we're usually at a size where making swaps does not result in unreachable
    regions. Increasing group size makes it more likely we will have unreachable regions the next time we check, but
    if we're successful enough times in making multiple rotations before checking connectedness, it should save time
    overall.

    In the case where the graph is already very unlikely to be connected after a rotation, we don't want to have this
    group rotation method put us in a situation where every time we have a successful swap, we try to swap more next
    time and always fail. So group swaps will only come into effect after a few successful swaps in a row. The idea is
    to create a self-regulating system that saves reachability checks when it can, but doesn't waste too many swaps to
    do so.

    Instead of only rotating 2 pairs of warps, we can rotate an arbitrary amount (see the docstring for
    `rotate_entrances`). This should increase the variety of possible resulting graphs, but may result in more
    instances of unreachable regions. Here, the number of pairs is random on the interval [2, 5].

    To increase the "perceived" randomness of the resulting graph, the candidates for randomly chosen warps are heavily
    biased toward warps that have been involved in fewer swaps. Every failed swap, the next attempt will involve
    warps that have been involved in one more previous swap. Every successful swap, the ceiling is reset to the average
    number of times any given warp has been swapped. This makes it much less likely that there will be untouched
    swaps after randomization, even without a large number of total swaps.
    """
    # Counter keeps track of which warps can be randomized and how many times each one has been involved in a swap
    warp_swap_counter: Counter[str] = Counter({
        warp: 0
        for warp in multiworld.worlds[player].modified_data.warp_destinations.keys()
        if warp not in _unrandomizable_warps
    })

    def rotate_entrances(*entrance_pairs: Tuple[Entrance, Entrance]) -> Callable[[], None]:
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
            multiworld.worlds[player].modified_data.warp_map[AB.name] = f"{AB.name.split('/')[0]}/{BA_next.name.split('/')[0]}"

            BA.connected_region.entrances.remove(BA)
            BA.connect(AB_prev.parent_region)
            multiworld.worlds[player].modified_data.warp_destinations[BA.name] = AB_prev.name
            multiworld.worlds[player].modified_data.warp_map[BA.name] = f"{BA.name.split('/')[0]}/{AB_prev.name.split('/')[0]}"

            warp_swap_counter.update({AB.name: 1})
            warp_swap_counter.update({BA.name: 1})

        def undo():
            for AB, BA in entrance_pairs:
                AB.connected_region.entrances.remove(AB)
                AB.connect(BA.parent_region)
                multiworld.worlds[player].modified_data.warp_destinations[AB.name] = BA.name
                multiworld.worlds[player].modified_data.warp_map[AB.name] = f"{AB.name.split('/')[0]}/{BA.name.split('/')[0]}"

                BA.connected_region.entrances.remove(BA)
                BA.connect(AB.parent_region)
                multiworld.worlds[player].modified_data.warp_destinations[BA.name] = AB.name
                multiworld.worlds[player].modified_data.warp_map[BA.name] = f"{BA.name.split('/')[0]}/{AB.name.split('/')[0]}"

                warp_swap_counter.subtract({AB.name: 1})
                warp_swap_counter.subtract({BA.name: 1})

        return undo

    all_regions: Set[Region] = set(multiworld.get_regions(player))

    def is_map_fully_connected() -> bool:
        world = multiworld.worlds[player]
        all_state = CollectionState(multiworld)

        for item in multiworld.itempool:
            if item.player == player:
                world.collect(all_state, item)

        # Enabling either HM/Badge shuffle seems to increase warp rando time by ~80% because of this
        if world.hm_shuffle_info is not None:
            for _, item in world.hm_shuffle_info:
                world.collect(all_state, item)

        if world.badge_shuffle_info is not None:
            for _, item in world.badge_shuffle_info:
                world.collect(all_state, item)

        if world.hm_shuffle_info is not None or world.badge_shuffle_info is not None:
            all_state.sweep_for_events()

        reachable_regions = all_state.reachable_regions[player]

        assert not len(reachable_regions) == len(all_regions) ^ len(all_regions - reachable_regions) == 0

        return len(reachable_regions) == len(all_regions)

    group_size = 1  # Controls the number of rotations to do before checking connectedness
    max_candidate_swaps = 0  # The maximum number of times a warp can have already been swapped before being considered
    num_swaps = 0  # Tracks the number of warps that have been swapped
    panic_counter = 0  # Breaks out of loops that could otherwise be infinite or very long
    while num_swaps < 1000 and panic_counter < 10000:
        panic_counter += 1

        # A list of warps we're allowed to swap this iteration
        candidate_warps = [
            warp
            for warp in warp_swap_counter
            if warp_swap_counter[warp] <= max_candidate_swaps
        ]

        undo_stack: List[Callable[[], None]] = []
        for _i in range(group_size if group_size > 3 else 1):
            warps_in_rotation: Set[str] = set()
            pairs: List[Tuple[Entrance, Entrance]] = []

            # Varies the number of pairs in the rotation for more diverse outcomes
            num_pairs = multiworld.worlds[player].random.randrange(2, 6)

            for _j in range(num_pairs):
                while panic_counter < 10000:
                    panic_counter += 1
                    AB = multiworld.get_entrance(multiworld.worlds[player].random.choice(candidate_warps), player)
                    BA = multiworld.get_entrance(multiworld.worlds[player].modified_data.warp_destinations[AB.name], player)

                    assert not AB.name in _unrandomizable_warps
                    assert not BA.name in _unrandomizable_warps

                    if multiworld.worlds[player].modified_data.warp_destinations[BA.name] != AB.name:
                        continue
                    if AB.name in warps_in_rotation or BA.name in warps_in_rotation:
                        continue

                    pairs.append((AB, BA))
                    warps_in_rotation |= {AB.name, BA.name}
                    break

            undo_stack.append(rotate_entrances(*pairs))

        # If all regions are reachable, try doing more swaps next time before checking connectedness and reset the limit
        # on which warps should be swapped first. Otherwise, undo the rotations we've done in reverse order, cut the
        # number of swaps next time, and increase the pool of warps to include more warps that have already been
        # swapped.
        if is_map_fully_connected():
            num_swaps += group_size
            group_size += 1
            max_candidate_swaps = int(warp_swap_counter.total() / len(warp_swap_counter))
        else:
            for undo in reversed(undo_stack):
                undo()

            assert is_map_fully_connected()

            group_size = max(int(group_size / 2), 1)
            max_candidate_swaps += 1
