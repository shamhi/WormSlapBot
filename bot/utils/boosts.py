from enum import Enum


class FreeBoosts(str, Enum):
    TURBO = "turbo"
    ENERGY = "full_energy"


class UpgradableBoosts(str, Enum):
    SLAP = "energy_per_tap"
    ENERGY = "energy_max"
    CHARGE = "energy_per_second"
