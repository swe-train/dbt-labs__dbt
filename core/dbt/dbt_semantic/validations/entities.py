from typing import List
from dbt.dbt_semantic.references import EntityElementReference, EntityReference

from dbt.contracts.graph.nodes import Entity
from dbt.dbt_semantic.objects.dimensions import DimensionType
from dbt.dbt_semantic.objects.identifiers import IdentifierType
from dbt.dbt_semantic.objects.user_configured_model import UserConfiguredModel
from dbt.dbt_semantic.validations.validator_helpers import (
    EntityContext,
    EntityElementContext,
    EntityElementType,
    ModelValidationRule,
    ValidationIssueType,
    ValidationError,
)
from dbt.dbt_semantic.time import SUPPORTED_GRANULARITIES


class EntityTimeDimensionWarningsRule(ModelValidationRule):
    """Checks time dimensions in entities."""

    @staticmethod
    def validate_model(model: UserConfiguredModel) -> List[ValidationIssueType]:  # noqa: D
        issues: List[ValidationIssueType] = []

        for entity in model.entities:
            issues.extend(EntityTimeDimensionWarningsRule._validate_entity(entity=entity))
        return issues

    @staticmethod
    def _validate_entity(entity: Entity) -> List[ValidationIssueType]:
        issues: List[ValidationIssueType] = []

        primary_time_dimensions = []

        for dim in entity.dimensions:
            context = EntityElementContext(
                entity_element=EntityElementReference(
                    entity_name=entity.name, name=dim.name
                ),
                element_type=EntityElementType.DIMENSION,
            )

            if dim.type == DimensionType.TIME:
                if dim.type_params is None:
                    continue
                elif dim.type_params.is_primary:
                    primary_time_dimensions.append(dim)
                elif dim.type_params.time_granularity:
                    if dim.type_params.time_granularity not in SUPPORTED_GRANULARITIES:
                        issues.append(
                            ValidationError(
                                context=context,
                                message=f"Unsupported time granularity in time dimension with name: {dim.name}, "
                                f"Please use {[s.value for s in SUPPORTED_GRANULARITIES]}",
                            )
                        )

        # A entity must have a primary time dimension if it has
        # any measures that don't have an `agg_time_dimension` set
        if (
            len(primary_time_dimensions) == 0
            and len(entity.measures) > 0
            and any(measure.agg_time_dimension is None for measure in entity.measures)
        ):
            issues.append(
                ValidationError(
                    context=EntityContext(
                        entity=EntityReference(entity_name=entity.name),
                    ),
                    message=f"No primary time dimension in entity with name ({entity.name}). Please add one",
                )
            )

        if len(primary_time_dimensions) > 1:
            for primary_time_dimension in primary_time_dimensions:
                issues.append(
                    ValidationError(
                        context=EntityContext(
                            entity=EntityReference(entity_name=entity.name),
                        ),
                        message=f"In entity {entity.name}, "
                        f"Primary time dimension with name: {primary_time_dimension.name} "
                        f"is one of many defined as primary.",
                    )
                )

        return issues


class EntityValidityWindowRule(ModelValidationRule):
    """Checks validity windows in entitys to ensure they comply with runtime requirements"""

    @staticmethod
    def validate_model(model: UserConfiguredModel) -> List[ValidationIssueType]:
        """Checks the validity param definitions in every entity in the model"""
        issues: List[ValidationIssueType] = []

        for entity in model.entities:
            issues.extend(EntityValidityWindowRule._validate_entity(entity=entity))

        return issues

    @staticmethod
    def _validate_entity(entity: Entity) -> List[ValidationIssueType]:
        """Runs assertions on entities with validity parameters set on one or more time dimensions"""

        issues: List[ValidationIssueType] = []

        validity_param_dims = [dim for dim in entity.dimensions if dim.validity_params is not None]

        if not validity_param_dims:
            return issues

        context = EntityContext(
            entity=EntityReference(entity_name=entity.name),
        )
        requirements = (
            "Data sources using dimension validity params to define a validity window must have exactly two time "
            "dimensions with validity params specified - one marked `is_start` and the other marked `is_end`."
        )
        validity_param_dimension_names = [dim.name for dim in validity_param_dims]
        start_dim_names = [
            dim.name for dim in validity_param_dims if dim.validity_params and dim.validity_params.is_start
        ]
        end_dim_names = [dim.name for dim in validity_param_dims if dim.validity_params and dim.validity_params.is_end]
        num_start_dims = len(start_dim_names)
        num_end_dims = len(end_dim_names)

        if len(validity_param_dims) == 1 and num_start_dims == 1 and num_end_dims == 1:
            # Defining a single point window, such as one might find in a daily snapshot table keyed on date,
            # is not currently supported.
            error = ValidationError(
                context=context,
                message=(
                    f"Data source {entity.name} has a single validity param dimension that defines its window: "
                    f"`{validity_param_dimension_names[0]}`. This is not a currently supported configuration! "
                    f"{requirements} If you have one column defining a window, as in a daily snapshot table, you can "
                    f"define a separate dimension and increment the time value in the `expr` field as a work-around."
                ),
            )
            issues.append(error)
        elif len(validity_param_dims) != 2:
            error = ValidationError(
                context=context,
                message=(
                    f"Data source {entity.name} has {len(validity_param_dims)} dimensions defined with validity "
                    f"params. They are: {validity_param_dimension_names}. There must be either zero or two! "
                    f"If you wish to define a validity window for this entity, please follow these requirements: "
                    f"{requirements}"
                ),
            )
            issues.append(error)
        elif num_start_dims != 1 or num_end_dims != 1:
            # Validity windows must define both a start and an end, and there should be exactly one
            start_dim_names = []
            error = ValidationError(
                context=context,
                message=(
                    f"Data source {entity.name} has two validity param dimensions defined, but does not have "
                    f"exactly one each marked with is_start and is_end! Dimensions: {validity_param_dimension_names}. "
                    f"is_start dimensions: {start_dim_names}. is_end dimensions: {end_dim_names}. {requirements}"
                ),
            )
            issues.append(error)

        primary_or_unique_identifiers = [
            identifier
            for identifier in entity.identifiers
            if identifier.type in (IdentifierType.PRIMARY, IdentifierType.UNIQUE)
        ]
        if not any([identifier.type is IdentifierType.NATURAL for identifier in entity.identifiers]):
            error = ValidationError(
                context=context,
                message=(
                    f"Data source {entity.name} has validity param dimensions defined, but does not have an "
                    f"identifier with type `natural` set. The natural key for this entity is what we use to "
                    f"process a validity window join. Primary or unique identifiers, if any, might be suitable for "
                    f"use as natural keys: ({[identifier.name for identifier in primary_or_unique_identifiers]})."
                ),
            )
            issues.append(error)

        if primary_or_unique_identifiers:
            error = ValidationError(
                context=context,
                message=(
                    f"Data source {entity.name} has validity param dimensions defined and also has one or more "
                    f"identifiers designated as `primary` or `unique`. This is not yet supported, as we do not "
                    f"currently process joins against these key types for entitys with validity windows "
                    f"specified."
                ),
            )
            issues.append(error)

        if entity.measures:
            # Temporarily block measure definitions in entitys with validity windows set
            measure_names = [measure.name for measure in entity.measures]
            error = ValidationError(
                context=context,
                message=(
                    f"Data source {entity.name} has both measures and validity param dimensions defined. This "
                    f"is not currently supported! Please remove either the measures or the validity params. "
                    f"Measure names: {measure_names}. Validity param dimension names: "
                    f"{validity_param_dimension_names}."
                ),
            )
            issues.append(error)

        return issues