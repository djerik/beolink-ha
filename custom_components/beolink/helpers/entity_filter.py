"""Entity filtering mixin for BeoLink integration."""

from custom_components.beolink.const import MODE_EXCLUDE, MODE_INCLUDE


class EntityFilterMixin:
    """Mixin for entity include/exclude filtering."""

    include_entities: list[str]
    exclude_entities: list[str]
    include_exclude_mode: str

    def should_include_entity(self, entity_id: str) -> bool:
        """Check if entity should be included based on include/exclude mode."""
        if self.include_exclude_mode == MODE_INCLUDE:
            return entity_id in self.include_entities
        if self.include_exclude_mode == MODE_EXCLUDE:
            return entity_id not in self.exclude_entities
        return True
