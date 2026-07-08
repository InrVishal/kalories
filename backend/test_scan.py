import urllib.request
import urllib.error
import json
import time

API_HOST = "http://localhost:8000"

def make_request(url, data=None, headers=None, method=None):
    if headers is None:
        headers = {}
    if data is not None and isinstance(data, dict):
        data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return json.loads(body), e.code
        except Exception:
            return {"error": body}, e.code
    except Exception as e:
        return {"error": str(e)}, 0

def run_integration_test():
    print("[START] Starting integration and verification test...")

    # 1. Register a new user
    user_payload = {
        "username": f"testuser_{int(time.time())}",
        "password": "SuperSecurePassword123!"
    }
    print(f"1. Registering user: {user_payload['username']}...")
    reg_res, reg_code = make_request(f"{API_HOST}/auth/register", data=user_payload)
    if reg_code not in [200, 201]:
        print(f"[FAIL] Registration failed ({reg_code}): {reg_res}")
        return False
    print("[OK] Registration successful!")
    
    token = reg_res["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 2. Login to verify credentials
    print("2. Verifying login...")
    login_res, login_code = make_request(f"{API_HOST}/auth/login", data=user_payload)
    if login_code != 200:
        print(f"[FAIL] Login failed ({login_code}): {login_res}")
        return False
    print("[OK] Login successful! Token verified.")

    # 3. Submit a food image scan (POST /scans)
    print("3. Submitting food scan...")
    boundary = "FormBoundary7MA4YWxkTrZu0gW"
    try:
        with open("test_food.jpg", "rb") as f:
            image_bytes = f.read()
    except FileNotFoundError:
        image_bytes = b"fake-jpg-binary-content-for-testing"

    meta = json.dumps({
        "depth_mm": 120,
        "depth_supported": True,
        "device_model": "integration-test-runner",
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

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {token}"
    }

    scan_res, scan_code = make_request(f"{API_HOST}/scans", data=body, headers=headers)
    if scan_code not in [200, 201, 202]:
        print(f"[FAIL] Scan submission failed ({scan_code}): {scan_res}")
        return False
    
    scan_id = scan_res["scan_id"]
    status = scan_res["status"]
    print(f"[OK] Scan submitted successfully! scan_id={scan_id}, status={status}")

    # 4. Poll status (GET /scans/{scan_id})
    print("4. Polling scan status...")
    max_polls = 60
    for attempt in range(max_polls):
        time.sleep(2.0)
        poll_res, poll_code = make_request(f"{API_HOST}/scans/{scan_id}", headers=auth_headers, method="GET")
        if poll_code != 200:
            print(f"[FAIL] Polling failed ({poll_code}): {poll_res}")
            return False
        
        status = poll_res["status"]
        print(f"   [Poll {attempt + 1}] status = {status}")
        
        if status == "complete":
            print("[OK] Scan completed successfully in background!")
            print(json.dumps(poll_res, indent=2))
            return True
        elif status == "failed":
            print(f"[FAIL] Background scan failed: {poll_res}")
            return False

    print("[FAIL] Polling timed out (scan stuck in pending state)")
    return False

if __name__ == "__main__":
    run_integration_test()
