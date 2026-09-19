"""Capture public OpenRouter model and endpoint metadata; no credentials or inference calls."""
import csv, hashlib, json, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

API = "https://openrouter.ai/api/v1"
CANDIDATES = ["tencent/hy-mt2-1.8b", "tencent/hy-mt2-7b", "openai/gpt-oss-120b", "openai/gpt-5-nano"]

def now(): return datetime.now(timezone.utc).isoformat()
def get(url):
    started = now()
    try:
        req = urllib.request.Request(url, headers={"Accept":"application/json", "User-Agent":"PushinWeight-model-endpoint-snapshot/1.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read()
            return {"url":url,"started_at_utc":started,"retrieved_at_utc":now(),"http_status":response.status,
                    "http_version":getattr(response, "version", None),"http_date":response.headers.get("Date"),
                    "etag":response.headers.get("ETag"),"cache_control":response.headers.get("Cache-Control"),
                    "age":response.headers.get("Age")}, body, json.loads(body)
    except urllib.error.HTTPError as exc:
        return {"url":url,"started_at_utc":started,"retrieved_at_utc":now(),"http_status":exc.code,
                "http_date":exc.headers.get("Date") if exc.headers else None}, None, None
    except Exception as exc:
        return {"url":url,"started_at_utc":started,"retrieved_at_utc":now(),"error_type":type(exc).__name__}, None, None

root = Path(__file__).resolve().parent
(root / "raw").mkdir(parents=True, exist_ok=True)
started = now(); receipts=[]; rows=[]; coverage=[]

def fetch(mid): return mid, get(API + "/models/" + mid + "/endpoints")
with ThreadPoolExecutor(max_workers=3) as pool:
    results = list(pool.map(fetch, CANDIDATES))
for mid, (receipt, body, obj) in results:
    fn = "raw/endpoints-" + mid.replace("/", "__") + ".json"
    if body is not None:
        (root / fn).write_bytes(body)
        receipt["file"] = fn
    receipts.append(receipt)
    eps = ((obj or {}).get("data") or {}).get("endpoints") or []
    coverage.append({"model_id":mid,"url":receipt["url"],"http_status":receipt.get("http_status"),"endpoint_count":len(eps),"error_type":receipt.get("error_type"),"raw_file":fn if body is not None else None})
    for ep in eps:
        rows.append({"model_id":mid,"endpoint_name":ep.get("name"),"provider_name":ep.get("provider_name"),"endpoint_tag":ep.get("tag"),"quantization":ep.get("quantization"),"context_length":ep.get("context_length"),"max_completion_tokens":ep.get("max_completion_tokens"),"supported_parameters":json.dumps(ep.get("supported_parameters"),separators=(",",":")),"input_modalities":json.dumps(ep.get("architecture",{}).get("input_modalities"),separators=(",",":")),"output_modalities":json.dumps(ep.get("architecture",{}).get("output_modalities"),separators=(",",":")),"pricing":json.dumps(ep.get("pricing"),separators=(",",":")),"endpoint_json":json.dumps(ep,separators=(",",":"))})
fields=list(rows[0]) if rows else ["model_id","endpoint_name","provider_name","endpoint_tag","quantization","context_length","max_completion_tokens","supported_parameters","input_modalities","output_modalities","pricing","endpoint_json"]
with (root / "endpoint-metadata.csv").open("x",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
summary={"schema":"openrouter-model-endpoint-snapshot/v1","started_at_utc":started,"finished_at_utc":now(),"candidate_model_count":len(CANDIDATES),"endpoint_count":len(rows),"candidate_coverage":coverage,"requests":receipts,"scope":"Public GET endpoint metadata for four named model routes; no inference, credentials, or paid calls.","warnings":["Empty endpoint arrays indicate no endpoint returned by this API response at capture time.","Provider availability, tags, parameters and prices may change after capture."]}
summary["sha256"]={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file() and p.name != "manifest.json"}
(root / "manifest.json").write_text(json.dumps(summary,indent=2)+"\n")
print(json.dumps({"directory":str(root),"endpoints":len(rows),"coverage":coverage,"verified":all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in summary["sha256"].items())},indent=2))
