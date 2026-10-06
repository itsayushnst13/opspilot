"""Convert pydantic JSON schema to the OpenAPI subset accepted by Gemini function declarations / response schemas."""
from __future__ import annotations

from typing import Any


def to_gemini_schema(schema: dict, defs: dict | None = None) -> dict:
    defs = defs if defs is not None else schema.get("$defs", {})
    if "$ref" in schema:
        return to_gemini_schema(defs[schema["$ref"].split("/")[-1]], defs)
    if "anyOf" in schema:
        non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
        merged = to_gemini_schema(non_null[0], defs) if non_null else {"type": "string"}
        if len(non_null) != len(schema["anyOf"]):
            merged["nullable"] = True
        if "description" in schema:
            merged["description"] = schema["description"]
        return merged
    out: dict[str, Any] = {}
    t = schema.get("type", "string")
    out["type"] = {"integer": "integer", "number": "number", "boolean": "boolean", "array": "array",
                   "object": "object"}.get(t, "string")
    desc = schema.get("description", "")
    if schema.get("format") == "date":
        desc = (desc + " (ISO date YYYY-MM-DD)").strip()
    if desc:
        out["description"] = desc
    if out["type"] == "object" and "properties" in schema:
        out["properties"] = {k: to_gemini_schema(v, defs) for k, v in schema["properties"].items()}
        if schema.get("required"):
            out["required"] = schema["required"]
    if out["type"] == "array":
        out["items"] = to_gemini_schema(schema.get("items", {"type": "string"}), defs)
    return out
