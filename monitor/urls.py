"""URL patterns for the Pushin' Weight dashboard (U7)."""

from django.urls import path

from . import views

urlpatterns = [
    # Multi-brand home
    path("", views.home, name="home"),

    # Single-brand home (two forms: with company and without)
    path("<str:company>/<str:brand>/", views.brand_home, name="brand_home"),
    path("_/<str:brand>/", views.brand_home, name="brand_home_underscore"),

    # JSON APIs — feed
    path("api/v1/home.feed.json", views.home_feed_json, name="home_feed_json"),
    path("api/v1/home.feed.html", views.home_feed_json, name="home_feed_html"),
    path(
        "api/v1/brand.feed.json",
        views.brand_feed_json,
        kwargs={"brand": None},
        name="brand_feed_json",
    ),
    path(
        "api/v1/brand.feed.json/<str:brand>",
        views.brand_feed_json,
        name="brand_feed_json_named",
    ),

    # JSON APIs — charts
    path("api/v1/home.chart.json", views.home_chart_json, name="home_chart_json"),
    path("api/v1/home.chart.html", views.home_chart_json, name="home_chart_html"),
    path(
        "api/v1/brand.chart.json",
        views.brand_chart_json,
        kwargs={"brand": None},
        name="brand_chart_json",
    ),
    path(
        "api/v1/brand.chart.json/<str:brand>",
        views.brand_chart_json,
        name="brand_chart_json_named",
    ),
]
