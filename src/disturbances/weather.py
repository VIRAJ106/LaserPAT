import numpy as np

WEATHER_PRESETS = {
    "clear": {"sigma": 0, "poisson": False, "sp": 0.0, "attenuation_coef": 0.001},
    "haze": {"sigma": 5, "poisson": True, "sp": 0.01, "attenuation_coef": 0.01},
    "fog": {"sigma": 15, "poisson": True, "sp": 0.05, "attenuation_coef": 0.05},
    "rain": {"sigma": 10, "poisson": True, "sp": 0.1, "attenuation_coef": 0.02},
    "low_light": {"sigma": 25, "poisson": True, "sp": 0.02, "attenuation_coef": 0.001},
}

def get_weather_preset(preset_name: str) -> dict:
    return WEATHER_PRESETS.get(preset_name, WEATHER_PRESETS["clear"])

