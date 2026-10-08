(function () {
  "use strict";
  var node = document.getElementById("pw-analytics-config");
  if (!node || navigator.doNotTrack === "1" || navigator.globalPrivacyControl === true) return;
  try {
    var config = JSON.parse(node.textContent);
    if (!["https://us.i.posthog.com", "https://eu.i.posthog.com"].includes(config.host)) return;
    var safeUrl = window.location.origin + config.path;
    var allowed = [
      "token", "distinct_id", "$cookieless_mode", "$device_id", "$user_id",
      "$anon_distinct_id", "$session_id", "$window_id", "$lib", "$lib_version",
      "$process_person_profile", "$is_identified"
    ];
    var sdk = document.createElement("script");
    sdk.src = config.host.replace(".i.posthog.com", "-assets.i.posthog.com") + "/static/array.js";
    sdk.async = true;
    sdk.crossOrigin = "anonymous";
    sdk.onload = function () {
      try {
        window.posthog.init(config.token, {
          api_host: config.host,
          defaults: "2026-05-30",
          autocapture: false,
          capture_pageview: false,
          capture_pageleave: false,
          capture_dead_clicks: false,
          rageclick: false,
          capture_performance: false,
          capture_exceptions: false,
          enable_heatmaps: false,
          disable_session_recording: true,
          disable_surveys: true,
          advanced_disable_flags: true,
          save_campaign_params: false,
          save_referrer: false,
          person_profiles: "identified_only",
          respect_dnt: true,
          before_send: function (event) {
            if (!event || !["$pageview", "$identify"].includes(event.event)) return null;
            var properties = {};
            allowed.forEach(function (name) {
              if (event.properties && event.properties[name] !== undefined) properties[name] = event.properties[name];
            });
            properties.environment = config.environment;
            properties.channel = "web";
            properties.is_test = config.isTest;
            properties.$geoip_disable = true;
            if (event.event === "$pageview") {
              properties.$current_url = safeUrl;
              properties.$pathname = config.path;
            }
            event.properties = properties;
            delete event.$set;
            delete event.$set_once;
            return event;
          },
          loaded: function (posthog) {
            var previous = posthog.get_property("$user_id");
            if (previous && previous !== config.userId) posthog.reset();
            if (config.userId) posthog.identify(config.userId);
            posthog.capture("$pageview", { $current_url: safeUrl });
          }
        });
      } catch (_) { /* Analytics availability does not affect the page. */ }
    };
    document.head.appendChild(sdk);
  } catch (_) { /* Ignore unavailable analytics. */ }
})();
