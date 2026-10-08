"""Reviewed comparisons can reuse history without copying or rewriting facts."""

from core.measurement_taxonomy import require
from core.models import MetricCollectionContract


def measurement_contract(contract, line):
    pin = line.get("measurement_contract")
    if pin is None:
        return contract
    parent = MetricCollectionContract.objects.get(pk=pin["id"])
    require(
        parent.contract_hash == pin["contract_hash"],
        "measurement contract hash mismatch",
    )
    source = line["source"]
    expected = next(
        d
        for d in contract.source_configuration[source]["definitions"]
        if d["metric_key"] == line["metric_key"]
    )
    retained = next(
        (
            d
            for d in parent.source_configuration.get(source, {}).get("definitions", [])
            if d["metric_key"] == line["metric_key"]
        ),
        None,
    )
    require(expected == retained, "measurement pin definition mismatch")
    require(
        contract.source_configuration[source].get("config")
        == parent.source_configuration[source].get("config"),
        "measurement pin provider configuration mismatch",
    )
    current = {
        (m.external_identifier, m.source_subject_kind, m.identifier_scope, m.subject_id)
        for m in contract.mappings.filter(
            source_id=source, external_identifier__in=line["mapping_identifiers"]
        )
    }
    previous = {
        (m.external_identifier, m.source_subject_kind, m.identifier_scope, m.subject_id)
        for m in parent.mappings.filter(
            source_id=source, external_identifier__in=line["mapping_identifiers"]
        )
    }
    require(bool(current) and current == previous, "measurement pin mapping mismatch")
    return parent


def validate_pin(line, mappings, config):
    pin = line.get("measurement_contract")
    if pin is None:
        return
    require(line["source"] != "x", "native posts do not use provider measurement pins")
    parent = MetricCollectionContract.objects.get(pk=pin["id"])
    require(
        parent.contract_hash == pin["contract_hash"],
        "measurement contract hash mismatch",
    )
    source = line["source"]
    expected = next(
        d
        for d in config[source]["definitions"]
        if d["metric_key"] == line["metric_key"]
    )
    retained = next(
        (
            d
            for d in parent.source_configuration.get(source, {}).get("definitions", [])
            if d["metric_key"] == line["metric_key"]
        ),
        None,
    )
    require(
        expected == retained
        and config[source].get("config")
        == parent.source_configuration[source].get("config"),
        "measurement pin definition/configuration mismatch",
    )
    selected = {
        (
            m["external_identifier"],
            m["source_subject_kind"],
            m["identifier_scope"],
            str(m["subject_id"]),
        )
        for m in mappings
        if m["source"] == source
        and m["external_identifier"] in line["mapping_identifiers"]
    }
    retained_mappings = {
        (
            m.external_identifier,
            m.source_subject_kind,
            m.identifier_scope,
            str(m.subject_id),
        )
        for m in parent.mappings.filter(
            source_id=source, external_identifier__in=line["mapping_identifiers"]
        )
    }
    require(
        bool(selected) and selected == retained_mappings,
        "measurement pin mapping mismatch",
    )
