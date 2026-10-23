import urllib.request
import json

def test():
    login_data = json.dumps({"email": "architect@ndtm.kernel", "password": "KernelAdmin2026!"}).encode()
    login_req = urllib.request.Request("http://nginx/api/v1/auth/login", data=login_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(login_req) as resp:
        res = json.loads(resp.read().decode())
        token = res["access_token"]
        print("LOGIN OK. User:", res["user"]["email"])

    inc_req = urllib.request.Request("http://nginx/api/v1/incidents?limit=50&offset=0", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(inc_req) as resp:
        incs = json.loads(resp.read().decode())
        print(f"INCIDENTS OK: fetched {len(incs)} active incidents through NGINX proxy!")

    crdt_req = urllib.request.Request("http://nginx/api/v3/crdt/all-regions", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(crdt_req) as resp:
        crdt = json.loads(resp.read().decode())
        print("CRDT OK: fetched all regions status through NGINX proxy!")

    sre_req = urllib.request.Request("http://nginx/api/v3/sre/slo-budget", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(sre_req) as resp:
        sre = json.loads(resp.read().decode())
        print("SRE OK: fetched SLO budget through NGINX proxy! Remaining:", sre.get("remaining_budget_pct"))

if __name__ == "__main__":
    test()
