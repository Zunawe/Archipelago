"""
Classes and functions related to AP items for Pokemon Emerald
"""
from typing import Dict, FrozenSet, Optional

from BaseClasses import Item, ItemClassification

from .data import BASE_OFFSET, GAME_NAME, data


class PokemonEmeraldItem(Item):
    game: str = GAME_NAME
    tags: FrozenSet[str]

    def __init__(self, name: str, classification: ItemClassification, code: Optional[int], player: int) -> None:
        super().__init__(name, classification, code, player)

        if code is None:
            self.tags = frozenset(["Event"])
        else:
            self.tags = data.items[code - BASE_OFFSET].tags


def create_item_label_to_code_map() -> Dict[str, int]:
    """
    Creates a map from item labels to their AP item id (code)
    """
    label_to_code_map: Dict[str, int] = {}
    for item_value, attributes in data.items.items():
        label_to_code_map[attributes.label] = item_value + BASE_OFFSET

    return label_to_code_map


def get_item_classification(item_code: int) -> ItemClassification:
    """
    Returns the item classification for a given AP item id (code)
    """
    return data.items[item_code - BASE_OFFSET].classification
