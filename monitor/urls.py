"""URL patterns for the Pushin' Weight dashboard (U7).

Descriptive paths without version or internal prefixes. Data endpoints
return JSON; HTML partials for htmx swaps use a .html suffix on the same
paths. Brand drill-down: /brands/<brand>/.
"""

from django.shortcuts import redirect
from django.urls import path

from . import views

urlpatterns = [
    # Pages
    path("", views.home, name="home"),
    path("brands/<str:brand>/", views.brand_home, name="brand_home"),

    # JSON data APIs
    path("feed/", views.home_feed_json, name="feed"),
    path("chart/", views.chart_json, name="chart"),
    path("brand-chart/<str:brand>/", views.brand_chart_json, name="brand_chart"),

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
    path("debug/i18n/", views.debug_i18n, name="debug_i18n"),
    path("window/<int:days>/", views.set_window, name="set_window"),
]
