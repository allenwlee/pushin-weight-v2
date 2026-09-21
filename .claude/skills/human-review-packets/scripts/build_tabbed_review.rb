#!/usr/bin/env ruby
# frozen_string_literal: true

require "cgi"
require "csv"
require "json"
require "optparse"
require "pathname"
require "set"
require "time"

options = { signals_csv: [] }
default_taxonomy = File.expand_path("../references/latest-taxonomy.json", __dir__)

OptionParser.new do |parser|
  parser.banner = "Usage: build_tabbed_review.rb --source-html PATH --review-inputs PATH --signals-csv PATH [--model-results PATH] --output-html PATH"
  parser.on("--source-html PATH", "Existing static review packet") { |value| options[:source_html] = value }
  parser.on("--review-inputs PATH", "Frozen JSON review inputs") { |value| options[:review_inputs] = value }
  parser.on("--signals-csv PATH", "CSV with tweet_id, brand_id, existing_signals (repeatable)") { |value| options[:signals_csv] << value }
  parser.on("--taxonomy-json PATH", "Taxonomy contract (default: #{default_taxonomy})") { |value| options[:taxonomy_json] = value }
  parser.on("--model-results PATH", "Optional classifier results rendered in red without pre-filling owner controls") { |value| options[:model_results] = value }
  parser.on("--output-html PATH", "New interactive HTML file") { |value| options[:output_html] = value }
end.parse!

options[:taxonomy_json] ||= default_taxonomy
required = %i[source_html review_inputs output_html]
missing = required.select { |key| options[key].to_s.empty? }
abort "Missing required option(s): #{missing.join(', ')}" unless missing.empty?
abort "At least one --signals-csv is required" if options[:signals_csv].empty?

(required + [:taxonomy_json]).each do |key|
  next if key == :output_html
  abort "File not found: #{options[key]}" unless File.file?(options[key])
end
options[:signals_csv].each { |path| abort "File not found: #{path}" unless File.file?(path) }
abort "File not found: #{options[:model_results]}" if options[:model_results] && !File.file?(options[:model_results])

taxonomy = JSON.parse(File.read(options[:taxonomy_json]))
inputs = JSON.parse(File.read(options[:review_inputs]))
model_results = options[:model_results] ? JSON.parse(File.read(options[:model_results])) : nil
abort "Review inputs must be a nonempty JSON array" unless inputs.is_a?(Array) && !inputs.empty?

required_input_keys = %w[case_id tweet_id target_brand stored_brand_associations]
inputs.each_with_index do |item, index|
  missing_keys = required_input_keys.reject { |key| item.key?(key) }
  abort "Review input #{index + 1} is missing: #{missing_keys.join(', ')}" unless missing_keys.empty?
  abort "Review input #{index + 1} has a blank target_brand" if item["target_brand"].to_s.strip.empty?
  abort "Review input #{index + 1} stored_brand_associations must be an array" unless item["stored_brand_associations"].is_a?(Array)
end

case_ids = inputs.map { |item| item.fetch("case_id").to_s }
case_id_counts = Hash.new(0)
case_ids.each { |case_id| case_id_counts[case_id] += 1 }
duplicates = case_id_counts.select { |_id, count| count > 1 }.keys
abort "Duplicate case IDs: #{duplicates.join(', ')}" unless duplicates.empty?

source_html = File.read(options[:source_html])
article_matches = source_html.scan(/<article\s+id="([^"]+)"[^>]*>(.*?)<\/article>/m)
abort "No review articles found in #{options[:source_html]}" if article_matches.empty?
article_ids = article_matches.map(&:first)
unless article_ids == case_ids
  missing_articles = case_ids - article_ids
  extra_articles = article_ids - case_ids
  abort "Packet/input mismatch. Missing articles: #{missing_articles.inspect}; extra articles: #{extra_articles.inspect}; order matches: #{article_ids == case_ids}"
end
article_by_id = article_matches.to_h

signal_pairs = {}
options[:signals_csv].each do |path|
  table = CSV.read(path, headers: true)
  required_headers = %w[tweet_id brand_id existing_signals]
  missing_headers = required_headers - table.headers.compact
  abort "#{path} is missing CSV columns: #{missing_headers.join(', ')}" unless missing_headers.empty?

  table.each do |row|
    signal = row["existing_signals"].to_s.strip
    next if signal.empty?
    pair = [row["tweet_id"].to_s, row["brand_id"].to_s]
    signal_pairs[pair] ||= []
    signal_pairs[pair] << signal unless signal_pairs[pair].include?(signal)
  end
end
abort "Signal exports contained no nonempty existing_signals values" if signal_pairs.empty?

def h(value)
  CGI.escapeHTML(value.to_s)
end

def safe_json(value)
  JSON.generate(value).gsub("</", "<\\/")
end

def display_value(value)
  return "—" if value.nil? || value == "" || value == []
  return value.join(", ") if value.is_a?(Array)
  value.to_s
end

def source_fragment(raw)
  fragment = raw.sub(/<section class="review">.*?<\/section>/m, "")
  fragment = fragment.sub(/<a class="back"[^>]*>.*?<\/a>/m, "")
  fragment.gsub(/<details(?![^>]*\bopen\b)([^>]*)>/, '<details open\1>')
end

def choice_field(field, case_id:, scope:, brand: "")
  field_key = field.fetch("key")
  control = field.fetch("control")
  span = field.fetch("span", "full")
  exclusive = JSON.generate(field.fetch("exclusive_values", []))
  input_name = [case_id, scope, brand, field_key].reject(&:empty?).join("__")
  choices = field.fetch("choices").map do |choice|
    help = choice["help"] ? %(<small>#{h(choice["help"])}</small>) : ""
    sentinel = choice["ui_sentinel"] ? " sentinel" : ""
    %(<label class="choice#{sentinel}"><input type="#{h(control)}" name="#{h(input_name)}" value="#{h(choice.fetch("value"))}" data-review-input data-case="#{h(case_id)}" data-scope="#{h(scope)}" data-brand="#{h(brand)}" data-field="#{h(field_key)}" data-control="#{h(control)}" data-exclusive="#{h(exclusive)}"><span><strong>#{h(choice.fetch("label"))}</strong>#{help}</span></label>)
  end.join
  explanation = if field["explanation"]
    %(<label class="explanation"><span>#{h(field["explanation"])}</span><textarea rows="2" data-review-input data-case="#{h(case_id)}" data-scope="#{h(scope)}" data-brand="#{h(brand)}" data-field="#{h(field_key)}_explanation" data-control="textarea"></textarea></label>)
  else
    ""
  end
  description = field["description"] ? %(<p class="field-description">#{h(field["description"])}</p>) : ""
  %(<fieldset class="review-field span-#{h(span)}" data-fieldset="#{h(field_key)}"><legend>#{h(field.fetch("label"))}</legend>#{description}<div class="choices">#{choices}</div>#{explanation}</fieldset>)
end

def textarea_field(field, case_id:, scope:, brand: "")
  span = field.fetch("span", "full")
  field_key = field.fetch("key")
  %(<label class="review-field textarea-field span-#{h(span)}"><span class="field-label">#{h(field.fetch("label"))}</span><textarea rows="3" placeholder="#{h(field.fetch("placeholder", "Optional"))}" data-review-input data-case="#{h(case_id)}" data-scope="#{h(scope)}" data-brand="#{h(brand)}" data-field="#{h(field_key)}" data-control="textarea"></textarea></label>)
end

def render_field(field, case_id:, scope:, brand: "")
  if field.fetch("control") == "textarea"
    textarea_field(field, case_id: case_id, scope: scope, brand: brand)
  else
    choice_field(field, case_id: case_id, scope: scope, brand: brand)
  end
end

packet_cases = inputs.map do |item|
  target = item.fetch("target_brand").to_s
  associations = item.fetch("stored_brand_associations").map(&:to_s).reject(&:empty?).uniq
  associations.unshift(target) unless associations.include?(target)
  signal_backed = associations.select { |brand| signal_pairs.key?([item.fetch("tweet_id").to_s, brand]) }
  review_brands = ([target] + signal_backed).uniq
  {
    "case_id" => item.fetch("case_id").to_s,
    "tweet_id" => item.fetch("tweet_id").to_s,
    "target_brand" => target,
    "stored_brand_associations" => associations,
    "signal_backed_brands" => signal_backed,
    "review_brands" => review_brands
  }
end

if model_results
  abort "Model results must be an object" unless model_results.is_a?(Hash)
  abort "Model results require model_label" if model_results["model_label"].to_s.strip.empty?
  model_cases = model_results["cases"]
  abort "Model results require a cases object" unless model_cases.is_a?(Hash)
  expected_case_ids = packet_cases.map { |item| item.fetch("case_id") }
  abort "Model-result case IDs do not match packet order" unless model_cases.keys == expected_case_ids
  allowed_brand_fields = taxonomy.fetch("per_brand_fields").map { |field| field.fetch("key") }.to_set
  allowed_post_fields = taxonomy.fetch("post_level_fields").map { |field| field.fetch("key") }.to_set | Set["promoted_subjects"]
  packet_cases.each do |item|
    model_case = model_cases.fetch(item.fetch("case_id"))
    per_brand = model_case["per_brand"]
    abort "Model result #{item.fetch('case_id')} requires per_brand" unless per_brand.is_a?(Hash)
    abort "Model-result brands do not match review brands for #{item.fetch('case_id')}" unless per_brand.keys == item.fetch("review_brands")
    per_brand.each do |brand, fields|
      abort "Model result #{item.fetch('case_id')}/#{brand} must be an object" unless fields.is_a?(Hash)
      unknown = fields.keys.to_set - allowed_brand_fields
      abort "Unknown model fields for #{item.fetch('case_id')}/#{brand}: #{unknown.to_a.join(', ')}" unless unknown.empty?
    end
    post_level = model_case["post_level"]
    abort "Model result #{item.fetch('case_id')} requires post_level" unless post_level.is_a?(Hash)
    unknown = post_level.keys.to_set - allowed_post_fields
    abort "Unknown post-level model fields for #{item.fetch('case_id')}: #{unknown.to_a.join(', ')}" unless unknown.empty?
  end
end

def model_card(model_results, taxonomy, case_id:, brand: nil)
  return "" unless model_results
  result = if brand
    model_results.fetch("cases").fetch(case_id).fetch("per_brand").fetch(brand)
  else
    model_results.fetch("cases").fetch(case_id).fetch("post_level")
  end
  taxonomy_fields = brand ? taxonomy.fetch("per_brand_fields") : taxonomy.fetch("post_level_fields")
  rows = taxonomy_fields.each_with_object([]) do |field, output|
    key = field.fetch("key")
    next unless result.key?(key)
    output << %(<div class="model-result-row"><strong>#{h(field.fetch("label"))}</strong><span>#{h(display_value(result[key]))}</span></div>)
  end
  if !brand && result.key?("promoted_subjects")
    rows << %(<div class="model-result-row"><strong>Promoted subjects</strong><span>#{h(display_value(result["promoted_subjects"].map { |item| item.is_a?(Hash) ? item.compact.values.join(" · ") : item }))}</span></div>)
  end
  %(<aside class="model-result-card" data-model-result><div class="model-result-heading"><span>#{h(model_results.fetch("model_label"))}</span><strong>Model result</strong></div>#{rows.join}</aside>)
end

case_tabs = packet_cases.each_with_index.map do |item, index|
  number = item.fetch("case_id").split("-").last
  %(<button type="button" class="case-tab" role="tab" aria-selected="false" data-case-tab="#{h(item.fetch("case_id"))}" title="#{h(item.fetch("case_id"))} · #{h(item.fetch("target_brand"))}"><span>#{h(number)}</span><i aria-hidden="true"></i></button>)
end.join

case_panels = packet_cases.map do |item|
  case_id = item.fetch("case_id")
  target = item.fetch("target_brand")
  source = source_fragment(article_by_id.fetch(case_id))
  brand_tabs = item.fetch("review_brands").map do |brand|
    roles = []
    roles << "target" if brand == target
    roles << "signal" if item.fetch("signal_backed_brands").include?(brand)
    badge = roles.empty? ? "" : %(<small>#{h(roles.join(" + "))}</small>)
    %(<button type="button" class="brand-tab" role="tab" aria-selected="false" data-brand-tab="#{h(brand)}" data-case="#{h(case_id)}"><span>#{h(brand)}</span>#{badge}<i aria-hidden="true"></i></button>)
  end.join

  brand_panels = item.fetch("review_brands").map do |brand|
    status = if brand == target && item.fetch("signal_backed_brands").include?(brand)
      "Designated target · stored PostBrandSignal present"
    elsif brand == target
      "Designated target · included even without a stored PostBrandSignal"
    else
      "Stored PostBrandSignal present"
    end
    fields = taxonomy.fetch("per_brand_fields").map do |field|
      render_field(field, case_id: case_id, scope: "brand", brand: brand)
    end.join
    model_summary = model_card(model_results, taxonomy, case_id: case_id, brand: brand)
    %(<section class="brand-panel" data-brand-panel="#{h(brand)}" data-case="#{h(case_id)}" hidden><div class="brand-context"><strong>Reviewing #{h(brand)}</strong><span>#{h(status)}</span></div>#{model_summary}<div class="field-grid">#{fields}</div></section>)
  end.join

  post_fields = taxonomy.fetch("post_level_fields").map do |field|
    render_field(field, case_id: case_id, scope: "post")
  end.join

  associations = item.fetch("stored_brand_associations").map do |brand|
    signal = item.fetch("signal_backed_brands").include?(brand)
    kind = signal ? "signal present" : "association only"
    %(<span class="association #{signal ? 'has-signal' : ''}" role="listitem">#{h(brand)} <small>#{h(kind)}</small></span>)
  end.join

  <<~HTML
    <article class="case-panel" data-case-panel="#{h(case_id)}" hidden>
      <section class="source-pane" aria-label="Source evidence for #{h(case_id)}">
        <div class="pane-heading"><span>Source evidence</span><strong>#{h(case_id)}</strong></div>
        <div class="association-row" role="list" aria-label="Stored brand associations">#{associations}</div>
        <div class="source-content">#{source}</div>
      </section>
      <section class="review-pane" aria-label="Review controls for #{h(case_id)}">
        <div class="review-heading">
          <div><span>Your review</span><strong>#{h(case_id)} · target #{h(target)}</strong></div>
          <div class="case-actions"><button type="button" class="secondary" data-previous-case>Previous</button><button type="button" class="primary" data-save-case>Save case</button><button type="button" class="primary" data-next-case>Save &amp; next</button></div>
        </div>
        <div class="brand-tabs" role="tablist" aria-label="Brand reviews for #{h(case_id)}">#{brand_tabs}</div>
        <div class="review-scroll">
          #{brand_panels}
          <section class="post-level-panel"><div class="post-level-heading"><span>Once per post</span><strong>Post-level review</strong></div>#{model_card(model_results, taxonomy, case_id: case_id)}<div class="field-grid">#{post_fields}</div></section>
        </div>
      </section>
    </article>
  HTML
end.join

client_config = {
  "schema" => "pushinweight.human_review/v1",
  "taxonomy_id" => taxonomy.fetch("taxonomy_id"),
  "storage_namespace" => taxonomy.fetch("storage_namespace"),
  "source_packet" => File.basename(options.fetch(:source_html)),
  "cases" => packet_cases,
  "per_brand_fields" => taxonomy.fetch("per_brand_fields").map { |field| { "key" => field.fetch("key"), "control" => field.fetch("control") } },
  "post_level_fields" => taxonomy.fetch("post_level_fields").map { |field| { "key" => field.fetch("key"), "control" => field.fetch("control") } }
}

signal_backed_count = packet_cases.sum { |item| item.fetch("signal_backed_brands").length }
review_target_count = packet_cases.sum { |item| item.fetch("review_brands").length }

html = <<~HTML
  <!doctype html>
  <html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>PushinWeight · #{inputs.length} posts — tabbed brand review</title>
    <style>
      :root{--ink:#172230;--muted:#647386;--line:#d6dee7;--paper:#fff;--wash:#edf2f6;--accent:#075b9b;--accent-soft:#e8f3fc;--success:#18825b;--warning:#9a6210;--radius:10px;color-scheme:light}
      *{box-sizing:border-box;min-width:0}
      html,body{height:100%;margin:0}
      body{font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink);background:var(--wash);overflow:hidden}
      button,input,textarea{font:inherit}
      button{cursor:pointer}
      .app{height:100vh;display:grid;grid-template-rows:auto auto minmax(0,1fr)}
      .app-header{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:10px 16px;background:#13283a;color:#fff}
      .title-block{display:flex;align-items:baseline;gap:12px;white-space:nowrap}.title-block h1{font-size:18px;margin:0}.title-block p{margin:0;color:#c8d6e2;font-size:12px;white-space:normal}
      .global-actions,.case-actions{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
      button.primary,button.secondary{border-radius:7px;padding:7px 11px;font-weight:700;border:1px solid transparent}
      button.primary{background:var(--accent);color:#fff}button.primary:hover{background:#064d83}
      button.secondary{background:#fff;color:#284052;border-color:#bfd0dd}button.secondary:hover{background:#eef5fa}
      .save-state{font-size:12px;color:#c8d6e2;min-width:116px;text-align:right}.save-state.error{color:#ffd0d0}
      .case-tabs{display:flex;flex-wrap:wrap;align-content:flex-start;gap:5px;padding:7px 12px;background:#f8fafc;border-bottom:1px solid var(--line);max-height:82px;overflow-y:auto;overflow-x:hidden}
      .case-tab{position:relative;width:35px;height:29px;padding:0;border:1px solid #bac8d4;border-radius:6px;background:#fff;color:#3b4b5a;font-weight:750}
      .case-tab:hover{border-color:var(--accent)}.case-tab[aria-selected="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
      .case-tab i,.brand-tab i{position:absolute;width:6px;height:6px;border-radius:50%;background:transparent;right:3px;top:3px}.case-tab.started i,.brand-tab.started i{background:#f3a828}.case-tab[aria-selected="true"].started i,.brand-tab[aria-selected="true"].started i{background:#fff}
      #casePanels{min-height:0;overflow:hidden}
      .case-panel{height:100%;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);background:var(--paper)}.case-panel[hidden]{display:none}
      .source-pane,.review-pane{min-height:0;overflow:hidden}.source-pane{overflow-y:auto;padding:14px 18px 32px;border-right:1px solid #b9c5d0;background:#fbfcfd}.review-pane{display:grid;grid-template-rows:auto auto minmax(0,1fr);background:#fff}
      .pane-heading,.review-heading{display:flex;align-items:center;justify-content:space-between;gap:10px}.pane-heading{position:sticky;top:-14px;z-index:3;margin:-14px -18px 10px;padding:10px 18px;background:rgba(251,252,253,.96);border-bottom:1px solid var(--line);backdrop-filter:blur(5px)}
      .pane-heading span,.review-heading span,.post-level-heading span{display:block;color:var(--muted);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}.pane-heading strong,.review-heading strong{font-size:14px}
      .review-heading{padding:9px 13px;border-bottom:1px solid var(--line);background:#f8fafc}.review-heading>div:first-child{display:flex;flex-direction:column}
      .review-heading .secondary,.review-heading .primary{padding:5px 8px;font-size:12px}
      .brand-tabs{display:flex;align-items:stretch;gap:5px;padding:7px 12px;background:#edf3f7;border-bottom:1px solid var(--line);overflow-x:auto}
      .brand-tab{position:relative;display:flex;flex-direction:column;align-items:flex-start;border:1px solid #b9c8d5;border-radius:7px;background:#fff;color:#284052;padding:5px 12px 5px 8px;line-height:1.2;white-space:nowrap}.brand-tab span{font-weight:800}.brand-tab small{font-size:9px;color:var(--muted)}.brand-tab[aria-selected="true"]{background:var(--accent);border-color:var(--accent);color:#fff}.brand-tab[aria-selected="true"] small{color:#d8ebf9}
      .review-scroll{min-height:0;overflow-y:auto;padding:12px 14px 32px;scrollbar-gutter:stable}
      .brand-panel[hidden]{display:none}.brand-context{display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:7px 9px;margin-bottom:10px;background:var(--accent-soft);border-left:3px solid var(--accent);border-radius:5px}.brand-context span{font-size:11px;color:#4f6678;text-align:right}
      .field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;align-items:start}.span-full{grid-column:1/-1}.span-half{grid-column:auto}
      .review-field{display:block;margin:0;padding:9px;border:1px solid var(--line);border-radius:8px;background:#fff}.review-field legend,.field-label{font-weight:800;color:#24384a}.review-field legend{padding:0 4px}.field-description{margin:0 0 7px;color:var(--muted);font-size:11px}
      .choices{display:grid;grid-template-columns:repeat(auto-fit,minmax(138px,1fr));gap:5px}.choice{display:flex;gap:6px;align-items:flex-start;padding:6px 7px;border:1px solid #d7e0e7;border-radius:6px;background:#fafcfd;cursor:pointer}.choice:hover{border-color:#9eb7c9;background:#f2f8fc}.choice:has(input:checked){border-color:var(--accent);background:var(--accent-soft)}.choice:has(input:checked) small{color:#40596d}.choice.sentinel{border-style:dashed}.choice input{flex:0 0 auto;margin:3px 0 0;accent-color:var(--accent)}.choice span{display:block;line-height:1.2}.choice strong{font-size:12px}.choice small{display:block;margin-top:3px;color:var(--muted);font-size:10px;line-height:1.25}
      .explanation{display:block;margin-top:7px;color:var(--muted);font-size:11px}.explanation span{display:block;margin-bottom:3px}textarea{display:block;width:100%;resize:vertical;min-height:42px;padding:6px 7px;color:var(--ink);background:#fff;border:1px solid #bac7d2;border-radius:6px;line-height:1.3}textarea:focus,input:focus-visible,button:focus-visible{outline:2px solid #5aa5d8;outline-offset:1px}
      .textarea-field{font-size:11px}.textarea-field .field-label{display:block;margin-bottom:5px;font-size:13px}
      .post-level-panel{margin-top:15px;padding-top:13px;border-top:3px solid #2e475a}.post-level-heading{display:flex;align-items:baseline;gap:10px;margin-bottom:8px}.post-level-heading strong{font-size:15px}
      .model-result-card{margin:0 0 11px;padding:10px;border:1px solid #f0aaa4;border-radius:8px;background:#fff4f2;color:#8f1d16}.model-result-heading{display:flex;align-items:baseline;justify-content:space-between;gap:10px;padding-bottom:6px;border-bottom:1px solid #f5c8c4}.model-result-heading span{font-size:11px;font-weight:850;letter-spacing:.07em;text-transform:uppercase}.model-result-heading strong{font-size:12px}.model-result-row{display:grid;grid-template-columns:minmax(145px,.55fr) minmax(0,1fr);gap:9px;padding-top:6px;overflow-wrap:anywhere}.model-result-row strong{font-size:11px}.model-result-row span{font-weight:700}
      .association-row{display:flex;flex-wrap:wrap;gap:5px;margin:0 0 12px}.association{padding:3px 7px;border:1px solid #cfd9e1;border-radius:999px;background:#fff;font-size:11px;font-weight:700}.association small{font-weight:500;color:var(--muted)}.association.has-signal{border-color:#8ebba9;background:#edf8f3;color:#126846}.association.has-signal small{color:#365d50}
      .source-content h2{font-size:20px;margin:5px 0 10px}.source-content h2 span{font-size:13px;color:var(--muted);margin-left:8px}.source-content h3{font-size:13px;margin:15px 0 5px}.source-content a{color:var(--accent);overflow-wrap:anywhere}.source-content .metadata{display:grid;grid-template-columns:160px minmax(0,1fr);gap:4px 10px;font-size:12px}.source-content .metadata dt{font-weight:750}.source-content .metadata dd{margin:0;overflow-wrap:anywhere}.source-content .verbatim{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;border-left:3px solid #8ea9bd;padding:10px;font:13px/1.5 system-ui,-apple-system,sans-serif}.source-content .muted{color:var(--muted);font-size:11px}.source-content details{margin:11px 0}.source-content summary{cursor:pointer;color:var(--accent);font-weight:750}.source-content ul{padding-left:20px}
      .status-line{display:flex;align-items:center;gap:8px}.progress{font-size:12px;color:#d7e5ef;white-space:nowrap}
      @media(max-width:1000px){.title-block p{display:none}.field-grid{grid-template-columns:1fr}.span-half{grid-column:1/-1}.choices{grid-template-columns:repeat(auto-fit,minmax(120px,1fr))}}
      @media(max-width:850px){html,body{height:auto}body{overflow:auto}.app{height:auto;min-height:100vh;display:block}.app-header{position:sticky;top:0;z-index:20;align-items:flex-start}.global-actions{justify-content:flex-end}.save-state{width:100%}.case-tabs{position:sticky;top:57px;z-index:19;max-height:74px}.case-panel{display:block;height:auto}.source-pane,.review-pane{overflow:visible;border:0}.source-pane{border-bottom:5px solid #2e475a}.review-pane{display:block}.review-heading,.brand-tabs{position:sticky;z-index:10}.review-heading{top:131px}.brand-tabs{top:183px}.review-scroll{overflow:visible}.title-block{white-space:normal}}
      @media(max-width:560px){.app-header{display:block}.global-actions{margin-top:7px;justify-content:flex-start}.save-state{text-align:left}.case-tabs{top:104px}.review-heading{position:static;display:block}.case-actions{margin-top:7px}.brand-tabs{top:178px}.source-content .metadata{display:block}.source-content .metadata dt{margin-top:5px}}
    </style>
  </head>
  <body>
    <div class="app" data-layout-contract="pushinweight-tabbed-review-v1" data-model-results="#{model_results ? 'true' : 'false'}">
      <header class="app-header">
        <div class="title-block"><h1>#{inputs.length}-post owner review</h1><p>One post at a time · per-brand judgments stay separate · #{model_results ? 'model results are red · ' : ''}blank means unreviewed</p></div>
        <div class="global-actions"><span class="progress" id="progress">0 / #{review_target_count} brand reviews started</span><button type="button" class="secondary" id="exportJson">Export JSON backup</button><button type="button" class="secondary" id="clearAll">Clear all</button><span class="save-state" id="saveState" role="status">Ready</span></div>
      </header>
      <nav class="case-tabs" id="caseTabs" role="tablist" aria-label="Posts">#{case_tabs}</nav>
      <main id="casePanels">#{case_panels}</main>
    </div>
    <script>
      (() => {
        "use strict";
        const CONFIG = #{safe_json(client_config)};
        const STORAGE_KEY = `${CONFIG.storage_namespace}:${CONFIG.source_packet}`;
        const saveState = document.getElementById("saveState");
        const progress = document.getElementById("progress");
        let timer = null;

        function blankState() {
          const cases = {};
          CONFIG.cases.forEach(item => {
            const perBrand = {};
            item.review_brands.forEach(brand => { perBrand[brand] = {}; });
            cases[item.case_id] = { target_brand: item.target_brand, review_targets: item.review_brands, per_brand: perBrand, post_level: {} };
          });
          return { schema: CONFIG.schema, taxonomy_id: CONFIG.taxonomy_id, source_packet: CONFIG.source_packet, saved_at: null, ui: { active_case: CONFIG.cases[0].case_id, active_brand: {} }, cases };
        }

        function loadState() {
          const clean = blankState();
          try {
            const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
            if (!parsed || parsed.taxonomy_id !== CONFIG.taxonomy_id || parsed.source_packet !== CONFIG.source_packet) return clean;
            CONFIG.cases.forEach(item => {
              const saved = parsed.cases && parsed.cases[item.case_id];
              if (!saved) return;
              item.review_brands.forEach(brand => {
                if (saved.per_brand && saved.per_brand[brand] && typeof saved.per_brand[brand] === "object") clean.cases[item.case_id].per_brand[brand] = saved.per_brand[brand];
              });
              if (saved.post_level && typeof saved.post_level === "object") clean.cases[item.case_id].post_level = saved.post_level;
            });
            clean.saved_at = parsed.saved_at || null;
            clean.ui.active_case = CONFIG.cases.some(item => item.case_id === parsed.ui?.active_case) ? parsed.ui.active_case : clean.ui.active_case;
            clean.ui.active_brand = parsed.ui?.active_brand || {};
            return clean;
          } catch (error) {
            saveState.textContent = "Saved data could not be read";
            saveState.classList.add("error");
            return clean;
          }
        }

        let state = loadState();
        let activeCase = state.ui.active_case;

        function persist(message = "Saved") {
          state.saved_at = new Date().toISOString();
          state.ui.active_case = activeCase;
          try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
            saveState.classList.remove("error");
            saveState.textContent = `${message} ${new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"})}`;
          } catch (error) {
            saveState.classList.add("error");
            saveState.textContent = "Save failed — export JSON now";
          }
          updateProgress();
        }

        function collectCase(caseId) {
          const panel = document.querySelector(`[data-case-panel="${caseId}"]`);
          if (!panel) return;
          panel.querySelectorAll('input[data-field="geopolitical_modes"][value="nationalism"]').forEach(enforceNationalismGate);
          const record = state.cases[caseId];
          record.per_brand = Object.fromEntries(record.review_targets.map(brand => [brand, {}]));
          record.post_level = {};
          panel.querySelectorAll("[data-review-input]").forEach(input => {
            const bucket = input.dataset.scope === "brand" ? record.per_brand[input.dataset.brand] : record.post_level;
            const key = input.dataset.field;
            if (input.dataset.control === "checkbox") {
              if (!Array.isArray(bucket[key])) bucket[key] = [];
              if (input.checked) bucket[key].push(input.value);
            } else if (input.dataset.control === "radio") {
              if (!(key in bucket)) bucket[key] = "";
              if (input.checked) bucket[key] = input.value;
            } else {
              bucket[key] = input.value;
            }
          });
        }

        function saveCase(caseId, message = "Autosaved") {
          collectCase(caseId);
          persist(message);
        }

        function answerPresent(value) {
          if (Array.isArray(value)) return value.length > 0;
          return typeof value === "string" ? value.trim().length > 0 : value != null;
        }

        function objectStarted(object) {
          return Object.values(object || {}).some(answerPresent);
        }

        function updateProgress() {
          let started = 0;
          let total = 0;
          CONFIG.cases.forEach(item => {
            const record = state.cases[item.case_id];
            let caseStarted = objectStarted(record.post_level);
            item.review_brands.forEach(brand => {
              total += 1;
              const brandStarted = objectStarted(record.per_brand[brand]);
              if (brandStarted) started += 1;
              caseStarted ||= brandStarted;
              document.querySelector(`[data-case="${item.case_id}"][data-brand-tab="${brand}"]`)?.classList.toggle("started", brandStarted);
            });
            document.querySelector(`[data-case-tab="${item.case_id}"]`)?.classList.toggle("started", caseStarted);
          });
          progress.textContent = `${started} / ${total} brand reviews started`;
        }

        function restoreInputs() {
          document.querySelectorAll("[data-review-input]").forEach(input => {
            const record = state.cases[input.dataset.case];
            const bucket = input.dataset.scope === "brand" ? record?.per_brand?.[input.dataset.brand] : record?.post_level;
            const value = bucket?.[input.dataset.field];
            if (input.dataset.control === "checkbox") input.checked = Array.isArray(value) && value.includes(input.value);
            else if (input.dataset.control === "radio") input.checked = value === input.value;
            else input.value = typeof value === "string" ? value : "";
          });
          document.querySelectorAll('input[data-field="geopolitical_modes"][value="nationalism"]').forEach(enforceNationalismGate);
        }

        function showBrand(caseId, brand, saveFirst = true) {
          if (saveFirst) saveCase(caseId);
          const item = CONFIG.cases.find(candidate => candidate.case_id === caseId);
          if (!item) return;
          const selected = item.review_brands.includes(brand) ? brand : item.review_brands[0];
          state.ui.active_brand[caseId] = selected;
          document.querySelectorAll(`[data-case="${caseId}"][data-brand-tab]`).forEach(tab => tab.setAttribute("aria-selected", String(tab.dataset.brandTab === selected)));
          document.querySelectorAll(`[data-case="${caseId}"][data-brand-panel]`).forEach(panel => { panel.hidden = panel.dataset.brandPanel !== selected; });
          persist("Saved");
        }

        function showCase(caseId, saveFirst = true) {
          if (saveFirst && activeCase && state.cases[activeCase]) saveCase(activeCase);
          const item = CONFIG.cases.find(candidate => candidate.case_id === caseId) || CONFIG.cases[0];
          activeCase = item.case_id;
          document.querySelectorAll("[data-case-tab]").forEach(tab => tab.setAttribute("aria-selected", String(tab.dataset.caseTab === activeCase)));
          document.querySelectorAll("[data-case-panel]").forEach(panel => { panel.hidden = panel.dataset.casePanel !== activeCase; });
          const brand = state.ui.active_brand[activeCase] || item.review_brands[0];
          showBrand(activeCase, brand, false);
          document.querySelector(`[data-case-panel="${activeCase}"] .source-pane`)?.scrollTo(0, 0);
          document.querySelector(`[data-case-panel="${activeCase}"] .review-scroll`)?.scrollTo(0, 0);
          document.querySelector(`[data-case-tab="${activeCase}"]`)?.scrollIntoView({block: "nearest", inline: "nearest"});
        }

        function enforceExclusivity(input) {
          if (input.dataset.control !== "checkbox" || !input.checked) return;
          let exclusive = [];
          try { exclusive = JSON.parse(input.dataset.exclusive || "[]"); } catch (_) { return; }
          if (!exclusive.length) return;
          const siblings = [...input.closest(".choices").querySelectorAll('input[type="checkbox"]')];
          if (exclusive.includes(input.value)) siblings.forEach(other => { if (other !== input) other.checked = false; });
          else siblings.forEach(other => { if (exclusive.includes(other.value)) other.checked = false; });
        }

        const directionalNationalStances = new Set(["mild_pro", "pro", "constructive_critical", "anti", "mixed"]);
        const nationalStanceFields = new Set(["china_national_stance", "us_national_stance"]);

        function resetDirectionalNationalStances(panel) {
          nationalStanceFields.forEach(field => {
            const selected = panel.querySelector(`input[data-field="${field}"]:checked`);
            if (!selected || !directionalNationalStances.has(selected.value)) return;
            const none = panel.querySelector(`input[data-field="${field}"][value="none"]`);
            if (none) none.checked = true;
          });
        }

        function enforceNationalismGate(input) {
          if (input.dataset.scope !== "brand") return;
          const panel = input.closest("[data-brand-panel]");
          if (!panel) return;
          const nationalism = panel.querySelector('input[data-field="geopolitical_modes"][value="nationalism"]');
          if (!nationalism) return;

          if (nationalStanceFields.has(input.dataset.field) && input.checked && directionalNationalStances.has(input.value)) {
            nationalism.checked = true;
            enforceExclusivity(nationalism);
            return;
          }

          if (input.dataset.field !== "geopolitical_modes") return;
          const disablesNationalism = (input.value === "nationalism" && !input.checked)
            || (input.checked && ["none", "unavailable"].includes(input.value));
          if (disablesNationalism) resetDirectionalNationalStances(panel);
        }

        document.addEventListener("change", event => {
          const input = event.target.closest("[data-review-input]");
          if (!input) return;
          enforceExclusivity(input);
          enforceNationalismGate(input);
          saveCase(input.dataset.case);
        });
        document.addEventListener("input", event => {
          const input = event.target.closest("textarea[data-review-input]");
          if (!input) return;
          clearTimeout(timer);
          timer = setTimeout(() => saveCase(input.dataset.case), 180);
        });
        document.getElementById("caseTabs").addEventListener("click", event => {
          const tab = event.target.closest("[data-case-tab]");
          if (tab) showCase(tab.dataset.caseTab);
        });
        document.addEventListener("click", event => {
          const brandTab = event.target.closest("[data-brand-tab]");
          if (brandTab) return showBrand(brandTab.dataset.case, brandTab.dataset.brandTab);
          const panel = event.target.closest("[data-case-panel]");
          if (!panel) return;
          const index = CONFIG.cases.findIndex(item => item.case_id === panel.dataset.casePanel);
          if (event.target.closest("[data-save-case]")) saveCase(panel.dataset.casePanel, "Case saved");
          if (event.target.closest("[data-previous-case]")) showCase(CONFIG.cases[Math.max(0, index - 1)].case_id);
          if (event.target.closest("[data-next-case]")) showCase(CONFIG.cases[Math.min(CONFIG.cases.length - 1, index + 1)].case_id);
        });
        document.getElementById("exportJson").addEventListener("click", () => {
          saveCase(activeCase, "Saved before export");
          const payload = structuredClone(state);
          delete payload.ui;
          payload.exported_at = new Date().toISOString();
          const blob = new Blob([JSON.stringify(payload, null, 2) + "\\n"], {type: "application/json"});
          const link = document.createElement("a");
          link.href = URL.createObjectURL(blob);
          link.download = `${CONFIG.source_packet.replace(/\\.html$/i, "")}-answers.json`;
          link.click();
          setTimeout(() => URL.revokeObjectURL(link.href), 1000);
        });
        document.getElementById("clearAll").addEventListener("click", () => {
          if (!confirm("Clear every saved answer in this review packet? Export a JSON backup first if you may need it.")) return;
          localStorage.removeItem(STORAGE_KEY);
          state = blankState();
          activeCase = state.ui.active_case;
          restoreInputs();
          showCase(activeCase, false);
          persist("All answers cleared");
        });
        window.addEventListener("beforeunload", () => { collectCase(activeCase); localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); });
        document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") saveCase(activeCase); });

        restoreInputs();
        showCase(activeCase, false);
        if (state.saved_at) saveState.textContent = `Restored ${new Date(state.saved_at).toLocaleString()}`;
        updateProgress();
      })();
    </script>
  </body>
  </html>
HTML

output = Pathname.new(options.fetch(:output_html)).expand_path
abort "Refusing to overwrite source packet" if output == Pathname.new(options.fetch(:source_html)).expand_path
output.dirname.mkpath
File.write(output, html)

puts JSON.pretty_generate(
  output_html: output.to_s,
  cases: packet_cases.length,
  signal_backed_pairs: signal_backed_count,
  review_targets: review_target_count,
  taxonomy_id: taxonomy.fetch("taxonomy_id"),
  model_results: !model_results.nil?
)
