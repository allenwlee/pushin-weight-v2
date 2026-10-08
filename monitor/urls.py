"""URL patterns for the Pushin' Weight dashboard (U7).

Descriptive paths without version or internal prefixes. Data endpoints
return JSON; HTML partials for htmx swaps use a .html suffix on the same
paths. Brand drill-down: /brands/<brand>/.
"""

from django.shortcuts import redirect
from django.urls import path

from . import benchmark_views, views
from .editorial import views as editorial_views

urlpatterns = [
    path("benchmarks/<uuid:contract_id>/<slug:preset>/", benchmark_views.pulse, name="benchmark_pulse"),
    path("benchmarks/<uuid:contract_id>/<slug:preset>/series/", benchmark_views.series, name="benchmark_series"),
    path("stories/", editorial_views.archive, name="editorial_archive"),
    path("stories/<uuid:story_id>/", editorial_views.story, name="editorial_story"),
    path("stories/<uuid:story_id>/assets/<uuid:picture_id>/<str:variant>/", editorial_views.asset, name="editorial_asset"),
    path("api/v2/editorial-stories/", editorial_views.stories_api, name="editorial_stories_api"),
    # Pages
    path("", views.home, name="home"),
    path("dashboard/each", views.dashboard_each, name="dashboard_each"),
    path("dashboard/each/chart/", views.dashboard_each_chart_json, name="dashboard_each_chart"),
    path("internal/", views.home_internal, name="home_internal"),
    path("brands/<str:brand>/", views.brand_home, name="brand_home"),
    path("admin", views.product_review, name="product_review"),
    path("admin/", views.product_review_legacy),
    path("admin/official-accounts/frozen-run", views.frozen_account_run, name="frozen_account_run"),
    path(
        "admin/products/<int:proposal_id>/",
        views.product_review_detail,
        name="product_review_detail",
    ),
    path("product-review/", views.product_review_legacy),
    path("product-review/<int:proposal_id>/", views.product_review_legacy),

    # JSON data APIs
    path("feed/", views.home_feed_json, name="feed"),
    path("chart/", views.chart_json, name="chart"),
    path("brand-chart/<str:brand>/", views.brand_chart_json, name="brand_chart"),
    path(
        "api/v2/post-synthesis-demands/",
        views.post_synthesis_demands,
        name="post_synthesis_demands",
    ),

    # HTML partials (htmx swap targets)
    path("chart.html", views.chart_html, name="chart_html"),
    path(
        "brand-chart/<str:brand>.html",
        views.brand_chart_html,
        name="brand_chart_html",
    ),

    # Spend panel
    path("spend.html", views.spend_stub, name="spend_html"),

    # Locale and window cookie setters
    path("locale/<str:locale>/", views.set_locale, name="set_locale"),
    path("window/<int:days>/", views.set_window, name="set_window"),
]
