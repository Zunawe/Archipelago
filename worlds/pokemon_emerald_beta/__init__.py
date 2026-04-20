from .client import PokemonEmeraldClient
from .world import PokemonEmeraldWorld

# Try adding the Pokemon Gen 3 Adjuster
try:
    from worlds._pokemon_gen3_adjuster import __init__
except:
    pass
