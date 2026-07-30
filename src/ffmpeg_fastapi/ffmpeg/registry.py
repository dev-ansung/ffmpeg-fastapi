from .base import Feature
from .images_to_video import ImagesToVideoFeature
from .sprite import SpriteFeature

_FEATURES: dict[str, Feature] = {
    "sprite": SpriteFeature(),
    "images_to_video": ImagesToVideoFeature(),
}


def get_feature(name: str) -> Feature | None:
    return _FEATURES.get(name)


def all_features() -> dict[str, Feature]:
    return dict(_FEATURES)
