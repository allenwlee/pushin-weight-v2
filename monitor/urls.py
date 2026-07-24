"""URL patterns for the Pushin' Weight dashboard.

Descriptive paths without version or internal prefixes. Data endpoints
return JSON; HTML partials for htmx swaps use a .html suffix on the same
paths. Brand drill-down: /brands/<brand>/. Company-scoped routes are
registered for future paid-tier access and redirect to the unscoped
equivalent for now.
"""

from django.shortcuts import redirect
from django.urls import path

from . import views

urlpatterns = [
    # Pages
    path("", views.home, name="home"),
    path("brands/<str:brand>/", views.brand_home, name="brand_home"),
    # Company-scoped brand pages (future paid tier — redirect for now)
    path(
        "companies/<str:company>/brands/",
        lambda request, company: redirect("home"),
        name="company_brands",
    ),
    path(
        "companies/<str:company>/brands/<str:brand>/",
        lambda request, company, brand: redirect("brand_home", brand=brand),
        name="company_brand_home",
    ),

    # JSON data APIs (renamed from home_feed_json / home_chart_json in U2/U3)
    path("feed/", views.home_feed_json, name="feed"),
    path("chart/", views.home_chart_json, name="chart"),
    path("brand-chart/<str:brand>/", views.brand_chart_json, name="brand_chart"),

    # HTML partials (htmx swap targets — split from JSON views in U3)
    path("chart.html", views.home_chart_json, name="chart_html"),
    path(
        "brand-chart/<str:brand>.html",
        views.brand_chart_json,
        name="brand_chart_html",
    ),

    # Spend panel (stub view added in U5)
    path("spend.html", views.spend_stub, name="spend_html"),

    # Locale and window cookie setters
    path("locale/<str:locale>/", views.set_locale, name="set_locale"),
    path("window/<int:days>/", views.set_window, name="set_window"),
]
