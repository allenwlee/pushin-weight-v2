#!/usr/bin/env ruby
# frozen_string_literal: true

require "optparse"

options = { require_model_results: false }
OptionParser.new do |parser|
  parser.banner = "Usage: validate_tabbed_review.rb --html PATH [--cases N] [--require-model-results]"
  parser.on("--html PATH") { |value| options[:html] = value }
  parser.on("--cases N", Integer) { |value| options[:cases] = value }
  parser.on("--require-model-results") { options[:require_model_results] = true }
end.parse!

abort "Missing --html" if options[:html].to_s.empty?
abort "File not found: #{options[:html]}" unless File.file?(options[:html])

html = File.read(options[:html])
checks = {
  "layout marker" => html.scan(/data-layout-contract="pushinweight-tabbed-review-v1"/).length == 1,
  "horizontal overflow protection" => html.include?("overflow-wrap:anywhere"),
  "source pre-wrap" => html.include?("white-space:pre-wrap"),
  "independent source pane" => html.include?('class="source-pane"'),
  "independent review pane" => html.include?('class="review-pane"'),
}

case_tabs = html.scan(/<button\b[^>]*\bdata-case-tab="[^"]+"/).length
case_panels = html.scan(/<article\b[^>]*\bdata-case-panel="[^"]+"/).length
brand_tabs = html.scan(/<button\b[^>]*\bdata-brand-tab="[^"]+"/).length
brand_panels = html.scan(/<section\b[^>]*\bdata-brand-panel="[^"]+"/).length
checks["case tab/panel parity"] = case_tabs.positive? && case_tabs == case_panels
checks["brand tab/panel parity"] = brand_tabs.positive? && brand_tabs == brand_panels
checks["expected case count"] = case_tabs == options[:cases] if options[:cases]

translation_section_count = html.scan(/<summary>Stored English translation<\/summary>/).length
translation_count = html.scan(/class="[^"]*\bstored-translation\b[^"]*"/).length
translation_blocks = html.scan(/<[^>]+class="[^"]*\bstored-translation\b[^"]*"[^>]+data-source-format="(preserved|projected)"[^>]+data-source-lines="(\d+)"[^>]*>(.*?)<\/[^>]+>/m)
checks["translation formatting metadata"] = translation_section_count == translation_count && translation_blocks.length == translation_section_count
checks["multiline translations retain line breaks"] = translation_blocks.all? do |_mode, source_lines, body|
  source_lines.to_i <= 1 || body.include?("\n")
end

if options[:require_model_results]
  checks["model-results marker"] = html.scan(/data-model-results="true"/).length == 1
  checks["model result per brand and post"] = html.scan(/<aside\b[^>]*\bdata-model-result(?:\s|>)/).length == brand_panels + case_panels
  checks["red model result treatment"] = html.include?(".model-result-card") && html.include?("#fff4f2")
end

failures = checks.reject { |_name, passed| passed }
checks.each { |name, passed| puts "#{passed ? 'PASS' : 'FAIL'} #{name}" }
abort "Tabbed review layout validation failed" unless failures.empty?

puts "PASS cases=#{case_tabs} brand_reviews=#{brand_tabs} model_results=#{options[:require_model_results]}"
