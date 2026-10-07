"""Opt-in, read-only aggregate comparisons; never fetch providers on a request."""

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.benchmark_attribution import UseNotPermitted, enforce_use
from core.benchmark_metric_series import build_comparison
from core.models import MetricCollectionContract


def _contract(contract_id, preset):
    if not settings.BENCHMARK_METRICS_ENABLED:
        raise Http404
    contract = get_object_or_404(
        MetricCollectionContract.objects.select_related("taxonomy_version"),
        pk=contract_id,
    )
    if preset not in contract.methodology.get("comparisons", {}):
        raise Http404
    return contract


def _authorize(request, contract, result, use):
    review = (
        getattr(settings, "BENCHMARK_REVIEW_ENABLED", False)
        and (settings.DEBUG or settings.OLLIJA_STAGING_MODE)
        and request.user.is_authenticated
        and request.user.is_staff
    )
    enforce_use(
        contract, result, "isolated_review" if review else use, isolated_review=review
    )
    return review


@require_GET
@never_cache
def pulse(request, contract_id, preset):
    contract = _contract(contract_id, preset)
    comparisons = contract.methodology["comparisons"]
    try:
        result = build_comparison(
            contract, preset, request.GET.get("start"), request.GET.get("end")
        )
        _authorize(request, contract, result, "public_charts")
    except UseNotPermitted:
        return JsonResponse(
            {"error": "This comparison is not cleared for this use."}, status=403
        )
    except ValueError:
        return JsonResponse(
            {"error": "Invalid comparison dates or measurement configuration."},
            status=400,
        )
    return render(
        request,
        "monitor/benchmark_pulse.html",
        {
            "contract": contract,
            "preset": preset,
            "comparison": comparisons[preset],
            "comparisons": comparisons,
        },
    )


@require_GET
@never_cache
def series(request, contract_id, preset):
    contract = _contract(contract_id, preset)
    try:
        result = build_comparison(
            contract, preset, request.GET.get("start"), request.GET.get("end")
        )
        _authorize(request, contract, result, "numeric_export")
    except UseNotPermitted:
        return JsonResponse(
            {"error": "This comparison is not cleared for this use."}, status=403
        )
    except ValueError:
        return JsonResponse(
            {"error": "Invalid comparison dates or measurement configuration."},
            status=400,
        )
    return JsonResponse(result, json_dumps_params={"allow_nan": False})
