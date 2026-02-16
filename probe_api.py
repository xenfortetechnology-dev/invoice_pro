import requests
import json

CLOUD_API_BASE = "http://44.208.164.236:5000/api"

def probe():
    qid = 2469 
    patterns = [
        ("DELETE", f"/quotations/{qid}"),
        ("DELETE", f"/quotations?id={qid}"),
        ("DELETE", f"/quotations?quotation_id={qid}"),
        ("POST", f"/quotations/delete/{qid}"),
        ("POST", f"/quotation/delete/{qid}"),
        ("POST", f"/quotations/{qid}/delete"),
        ("POST", f"/quotation/{qid}/delete"),
        ("POST", f"/quotations/delete", {"id": qid}),
        ("POST", f"/quotation/delete", {"id": qid}),
        ("POST", f"/delete_quotation", {"id": qid}),
        ("POST", f"/delete_quotation?id={qid}"),
        ("GET", f"/quotations/delete/{qid}"),
        ("GET", f"/delete_quotation?id={qid}"),
        ("POST", f"/quotations", {"id": qid, "_method": "DELETE"}),
        ("PATCH", f"/quotations/{qid}", {"status": "Deleted"}),
    ]
    
    output = ""
    for method, path, *payload in patterns:
        url = f"{CLOUD_API_BASE}{path}"
        data = payload[0] if payload else None
        try:
            if method == "GET":
                r = requests.get(url, timeout=2)
            elif method == "POST":
                r = requests.post(url, json=data, timeout=2)
            elif method == "DELETE":
                r = requests.delete(url, timeout=2)
            elif method == "PATCH":
                r = requests.patch(url, json=data, timeout=2)
            
            output += f"{method} {path} -> {r.status_code}\n"
            if r.status_code != 404 and r.status_code != 405:
                output += f"  SUCCESS OR INTERESTING: {r.text[:200]}\n"
        except Exception as e:
            output += f"{method} {path} -> Error: {e}\n"
    
    with open("probe_results_v2.txt", "w") as f:
        f.write(output)
    print("Results saved to probe_results_v2.txt")

if __name__ == "__main__":
    probe()
