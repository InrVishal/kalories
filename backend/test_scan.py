import urllib.request
import json

boundary = "FormBoundary7MA4YWxkTrZu0gW"

with open("test_food.jpg", "rb") as f:
    image_bytes = f.read()

meta = json.dumps({
    "depth_mm": 120,
    "depth_supported": True,
    "device_model": "test",
    "os_version": 34
})

body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="image"; filename="test_food.jpg"\r\n'
    f"Content-Type: image/jpeg\r\n\r\n"
).encode() + image_bytes + (
    f"\r\n--{boundary}\r\n"
    f'Content-Disposition: form-data; name="meta"\r\n\r\n'
    f"{meta}"
    f"\r\n--{boundary}--\r\n"
).encode()

req = urllib.request.Request(
    "http://localhost:8000/scans",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
)

with urllib.request.urlopen(req, timeout=15) as resp:
    result = json.loads(resp.read())
    print(json.dumps(result, indent=2))
