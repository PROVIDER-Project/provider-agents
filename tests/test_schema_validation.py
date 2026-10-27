import jsonschema
import pytest

from provider_agents.abstract_provider_agent import validate_schema


def test_repeated_validation_checks_schema_only_once(monkeypatch):
    """Repeated agent steps must not repeat expensive meta-schema validation."""
    checks = []
    original = jsonschema.Draft202012Validator.check_schema

    def check_schema(schema, *args, **kwargs):
        checks.append(schema)
        return original(schema, *args, **kwargs)

    monkeypatch.setattr(jsonschema.Draft202012Validator, "check_schema", check_schema)
    schema = {"title": "reused step schema", "type": "object",
              "properties": {"quantity": {"type": "number", "minimum": 0}}}
    for _ in range(5):
        validate_schema({"quantity": 1}, schema)
    with pytest.raises(jsonschema.ValidationError):
        validate_schema({"quantity": -1}, schema)
    assert len(checks) == 1


def test_schema_changes_are_not_hidden_by_cache():
    schema = {"type": "object", "properties": {"value": {"type": "integer"}}}
    validate_schema({"value": 1}, schema)
    schema["properties"]["value"]["minimum"] = 2
    with pytest.raises(jsonschema.ValidationError):
        validate_schema({"value": 1}, schema)


def test_declared_schema_draft_is_respected():
    schema = {"$schema": "http://json-schema.org/draft-04/schema#",
              "type": "object", "properties": {
                  "value": {"type": "number", "minimum": 0, "exclusiveMinimum": True},
              }}
    validate_schema({"value": 1}, schema)
    with pytest.raises(jsonschema.ValidationError):
        validate_schema({"value": 0}, schema)


def test_invalid_schema_is_still_rejected():
    with pytest.raises(jsonschema.SchemaError):
        validate_schema({}, {"type": "not-a-json-schema-type"})
