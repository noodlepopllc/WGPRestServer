import requests, json
#models = requests.get("http://127.0.0.1:8080/models").text
#print(models)
jobs = requests.get("http://127.0.0.1:8080/status").json()

print(jobs)


default = requests.get("http://127.0.0.1:8080/defaults/ltx2_25_22B_distilled").json()
#print(json.dumps(default, indent=4))

settings = {
    "model_type": "ltx2_22B_distilled",
    "prompt": "A beautiful red headed female eastern european in a sundress, lots of cleavage, eating ice cream that drips down her top, at a park near seattle.",
    "resolution": "1280x704",
    "num_inference_steps": 8,
    "video_length": 97,
    "duration_seconds": 4,
    "force_fps": 24,
    "output_dir": r"/home/todd/MCP/wangp_server"
}

default.update(settings)

#job_id = requests.post("http://127.0.0.1:8080/run", json=default).json()
#print(job_id)

status = requests.get("http://127.0.0.1:8080/status/1").json()
print(json.dumps(status, indent=4))

updates = requests.get("http://127.0.0.1:8080/updates/1").json()
print(updates)


