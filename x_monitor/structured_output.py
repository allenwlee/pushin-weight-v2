"""Small schema primitives shared by headline and editorial requests."""


def closed_object(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
