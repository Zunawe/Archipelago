"""
Functions related to AP regions for Pokemon Emerald (see ./data/regions for region definitions)
"""
from collections import Counter
from typing import Optional, Tuple, List, Dict, Set, Callable

from BaseClasses import Entrance, ItemClassification, Region, MultiWorld

from .data import data
from .items import PokemonEmeraldItem
from .locations import PokemonEmeraldLocation


class PokemonEmeraldRegion(Region):
    shufflable_warps: List[Entrance]

    def __init__(self, name: str, player: int, multiworld: MultiWorld, hint: Optional[str] = None):
        super().__init__(name, player, multiworld, hint)
        self.shufflable_warps = []


def create_regions(multiworld: MultiWorld, player: int) -> None:
    """
    Iterates through regions created from JSON to create regions and adds them to the multiworld.
    Also creates and places events and connects regions via warps and the exits defined in the JSON.
    """
    regions: Dict[str, PokemonEmeraldRegion] = {}

    connections: List[Tuple[str, str, str, bool]] = []
    for region_name, region_data in data.regions.items():
        new_region = PokemonEmeraldRegion(region_name, player, multiworld)

        for event_data in region_data.events:
            event = PokemonEmeraldLocation(player, event_data.name, None, new_region)
            event.place_locked_item(PokemonEmeraldItem(event_data.name, ItemClassification.progression, None, player))
            new_region.locations.append(event)

        for region_exit in region_data.exits:
            connections.append((f"{region_name} -> {region_exit}", region_name, region_exit, False))

        for warp in region_data.warps:
            dest_warp = data.warps[data.warp_map[warp]]
            if dest_warp.parent_region is None:
                continue
            connections.append((warp, region_name, dest_warp.parent_region, True))

        regions[region_name] = new_region

    for name, source, dest, is_warp in connections:
        connection = Entrance(player, name, regions[source])
        regions[source].exits.append(connection)
        connection.connect(regions[dest])

        if is_warp:
            regions[source].shufflable_warps.append(connection)

    menu = PokemonEmeraldRegion("Menu", player, multiworld)
    connection = Entrance(player, "Start Game", menu)
    menu.exits.append(connection)
    connection.connect(regions["REGION_LITTLEROOT_TOWN/MAIN"])
    regions["Menu"] = menu

    multiworld.regions += regions.values()


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
    touched_warps = Counter()
    def rotate_entrances(AB: Entrance, BA: Entrance, CD: Entrance, DC: Entrance):
        # A -- B
        #
        # C -- D
        # to
        # A    B
        # |    |
        # C    D

        AB.connected_region.entrances.remove(AB)
        AB.connect(CD.parent_region)
        multiworld.worlds[player].modified_data.warp_map[AB.name] = CD.name

        BA.connected_region.entrances.remove(BA)
        BA.connect(DC.parent_region)
        multiworld.worlds[player].modified_data.warp_map[CD.name] = AB.name

        CD.connected_region.entrances.remove(CD)
        CD.connect(AB.parent_region)
        multiworld.worlds[player].modified_data.warp_map[BA.name] = DC.name

        DC.connected_region.entrances.remove(DC)
        DC.connect(BA.parent_region)
        multiworld.worlds[player].modified_data.warp_map[DC.name] = BA.name

        touched_warps.update({AB.name: 1})
        touched_warps.update({BA.name: 1})
        touched_warps.update({CD.name: 1})
        touched_warps.update({DC.name: 1})

        def undo():
            rotate_entrances(AB, CD, BA, DC)
            touched_warps.subtract({AB.name: 2})
            touched_warps.subtract({BA.name: 2})
            touched_warps.subtract({CD.name: 2})
            touched_warps.subtract({DC.name: 2})

        return undo

    all_regions: Set[PokemonEmeraldRegion] = set(multiworld.get_regions(player))

    group_size = 1
    num_swaps = 0
    num_attempts = 0
    while num_swaps < 5000 and num_attempts < 10000:
        num_attempts += 1

        undo_stack: List[Callable[[], None]] = []
        for _ in range(group_size):
            AB = multiworld.get_entrance(multiworld.worlds[player].random.choice(list(multiworld.worlds[player].modified_data.warps)), player)
            if multiworld.worlds[player].modified_data.warp_map[AB.name] is None:
                continue
            BA = multiworld.get_entrance(multiworld.worlds[player].modified_data.warp_map[AB.name], player)
            if multiworld.worlds[player].modified_data.warp_map[BA.name] != AB.name:
                continue

            CD = multiworld.get_entrance(multiworld.worlds[player].random.choice(list(multiworld.worlds[player].modified_data.warps)), player)
            if CD.name == AB.name or CD.name == BA.name or multiworld.worlds[player].modified_data.warp_map[CD.name] is None:
                continue
            DC = multiworld.get_entrance(multiworld.worlds[player].modified_data.warp_map[CD.name], player)
            if multiworld.worlds[player].modified_data.warp_map[DC.name] != CD.name:
                continue

            if AB.name in unrandomizable_warps or BA.name in unrandomizable_warps or\
                    CD.name in unrandomizable_warps or DC.name in unrandomizable_warps:
                continue

            undo_stack.append(rotate_entrances(AB, BA, CD, DC))

        if len(all_regions - multiworld.get_all_state(False).reachable_regions[player]) == 0:
            num_swaps += group_size
            group_size += 1
        else:
            for undo in reversed(undo_stack):
                undo()

            group_size = max(int(group_size / 2), 1)

            assert(len(all_regions - multiworld.get_all_state(False).reachable_regions[player]) == 0)

    print(f"{len(list(filter(lambda count: count > 0, touched_warps.values())))} / {len(list(filter(lambda warp: (not warp[1].is_one_way) and (warp[0] not in unrandomizable_warps), data.warps.items())))} two-way warps were shuffled")
